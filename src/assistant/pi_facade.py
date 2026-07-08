from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping
from urllib.parse import quote

from config.settings import Settings, load_settings
from db.ai_report_feedback import summarize_ai_report_feedback
from db.idea_threads import fetch_idea_thread_atoms, fetch_idea_threads
from output.intelligence_retrieval_items import (
    build_retrieval_items,
    find_latest_week_label,
    load_latest_workbook_json,
    load_mvp_radar_status,
    search_retrieval_items,
)


TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,}")


class PersonalIntelligenceFacade:
    """Read-only DTO facade for Hermes/PI Assistant foundations."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        db_path: str | Path | None = None,
        output_root: str | Path | None = None,
        visual_output_root: str | Path | None = None,
        ai_output_root: str | Path | None = None,
        mvp_output_root: str | Path | None = None,
        radar_output_root: str | Path | None = None,
        now: datetime | None = None,
    ) -> None:
        base_settings = settings or load_settings()
        if db_path is not None:
            base_settings = Settings(
                db_path=str(db_path),
                llm_api_key=base_settings.llm_api_key,
                model_provider=base_settings.model_provider,
                telegram_session_path=base_settings.telegram_session_path,
            )
        self._settings = base_settings
        self._output_root = Path(output_root) if output_root is not None else None
        self._visual_output_root = Path(visual_output_root) if visual_output_root is not None else None
        self._ai_output_root = Path(ai_output_root) if ai_output_root is not None else None
        self._mvp_output_root = Path(mvp_output_root) if mvp_output_root is not None else None
        self._radar_output_root = Path(radar_output_root) if radar_output_root is not None else None
        self._now = now

    def get_current_week_label(self) -> dict:
        week = find_latest_week_label(
            self._settings,
            output_root=self._output_root,
            visual_output_root=self._visual_output_root,
            ai_output_root=self._ai_output_root,
        )
        if week:
            return {
                "status": "ok",
                "week_label": week,
                "source": "latest_artifact",
                "message": "Latest workbook artifact found.",
            }
        current = self._current_week_label()
        return {
            "status": "ok",
            "week_label": current,
            "source": "date",
            "message": "No workbook artifact found; using the current ISO week label.",
        }

    def get_workbook_summary(self, week_label: str | None = None) -> dict:
        workbook = self._load_workbook(week_label)
        stable = self._empty_workbook_summary(week_label)
        if workbook is None:
            return {
                **stable,
                "status": "missing",
                "message": "Workbook JSON sidecar is missing.",
            }
        actual_week = _clean_text(workbook.get("week_label")) or week_label
        mvp_payload = workbook.get("mvp_radar") if isinstance(workbook.get("mvp_radar"), Mapping) else None
        return {
            "status": "ok",
            "week_label": actual_week,
            "title": f"Weekly AI Intelligence Workbook {actual_week}" if actual_week else "Weekly AI Intelligence Workbook",
            "generated_at": _clean_text(workbook.get("generated_at")) or None,
            "decision_brief": _decision_cards(workbook),
            "strong_signals": _strong_signals(workbook),
            "actions": _action_cards(workbook),
            "project_actions": _project_actions(workbook),
            "mvp_status": _mvp_status(mvp_payload, actual_week) if mvp_payload else None,
            "artifact_paths": _artifact_paths(workbook),
            "message": "Workbook summary loaded from JSON sidecar.",
        }

    def get_workbook_sections(self, week_label: str) -> dict:
        clean_week = str(week_label or "").strip()
        workbook = self._load_workbook(clean_week)
        if workbook is None:
            return {
                "status": "missing",
                "week_label": clean_week,
                "sections": [],
                "message": "Workbook JSON sidecar is missing.",
            }
        sections = _workbook_sections(workbook)
        return {
            "status": "ok",
            "week_label": _clean_text(workbook.get("week_label")) or clean_week,
            "sections": sections,
            "message": "Workbook sections loaded from JSON sidecar.",
        }

    def search_idea_threads(
        self,
        query: str,
        week_label: str | None = None,
        limit: int = 10,
    ) -> dict:
        threads = self._idea_thread_summaries(week_label=week_label)
        tokens = _tokens(query)
        scored: list[tuple[float, dict]] = []
        for thread in threads:
            score = _keyword_score(
                query,
                tokens,
                thread.get("slug"),
                thread.get("title"),
                thread.get("summary"),
                " ".join(_string_values(thread.get("claims"))),
            )
            if tokens and score <= 0:
                continue
            scored.append((score, thread))
        scored.sort(
            key=lambda pair: (
                pair[0],
                float(pair[1].get("momentum") or 0.0),
                str(pair[1].get("last_seen_at") or ""),
                str(pair[1].get("slug") or ""),
            ),
            reverse=True,
        )
        items = [
            {
                "slug": thread.get("slug"),
                "title": thread.get("title"),
                "summary": thread.get("summary"),
                "status": thread.get("status"),
                "momentum": thread.get("momentum"),
                "last_seen_at": thread.get("last_seen_at"),
                "source_atom_ids": list(thread.get("source_atom_ids") or []),
                "source_urls": list(thread.get("source_urls") or []),
            }
            for _score, thread in scored[: max(1, int(limit or 10))]
        ]
        return {
            "status": "ok" if items else "empty",
            "query": str(query or ""),
            "week_label": week_label,
            "items": items,
            "message": "Idea threads matched deterministic search." if items else "No matching idea threads found.",
        }

    def get_idea_thread(self, slug: str) -> dict:
        clean_slug = str(slug or "").strip()
        if not clean_slug:
            return self._missing_idea_thread(clean_slug, "Idea thread slug is required.")
        detail = self._idea_thread_detail_from_db(clean_slug) or self._idea_thread_detail_from_workbook(clean_slug)
        if detail is None:
            return self._missing_idea_thread(clean_slug, "Idea thread is missing.")
        return {
            "status": "ok",
            "slug": clean_slug,
            "title": detail.get("title"),
            "summary": detail.get("summary"),
            "claims": list(detail.get("claims") or []),
            "source_atom_ids": list(detail.get("source_atom_ids") or []),
            "source_urls": list(detail.get("source_urls") or []),
            "timeline": list(detail.get("timeline") or []),
            "message": "Idea thread loaded from curated thread storage.",
        }

    def get_project_actions(self, week_label: str | None = None) -> dict:
        workbook = self._load_workbook(week_label)
        if workbook is None:
            return {
                "status": "missing",
                "week_label": week_label,
                "items": [],
                "message": "Workbook JSON sidecar is missing.",
            }
        items = _project_actions(workbook)
        return {
            "status": "ok" if items else "empty",
            "week_label": _clean_text(workbook.get("week_label")) or week_label,
            "items": items,
            "message": "Project actions loaded from workbook." if items else "No project actions are available.",
        }

    def get_mvp_radar_status(self, week_label: str | None = None) -> dict:
        clean_week = str(week_label or "").strip() or self.get_current_week_label()["week_label"]
        workbook = self._load_workbook(clean_week)
        payload = workbook.get("mvp_radar") if isinstance(workbook, Mapping) and isinstance(workbook.get("mvp_radar"), Mapping) else None
        if not payload or _clean_text(payload.get("status")) == "not_available":
            payload = load_mvp_radar_status(
                clean_week,
                output_root=self._output_root,
                mvp_output_root=self._mvp_output_root,
                radar_output_root=self._radar_output_root,
            )
        if not payload:
            return {
                "status": "missing",
                "week_label": clean_week,
                "candidate": None,
                "dossier_status": None,
                "recommendation": None,
                "source_mix": None,
                "missing_evidence": [],
                "next_validation": [],
                "message": "MVP Radar result is missing.",
            }
        normalized = _mvp_status(payload, clean_week)
        missing_result = normalized["candidate"] is None and normalized["dossier_status"] is None
        return {
            **normalized,
            "status": "missing" if missing_result else "ok",
            "message": "MVP Radar status loaded." if not missing_result else "MVP Radar result is insufficient.",
        }

    def get_feedback_summary(self, week_label: str | None = None) -> dict:
        clean_week = str(week_label or "").strip() or None
        with self._readonly_connection() as connection:
            if connection is None or not _table_exists(connection, "ai_report_feedback_events"):
                return _empty_feedback_summary(clean_week, "missing", "AI report feedback table is missing.")
            try:
                summary = summarize_ai_report_feedback(connection, week_label=clean_week, limit=100)
            except sqlite3.Error:
                return _empty_feedback_summary(clean_week, "missing", "AI report feedback summary could not be loaded.")
        events = [event for event in summary.get("recent_events") or [] if isinstance(event, Mapping)]
        grouped = {
            "useful": _feedback_events(events, "useful"),
            "wrong_priority": _feedback_events(events, "wrong_priority"),
            "not_interested": _feedback_events(events, "not_interested"),
            "applied_to_project": _feedback_events(events, "applied_to_project"),
            "tried": _feedback_events(events, "tried"),
        }
        count = int(summary.get("event_count") or 0)
        return {
            "status": "ok" if count else "empty",
            "week_label": clean_week,
            "counts": dict(summary.get("counts_by_feedback") or {}),
            **grouped,
            "message": "Feedback summary loaded." if count else "No feedback events are available.",
        }

    def list_marked_posts(self, week_label: str | None = None, limit: int = 20) -> dict:
        clean_week = str(week_label or "").strip() or self.get_current_week_label()["week_label"]
        workbook = self._load_workbook(clean_week)
        workbook_posts = [
            _marked_post_item(post)
            for post in ((workbook or {}).get("marked_posts") or [])
            if isinstance(post, Mapping)
        ]
        if workbook_posts:
            return {
                "status": "ok",
                "week_label": clean_week,
                "items": workbook_posts[: max(1, int(limit or 20))],
                "message": "Marked posts loaded from workbook sidecar.",
            }
        with self._readonly_connection() as connection:
            if connection is None or not _table_exists(connection, "signal_feedback") or not _table_exists(connection, "posts"):
                return {
                    "status": "empty" if workbook is not None else "missing",
                    "week_label": clean_week,
                    "items": [],
                    "message": "Reaction/marked-post data is unavailable." if workbook is None else "No marked posts are available.",
                }
            rows = self._marked_post_rows(connection, clean_week, max(1, int(limit or 20)))
        items = [_marked_post_item(row) for row in rows]
        return {
            "status": "ok" if items else "empty",
            "week_label": clean_week,
            "items": items,
            "message": "Marked posts loaded." if items else "No marked posts are available; no reaction is treated as unknown, not negative.",
        }

    def search_intelligence_items(
        self,
        query: str,
        filters: dict | None = None,
        limit: int = 10,
    ) -> dict:
        clean_filters = dict(filters or {})
        items = build_retrieval_items(
            self._settings,
            week_label=clean_filters.get("week_label"),
            output_root=self._output_root,
            visual_output_root=self._visual_output_root,
            ai_output_root=self._ai_output_root,
            mvp_output_root=self._mvp_output_root,
            radar_output_root=self._radar_output_root,
        )
        results = search_retrieval_items(items, query, filters=clean_filters, limit=limit)
        return {
            "status": "ok" if results else "empty",
            "query": str(query or ""),
            "filters": clean_filters,
            "items": results,
            "message": "Curated intelligence items matched deterministic search." if results else "No curated intelligence items matched.",
        }

    def _current_week_label(self) -> str:
        current = self._now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        year, week, _day = current.astimezone(timezone.utc).isocalendar()
        return f"{year}-W{week:02d}"

    def _load_workbook(self, week_label: str | None) -> dict | None:
        return load_latest_workbook_json(
            self._settings,
            week_label,
            output_root=self._output_root,
            visual_output_root=self._visual_output_root,
            ai_output_root=self._ai_output_root,
        )

    @contextmanager
    def _readonly_connection(self) -> Iterator[sqlite3.Connection | None]:
        path = Path(str(self._settings.db_path))
        if not path.exists():
            yield None
            return
        uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(uri, uri=True)
            connection.row_factory = sqlite3.Row
            yield connection
        except sqlite3.Error:
            yield None
        finally:
            if connection is not None:
                connection.close()

    def _idea_thread_summaries(self, *, week_label: str | None) -> list[dict]:
        summaries = self._idea_threads_from_db(week_label=week_label)
        if summaries:
            return summaries
        workbook = self._load_workbook(week_label)
        return _idea_threads_from_workbook(workbook or {})

    def _idea_threads_from_db(self, *, week_label: str | None) -> list[dict]:
        with self._readonly_connection() as connection:
            if connection is None or not _table_exists(connection, "idea_threads") or not _table_exists(connection, "idea_thread_atoms"):
                return []
            try:
                threads = fetch_idea_threads(connection, limit=200)
            except sqlite3.Error:
                return []
            result: list[dict] = []
            for thread in threads:
                if week_label and not _thread_in_week_window(thread, week_label):
                    continue
                atoms = self._thread_atoms(connection, thread)
                source_urls = _unique(url for atom in atoms for url in _string_values(atom.get("source_urls")))
                atom_ids = [atom.get("id") for atom in atoms if atom.get("id") is not None]
                result.append(
                    {
                        "slug": thread.get("slug"),
                        "title": thread.get("title"),
                        "summary": thread.get("summary"),
                        "status": thread.get("status"),
                        "momentum": thread.get("momentum_30d"),
                        "last_seen_at": thread.get("last_seen_at"),
                        "claims": list(thread.get("current_claims") or []),
                        "source_atom_ids": atom_ids,
                        "source_urls": source_urls,
                    }
                )
            return result

    def _idea_thread_detail_from_db(self, slug: str) -> dict | None:
        with self._readonly_connection() as connection:
            if connection is None or not _table_exists(connection, "idea_threads") or not _table_exists(connection, "idea_thread_atoms"):
                return None
            try:
                threads = fetch_idea_threads(connection, slug=slug, limit=1)
            except sqlite3.Error:
                return None
            if not threads:
                return None
            thread = threads[0]
            atoms = self._thread_atoms(connection, thread)
        source_urls = _unique(url for atom in atoms for url in _string_values(atom.get("source_urls")))
        atom_ids = [atom.get("id") for atom in atoms if atom.get("id") is not None]
        timeline = [
            {
                "atom_id": atom.get("id"),
                "relation": atom.get("relation"),
                "claim": atom.get("claim"),
                "last_seen_at": atom.get("last_seen_at"),
                "source_urls": list(atom.get("source_urls") or []),
            }
            for atom in sorted(atoms, key=lambda item: str(item.get("last_seen_at") or ""))
        ]
        claims = [
            {
                "claim": atom.get("claim"),
                "atom_id": atom.get("id"),
                "evidence_quote": atom.get("evidence_quote"),
                "source_urls": list(atom.get("source_urls") or []),
            }
            for atom in atoms
            if atom.get("claim")
        ]
        if not claims:
            claims = [{"claim": claim, "atom_id": None, "evidence_quote": None, "source_urls": []} for claim in thread.get("current_claims") or []]
        return {
            "title": thread.get("title"),
            "summary": thread.get("summary"),
            "claims": claims,
            "source_atom_ids": atom_ids,
            "source_urls": source_urls,
            "timeline": timeline,
        }

    def _idea_thread_detail_from_workbook(self, slug: str) -> dict | None:
        workbook = self._load_workbook(None)
        for thread in _idea_threads_from_workbook(workbook or {}):
            if thread.get("slug") != slug:
                continue
            return {
                "title": thread.get("title"),
                "summary": thread.get("summary"),
                "claims": [{"claim": claim, "atom_id": None, "evidence_quote": None, "source_urls": []} for claim in thread.get("claims") or []],
                "source_atom_ids": list(thread.get("source_atom_ids") or []),
                "source_urls": list(thread.get("source_urls") or []),
                "timeline": [],
            }
        return None

    def _thread_atoms(self, connection: sqlite3.Connection, thread: Mapping[str, Any]) -> list[dict]:
        try:
            return fetch_idea_thread_atoms(connection, thread_id=int(thread["id"]), limit=100)
        except (KeyError, TypeError, ValueError, sqlite3.Error):
            return []

    def _marked_post_rows(self, connection: sqlite3.Connection, week_label: str, limit: int) -> list[dict]:
        start, end = _week_bounds(week_label)
        has_raw = _table_exists(connection, "raw_posts")
        if has_raw:
            sql = """
            SELECT
                signal_feedback.feedback AS reaction,
                signal_feedback.recorded_at,
                posts.id AS post_id,
                posts.channel_username,
                posts.content,
                raw_posts.message_url
            FROM signal_feedback
            JOIN posts ON posts.id = signal_feedback.post_id
            LEFT JOIN raw_posts ON raw_posts.id = posts.raw_post_id
            WHERE signal_feedback.feedback IN ('operator_marked_interesting', 'marked_important')
              AND signal_feedback.recorded_at >= ?
              AND signal_feedback.recorded_at < ?
            ORDER BY signal_feedback.recorded_at DESC, signal_feedback.id DESC
            LIMIT ?
            """
        else:
            sql = """
            SELECT
                signal_feedback.feedback AS reaction,
                signal_feedback.recorded_at,
                posts.id AS post_id,
                posts.channel_username,
                posts.content,
                NULL AS message_url
            FROM signal_feedback
            JOIN posts ON posts.id = signal_feedback.post_id
            WHERE signal_feedback.feedback IN ('operator_marked_interesting', 'marked_important')
              AND signal_feedback.recorded_at >= ?
              AND signal_feedback.recorded_at < ?
            ORDER BY signal_feedback.recorded_at DESC, signal_feedback.id DESC
            LIMIT ?
            """
        try:
            rows = connection.execute(sql, (_iso_for_sql(start), _iso_for_sql(end), limit)).fetchall()
        except sqlite3.Error:
            return []
        return [
            {
                "post_id": row["post_id"],
                "channel": row["channel_username"],
                "snippet": row["content"],
                "source_url": row["message_url"],
                "reaction": row["reaction"],
            }
            for row in rows
        ]

    @staticmethod
    def _empty_workbook_summary(week_label: str | None) -> dict:
        return {
            "status": "missing",
            "week_label": week_label,
            "title": None,
            "generated_at": None,
            "decision_brief": None,
            "strong_signals": [],
            "actions": [],
            "project_actions": [],
            "mvp_status": None,
            "artifact_paths": {"html": None, "json": None},
            "message": "",
        }

    @staticmethod
    def _missing_idea_thread(slug: str, message: str) -> dict:
        return {
            "status": "missing",
            "slug": slug,
            "title": None,
            "summary": None,
            "claims": [],
            "source_atom_ids": [],
            "source_urls": [],
            "timeline": [],
            "message": message,
        }


def _decision_cards(workbook: Mapping[str, Any]) -> list:
    cards = [card for card in workbook.get("decision_cards") or [] if isinstance(card, Mapping)]
    return [
        {
            "id": card.get("id"),
            "verdict": card.get("verdict"),
            "title": card.get("title"),
            "summary": card.get("why_for_operator"),
            "next_action": card.get("next_action"),
            "confidence": card.get("confidence"),
            "atom_ids": list(card.get("evidence_atom_ids") or []),
        }
        for card in cards
    ]


def _strong_signals(workbook: Mapping[str, Any]) -> list:
    cards = [card for card in workbook.get("claim_cards") or [] if isinstance(card, Mapping)]
    return [
        {
            "id": card.get("id"),
            "claim": card.get("claim"),
            "summary": card.get("caveat"),
            "source_refs": list(card.get("source_urls") or []),
            "atom_ids": list(card.get("evidence_atom_ids") or []),
            "evidence_tier": card.get("evidence_tier"),
            "verification_status": card.get("verification_status"),
            "confidence": card.get("confidence"),
        }
        for card in cards
    ]


def _action_cards(workbook: Mapping[str, Any]) -> list:
    cards = [card for card in workbook.get("action_cards") or workbook.get("actions") or [] if isinstance(card, Mapping)]
    return [
        {
            "id": card.get("id") or card.get("target_ref"),
            "title": card.get("title"),
            "next_step": card.get("next_step") or card.get("body"),
            "success_criterion": card.get("success_criterion"),
            "effort": card.get("effort"),
            "scope": card.get("scope"),
            "feedback_target_id": card.get("feedback_target_id"),
        }
        for card in cards
    ]


def _project_actions(workbook: Mapping[str, Any]) -> list:
    diagnostic = workbook.get("project_diagnostic") if isinstance(workbook.get("project_diagnostic"), Mapping) else {}
    suggestions = [item for item in diagnostic.get("implementation_suggestions") or [] if isinstance(item, Mapping)]
    return [
        {
            "project": suggestion.get("project"),
            "action": suggestion.get("title") or suggestion.get("next_step"),
            "why": suggestion.get("why") or suggestion.get("next_step"),
            "effort": suggestion.get("effort"),
            "acceptance": list(suggestion.get("acceptance_criteria") or []),
            "source_refs": _unique([*(suggestion.get("source_urls") or []), *[f"atom:{atom_id}" for atom_id in suggestion.get("source_atom_ids") or []]]),
            "risk": suggestion.get("risk_caveat"),
        }
        for suggestion in suggestions
    ]


def _mvp_status(payload: Mapping[str, Any] | None, week_label: str | None) -> dict:
    payload = payload or {}
    candidate = _clean_text(payload.get("selected_candidate") or payload.get("selected_title") or payload.get("title")) or None
    return {
        "status": "ok",
        "week_label": week_label,
        "candidate": candidate,
        "dossier_status": _clean_text(payload.get("dossier_status")) or None,
        "recommendation": _clean_text(payload.get("recommendation")) or None,
        "source_mix": dict(payload.get("source_mix") or {}) if isinstance(payload.get("source_mix"), Mapping) else None,
        "missing_evidence": _string_values(payload.get("missing_evidence")),
        "next_validation": _string_values(payload.get("next_validation")),
        "message": "",
    }


def _workbook_sections(workbook: Mapping[str, Any]) -> list[dict]:
    sections = workbook.get("workbook_sections")
    if isinstance(sections, list):
        rows = [section for section in sections if isinstance(section, Mapping)]
    else:
        rows = [
            {"id": _slug(title), "title": title, "title_en": title, "kind": _slug(title).replace("-", "_")}
            for title in workbook.get("sections") or []
            if str(title).strip()
        ]
    result = []
    for row in rows:
        section_id = _clean_text(row.get("id")) or _slug(row.get("title"))
        kind = _clean_text(row.get("kind"))
        result.append(
            {
                "id": section_id,
                "title": _clean_text(row.get("title_en")) or _clean_text(row.get("title")) or section_id,
                "summary": _section_summary(workbook, section_id, kind),
                "items": _section_items(workbook, section_id, kind),
                "source": "workbook_json",
            }
        )
    return result


def _section_items(workbook: Mapping[str, Any], section_id: str, kind: str) -> list:
    normalized = f"{section_id} {kind}".replace("-", "_")
    if "decision" in normalized:
        return _decision_cards(workbook)
    if "strong" in normalized:
        return _strong_signals(workbook)
    if "deep" in normalized:
        return [
            {
                "id": card.get("id"),
                "title": card.get("title"),
                "summary": card.get("what_is_this"),
                "source_refs": list(card.get("source_urls") or []),
                "evidence_tier": card.get("evidence_tier"),
                "verification_status": card.get("quote_verification_status"),
            }
            for card in workbook.get("deep_explanation_cards") or []
            if isinstance(card, Mapping)
        ]
    if "project" in normalized:
        return _project_actions(workbook)
    if "mvp" in normalized:
        payload = workbook.get("mvp_radar") if isinstance(workbook.get("mvp_radar"), Mapping) else {}
        return [_mvp_status(payload, workbook.get("week_label"))]
    if "read" in normalized or "try" in normalized or "build" in normalized:
        return _action_cards(workbook)
    if "feedback" in normalized:
        return [
            {
                "id": target.get("id"),
                "target_type": target.get("target_type"),
                "prompt": target.get("prompt"),
                "event_options": list(target.get("event_options") or []),
            }
            for target in workbook.get("feedback_targets") or []
            if isinstance(target, Mapping)
        ]
    return []


def _section_summary(workbook: Mapping[str, Any], section_id: str, kind: str) -> str | None:
    items = _section_items(workbook, section_id, kind)
    for item in items:
        if not isinstance(item, Mapping):
            continue
        for key in ("summary", "title", "claim", "action", "next_step", "candidate"):
            text = _clean_text(item.get(key))
            if text:
                return text
    return None


def _artifact_paths(workbook: Mapping[str, Any]) -> dict:
    paths = workbook.get("_artifact_paths") if isinstance(workbook.get("_artifact_paths"), Mapping) else {}
    return {
        "html": _clean_text(paths.get("html") or workbook.get("html_path")) or None,
        "json": _clean_text(paths.get("json") or workbook.get("json_path")) or None,
    }


def _feedback_events(events: Iterable[Mapping[str, Any]], feedback_type: str) -> list:
    return [
        {
            "target_type": event.get("target_type"),
            "target_ref": event.get("target_ref"),
            "source_url": event.get("source_url"),
            "notes": event.get("notes"),
            "created_at": event.get("created_at"),
        }
        for event in events
        if event.get("feedback_type") == feedback_type
    ]


def _empty_feedback_summary(week_label: str | None, status: str, message: str) -> dict:
    return {
        "status": status,
        "week_label": week_label,
        "counts": {},
        "useful": [],
        "wrong_priority": [],
        "not_interested": [],
        "applied_to_project": [],
        "tried": [],
        "message": message,
    }


def _marked_post_item(post: Mapping[str, Any]) -> dict:
    content = _clean_text(post.get("content") or post.get("snippet") or "")
    reaction = _clean_text(post.get("reaction") or post.get("feedback")) or None
    return {
        "post_id": post.get("post_id"),
        "channel": post.get("channel") or post.get("channel_username"),
        "title": _first_sentence(content) if content else None,
        "snippet": _truncate(content, 240) if content else None,
        "source_url": post.get("source_url") or post.get("message_url"),
        "reaction": reaction,
        "marked_reason_guess": "interesting" if reaction else None,
    }


def _idea_threads_from_workbook(workbook: Mapping[str, Any]) -> list[dict]:
    result: list[dict] = []
    for item in workbook.get("compressed_context") or []:
        if not isinstance(item, Mapping):
            continue
        result.append(
            {
                "slug": item.get("slug"),
                "title": item.get("title") or item.get("slug"),
                "summary": item.get("summary"),
                "status": item.get("status"),
                "momentum": item.get("momentum_30d"),
                "last_seen_at": item.get("last_seen_at"),
                "claims": list(item.get("current_claims") or []),
                "source_atom_ids": list(item.get("source_atom_ids") or []),
                "source_urls": [],
            }
        )
    for delta in workbook.get("thread_deltas") or []:
        if not isinstance(delta, Mapping):
            continue
        slug = delta.get("thread_slug")
        if not slug or any(item.get("slug") == slug for item in result):
            continue
        result.append(
            {
                "slug": slug,
                "title": delta.get("title") or slug,
                "summary": delta.get("updated_interpretation") or delta.get("new_evidence"),
                "status": delta.get("state"),
                "momentum": None,
                "last_seen_at": None,
                "claims": [delta.get("new_evidence"), delta.get("updated_interpretation")],
                "source_atom_ids": list(delta.get("new_evidence_atom_ids") or []),
                "source_urls": [],
            }
        )
    return result


def _thread_in_week_window(thread: Mapping[str, Any], week_label: str) -> bool:
    try:
        _start, end = _week_bounds(week_label)
    except ValueError:
        return True
    last_seen = _parse_iso(thread.get("last_seen_at"))
    if last_seen is None:
        return True
    return last_seen < end


def _week_bounds(week_label: str) -> tuple[datetime, datetime]:
    year_str, week_str = str(week_label).split("-W", maxsplit=1)
    start_date = date.fromisocalendar(int(year_str), int(week_str), 1)
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    return start, start + timedelta(days=7)


def _iso_for_sql(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: object) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    try:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            LIMIT 1
            """,
            (table_name,),
        ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def _tokens(value: object) -> list[str]:
    result: list[str] = []
    for match in TOKEN_RE.findall(str(value or "").lower()):
        if match not in result:
            result.append(match)
    return result


def _keyword_score(query: str, tokens: list[str], *values: object) -> float:
    haystack = " ".join(_clean_text(value).lower() for value in values if value is not None)
    titleish = _clean_text(values[1] if len(values) > 1 else "").lower()
    score = 0.0
    phrase = str(query or "").strip().lower()
    if phrase and phrase in haystack:
        score += 4.0
    for token in tokens:
        if token in titleish:
            score += 3.0
        if token in haystack:
            score += 1.0
    return score


def _string_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    return _unique(_clean_text(item) for item in values if _clean_text(item))


def _unique(values: Iterable[Any]) -> list:
    result = []
    seen = set()
    for value in values:
        if value in (None, ""):
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _first_sentence(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    return re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0][:120]


def _truncate(value: str, limit: int) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _slug(value: object) -> str:
    text = _clean_text(value).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug or "section"
