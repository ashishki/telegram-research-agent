from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping
from urllib.parse import quote

from config.settings import PROJECT_ROOT, Settings, load_settings
from db.ai_report_feedback import fetch_ai_report_feedback, summarize_ai_report_feedback
from db.idea_threads import fetch_idea_thread_atoms, fetch_idea_threads
from output.action_status import build_action_status_projection, summarize_action_statuses
from output.intelligence_retrieval_items import (
    DEFAULT_KNOWLEDGE_ATLAS_OUTPUT_DIR,
    DEFAULT_WEEKLY_BRIEF_OUTPUT_DIR,
    _dedupe_items,
    _items_from_workbook,
    build_retrieval_items,
    find_latest_week_label,
    load_latest_workbook_json,
    load_mvp_radar_status,
)
from output.mvp_radar_reader import (
    MvpRadarReaderError,
    adapt_legacy_mvp_radar_payload,
    invalid_mvp_radar_projection,
    load_bound_mvp_radar_reader,
)
from assistant.semantic_retrieval import retrieval_decision_note, search_curated_semantic_items
from output.strategy_reviewer import build_strategy_review
from output.weekly_intelligence_brief import (
    RADAR_DISABLED_DISCLOSURE_RU,
)
from output.weekly_run_manifest import (
    WeeklyRunManifestError,
    load_manifest,
    validate_manifest,
    verify_file_checksum,
)


TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,}")
_INVALID_MANIFEST_MARKER = "_weekly_manifest_invalid"
_UNCONTAINED_MANIFEST_MARKER = "_weekly_manifest_uncontained"
_ISO_WEEK_SEARCH_RE = re.compile(r"(?<![0-9A-Z])([0-9]{4}-W(?:0[1-9]|[1-4][0-9]|5[0-3]))(?![0-9])")


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
        weekly_run_root: str | Path | None = None,
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
        self._weekly_run_root = (
            Path(weekly_run_root)
            if weekly_run_root is not None
            else (
                self._output_root / "weekly_intelligence_runs"
                if self._output_root is not None
                else PROJECT_ROOT / "data" / "output" / "weekly_intelligence_runs"
            )
        )
        self._now = now

    def get_current_week_label(self) -> dict:
        manifest_selection = self._select_weekly_manifest(None)
        if manifest_selection is not None:
            manifest, manifest_path = manifest_selection
            if manifest.get(_INVALID_MANIFEST_MARKER):
                identity = _manifest_identity(manifest, manifest_path)
                return {
                    "status": "invalid",
                    "week_label": str(
                        manifest.get("_candidate_reporting_week")
                        or manifest.get("reporting_week")
                        or self._current_week_label()
                    ),
                    "source": "weekly_run_manifest",
                    **identity,
                    "message": (
                        "The latest weekly run manifest is invalid; older runs and "
                        "legacy artifacts were not substituted."
                    ),
                }
            return {
                "status": "ok",
                "week_label": manifest["reporting_week"],
                "source": "weekly_run_manifest",
                "run_id": manifest["run_id"],
                "manifest_path": str(manifest_path),
                "run_status": manifest["run_status"],
                "partial": bool(manifest["partial"]),
                "pipeline_profile": manifest["pipeline_profile"],
                "message": "Latest weekly run manifest found.",
            }
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
        embedded_mvp = workbook.get("mvp_radar") if isinstance(workbook.get("mvp_radar"), Mapping) else None
        manifest_selection = self._select_weekly_manifest(actual_week)
        mvp_authoritative = False
        if manifest_selection is not None:
            manifest, manifest_path = manifest_selection
            stages = manifest.get("stages") if isinstance(manifest.get("stages"), Mapping) else {}
            radar_stage = stages.get("radar")
            if isinstance(radar_stage, Mapping) and radar_stage.get("status") == "disabled":
                mvp_payload = {"reader_state": "disabled", "status": "intentionally_disabled"}
            elif not manifest.get(_INVALID_MANIFEST_MARKER):
                mvp_payload = self._load_manifest_radar_payload(
                    manifest, manifest_path, str(actual_week or "")
                )
                mvp_authoritative = mvp_payload is not None
            else:
                mvp_payload = None
        else:
            mvp_payload = _downgrade_unbound_mvp_payload(embedded_mvp, actual_week)
        artifact_status = self.get_artifact_status(actual_week)
        return {
            "status": "ok",
            "week_label": actual_week,
            "title": f"Weekly AI Intelligence Workbook {actual_week}" if actual_week else "Weekly AI Intelligence Workbook",
            "artifact_type": _clean_text(workbook.get("_artifact_kind") or workbook.get("artifact_type")) or "workbook",
            "generated_at": _clean_text(workbook.get("generated_at")) or None,
            "decision_brief": _decision_cards(workbook),
            "strong_signals": _strong_signals(workbook),
            "actions": _action_cards(workbook),
            "project_actions": _project_actions(workbook),
            "mvp_status": (
                _mvp_status(
                    mvp_payload,
                    actual_week,
                    authoritative=mvp_authoritative,
                )
                if mvp_payload
                else None
            ),
            "mvp_radar_gate": _mvp_gate_status(mvp_payload),
            "artifact_paths": _artifact_paths(workbook),
            "artifact_status": artifact_status,
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

    def get_idea_thread(self, slug: str, week_label: str | None = None) -> dict:
        clean_slug = str(slug or "").strip()
        if not clean_slug:
            return self._missing_idea_thread(clean_slug, "Idea thread slug is required.")
        manifest_selection = self._select_weekly_manifest(week_label)
        if manifest_selection is not None:
            detail = self._idea_thread_detail_from_manifest(
                clean_slug,
                *manifest_selection,
            )
        else:
            detail = self._idea_thread_detail_from_db(clean_slug) or self._idea_thread_detail_from_workbook(
                clean_slug,
                week_label=week_label,
            )
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

    def get_action_statuses(self, week_label: str | None = None) -> dict:
        workbook = self._load_workbook(week_label)
        if workbook is None:
            return {
                "status": "missing",
                "week_label": week_label,
                "items": [],
                "counts": summarize_action_statuses([]),
                "message": "Workbook JSON sidecar is missing.",
            }
        actual_week = _clean_text(workbook.get("week_label")) or week_label
        events: list[dict] = []
        with self._readonly_connection() as connection:
            if connection is not None and _table_exists(connection, "ai_report_feedback_events"):
                try:
                    events = fetch_ai_report_feedback(connection, week_label=actual_week, limit=200)
                except sqlite3.Error:
                    events = []
        items = build_action_status_projection(workbook, events)
        return {
            "status": "ok" if items else "empty",
            "week_label": actual_week,
            "items": items,
            "counts": summarize_action_statuses(items),
            "message": (
                "Action statuses loaded; missing feedback remains unknown."
                if items
                else "No workbook action cards are available."
            ),
        }

    def get_mvp_radar_status(self, week_label: str | None = None) -> dict:
        clean_week, manifest_selection = self._resolve_weekly_manifest_request(
            week_label
        )
        if manifest_selection is not None:
            manifest, manifest_path = manifest_selection
            identity = _manifest_identity(manifest, manifest_path)
            if manifest.get(_INVALID_MANIFEST_MARKER):
                return {
                    "status": "invalid",
                    "week_label": clean_week,
                    "candidate": None,
                    "dossier_status": None,
                    "recommendation": None,
                    "source_mix": None,
                    "missing_evidence": [],
                    "next_validation": [],
                    "matched_external_evidence_count": 0,
                    "matched_external_source_types": [],
                    "market_context_status": "context_only",
                    "mvp_radar_gate": _mvp_gate_status(None),
                    **identity,
                    "run_identity": identity,
                    "message": (
                        "The authoritative weekly run manifest is invalid; "
                        "older Radar artifacts were not substituted."
                    ),
                }
            radar_stage = manifest["stages"]["radar"]
            if radar_stage["status"] == "disabled":
                gate = _mvp_gate_status({"reader_state": "disabled", "status": "intentionally_disabled"})
                return {
                    "status": "disabled",
                    "week_label": clean_week,
                    "candidate": None,
                    "dossier_status": None,
                    "recommendation": None,
                    "source_mix": None,
                    "missing_evidence": [RADAR_DISABLED_DISCLOSURE_RU],
                    "next_validation": [],
                    "matched_external_evidence_count": 0,
                    "matched_external_source_types": [],
                    "market_context_status": "context_only",
                    "mvp_radar_gate": gate,
                    **identity,
                    "run_identity": identity,
                    "message": RADAR_DISABLED_DISCLOSURE_RU,
                }
            payload = (
                self._load_manifest_radar_payload(manifest, manifest_path, clean_week)
                if radar_stage["status"] == "succeeded"
                and manifest.get("run_status") in {"complete", "partial"}
                else None
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
                    "matched_external_evidence_count": 0,
                    "matched_external_source_types": [],
                    "market_context_status": "context_only",
                    "mvp_radar_gate": _mvp_gate_status(None),
                    **identity,
                    "run_identity": identity,
                    "message": (
                        "MVP Radar is not available in the authoritative weekly run; "
                        "legacy artifacts were not substituted."
                    ),
                }
            normalized = _mvp_status(payload, clean_week, authoritative=True)
            return {
                **normalized,
                "mvp_radar_gate": _mvp_gate_status(payload),
                **identity,
                "run_identity": identity,
                "status": "ok",
                "message": "MVP Radar status loaded from the authoritative weekly run.",
            }
        workbook = self._load_workbook(clean_week)
        payload = workbook.get("mvp_radar") if isinstance(workbook, Mapping) and isinstance(workbook.get("mvp_radar"), Mapping) else None
        payload = _downgrade_unbound_mvp_payload(payload, clean_week)
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
                "mvp_radar_gate": _mvp_gate_status(None),
                "message": "MVP Radar result is missing.",
            }
        normalized = _mvp_status(payload, clean_week)
        missing_result = normalized["candidate"] is None and normalized["dossier_status"] is None
        return {
            **normalized,
            "mvp_radar_gate": _mvp_gate_status(payload),
            "status": "missing" if missing_result else "ok",
            "message": "MVP Radar status loaded." if not missing_result else "MVP Radar result is insufficient.",
        }

    def get_artifact_status(self, week_label: str | None = None) -> dict:
        clean_week, manifest_selection = self._resolve_weekly_manifest_request(
            week_label
        )
        if manifest_selection is not None:
            return self._manifest_artifact_status(clean_week, *manifest_selection)
        current_week = self._current_week_label()
        brief_json, brief_html = self._split_artifact_paths(clean_week, "weekly_brief")
        atlas_json, atlas_html = self._split_artifact_paths(clean_week, "knowledge_atlas")
        mvp_payload = load_mvp_radar_status(
            clean_week,
            output_root=self._output_root,
            mvp_output_root=self._mvp_output_root,
            radar_output_root=self._radar_output_root,
        )
        mvp_path = Path(str(mvp_payload.get("source_path"))) if isinstance(mvp_payload, Mapping) and mvp_payload.get("source_path") else None
        weekly_brief = _artifact_descriptor(
            artifact_type="weekly_intelligence_brief",
            display_name="Weekly Brief",
            week_label=clean_week,
            current_week_label=current_week,
            json_path=brief_json,
            html_path=brief_html,
        )
        knowledge_atlas = _artifact_descriptor(
            artifact_type="knowledge_atlas",
            display_name="Knowledge Atlas",
            week_label=clean_week,
            current_week_label=current_week,
            json_path=atlas_json,
            html_path=atlas_html,
        )
        mvp_radar = _artifact_descriptor(
            artifact_type="mvp_radar",
            display_name="MVP Radar",
            week_label=clean_week,
            current_week_label=current_week,
            json_path=mvp_path,
            html_path=None,
            missing_message="MVP Radar artifact is missing; do not infer build/focused permission.",
        )
        mvp_gate = _mvp_gate_status(mvp_payload)
        if mvp_radar["status"] != "missing" and mvp_gate["decision"] == "do_not_build":
            mvp_radar["warning"] = mvp_gate["warning"]
        artifacts = [weekly_brief, knowledge_atlas, mvp_radar]
        status = "ok" if all(item["status"] == "current" for item in artifacts) else "partial"
        if all(item["status"] == "missing" for item in artifacts):
            status = "missing"
        return {
            "status": status,
            "week_label": clean_week,
            "current_week_label": current_week,
            "weekly_brief": weekly_brief,
            "knowledge_atlas": knowledge_atlas,
            "mvp_radar": mvp_radar,
            "mvp_radar_gate": mvp_gate,
            "artifact_paths": _artifact_status_paths(artifacts),
            "evidence_boundaries": _evidence_boundaries(mvp_gate),
            "message": _artifact_status_message(artifacts),
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

    def get_strategy_reviewer_notes(self, week_label: str | None = None) -> dict:
        clean_week = str(week_label or "").strip() or None
        with self._readonly_connection() as connection:
            if connection is None or not _table_exists(connection, "ai_report_feedback_events"):
                return _empty_strategy_review(clean_week, "missing", "AI report feedback table is missing.")
            try:
                review = build_strategy_review(
                    connection,
                    week_label=clean_week,
                    weekly_run_root=self._weekly_run_root,
                )
            except sqlite3.Error:
                return _empty_strategy_review(clean_week, "missing", "Strategy Reviewer notes could not be loaded.")
        suggestions = review.get("suggestions") if isinstance(review.get("suggestions"), Mapping) else {}
        return {
            "status": "ok",
            "week_label": clean_week,
            "generated_at": _clean_text(review.get("generated_at")) or None,
            "suggestions": {
                "keep": _string_values(suggestions.get("keep")),
                "change": _string_values(suggestions.get("change")),
                "demote": _string_values(suggestions.get("demote")),
                "test_next_week": _string_values(suggestions.get("test_next_week")),
            },
            "memory_only_updates": _string_values(review.get("memory_only_updates")),
            "approval_required": [dict(item) for item in review.get("approval_required") or [] if isinstance(item, Mapping)],
            "codex_tasks": [_codex_task(item) for item in review.get("codex_tasks") or [] if isinstance(item, Mapping)],
            "reaction_pattern_proposals": [
                dict(item)
                for item in review.get("reaction_pattern_proposals") or []
                if isinstance(item, Mapping)
            ],
            "risks": _string_values(review.get("risks")),
            "mutation_policy": dict(review.get("mutation_policy") or {}),
            "feedback_summary": dict(review.get("feedback_summary") or {}),
            "message": "Strategy Reviewer notes loaded.",
        }

    def list_marked_posts(self, week_label: str | None = None, limit: int = 20) -> dict:
        clean_week, manifest_selection = self._resolve_weekly_manifest_request(
            week_label
        )
        if manifest_selection is not None:
            workbook = self._load_manifest_workbook(*manifest_selection)
            if workbook is None:
                return {
                    "status": "missing",
                    "week_label": clean_week,
                    "items": [],
                    "message": (
                        "The authoritative weekly run Brief is unavailable or invalid; "
                        "live marked-post rows were not substituted."
                    ),
                }
            manifest_posts = workbook.get("marked_posts")
            if not isinstance(manifest_posts, list):
                return {
                    "status": "missing",
                    "week_label": clean_week,
                    "items": [],
                    "message": (
                        "The authoritative weekly run Brief has no valid marked-post snapshot; "
                        "live rows were not substituted."
                    ),
                }
            items = [
                _marked_post_item(post)
                for post in manifest_posts
                if isinstance(post, Mapping)
            ][: max(1, int(limit or 20))]
            return {
                "status": "ok" if items else "empty",
                "week_label": clean_week,
                "items": items,
                "message": (
                    "Marked posts loaded from the authoritative weekly run Brief."
                    if items
                    else "The authoritative weekly run contains no marked posts."
                ),
            }

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
        manifest_selection = self._select_weekly_manifest(clean_filters.get("week_label"))
        if manifest_selection is not None:
            items = self._manifest_retrieval_items(*manifest_selection)
        else:
            items = build_retrieval_items(
                self._settings,
                week_label=clean_filters.get("week_label"),
                output_root=self._output_root,
                visual_output_root=self._visual_output_root,
                ai_output_root=self._ai_output_root,
                mvp_output_root=self._mvp_output_root,
                radar_output_root=self._radar_output_root,
            )
        results = search_curated_semantic_items(items, query, filters=clean_filters, limit=limit)
        return {
            "status": "ok" if results else "empty",
            "query": str(query or ""),
            "filters": clean_filters,
            "retrieval_decision": retrieval_decision_note(),
            "items": results,
            "message": "Curated intelligence items matched deterministic+FTS search." if results else "No curated intelligence items matched.",
        }

    def _current_week_label(self) -> str:
        current = self._now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        year, week, _day = current.astimezone(timezone.utc).isocalendar()
        return f"{year}-W{week:02d}"

    def _load_workbook(self, week_label: str | None) -> dict | None:
        manifest_selection = self._select_weekly_manifest(week_label)
        if manifest_selection is not None:
            manifest, manifest_path = manifest_selection
            return self._load_manifest_workbook(manifest, manifest_path)
        return load_latest_workbook_json(
            self._settings,
            week_label,
            output_root=self._output_root,
            visual_output_root=self._visual_output_root,
            ai_output_root=self._ai_output_root,
        )

    def _resolve_weekly_manifest_request(
        self,
        week_label: str | None,
    ) -> tuple[str, tuple[dict[str, Any], Path] | None]:
        clean_week = str(week_label or "").strip()
        if clean_week:
            return clean_week, self._select_weekly_manifest(clean_week)
        selection = self._select_weekly_manifest(None)
        if selection is not None:
            manifest, _manifest_path = selection
            selected_week = str(
                manifest.get("_candidate_reporting_week")
                or manifest.get("reporting_week")
                or self._current_week_label()
            )
            return selected_week, selection
        return str(self.get_current_week_label()["week_label"]), None

    def _select_weekly_manifest(
        self,
        week_label: str | None,
    ) -> tuple[dict[str, Any], Path] | None:
        """Select one authoritative candidate without skipping invalid newer runs."""

        try:
            weekly_run_root = self._weekly_run_root.expanduser().resolve()
        except (OSError, RuntimeError):
            return None
        if not weekly_run_root.is_dir():
            return None
        clean_week = str(week_label or "").strip() or None
        candidates: list[
            tuple[tuple[int, str, str], dict[str, Any], Path, str | None, bool]
        ] = []
        for lexical_path in weekly_run_root.glob("*/manifest.json"):
            try:
                resolved_path = lexical_path.resolve()
            except (OSError, RuntimeError):
                resolved_path = lexical_path.absolute()
            if resolved_path.parent.parent != weekly_run_root:
                week_clues = _manifest_candidate_week_clues({}, lexical_path)
                candidate_week = _majority_week_clue(week_clues)
                if clean_week and candidate_week and clean_week != candidate_week:
                    continue
                payload = {
                    _INVALID_MANIFEST_MARKER: True,
                    _UNCONTAINED_MANIFEST_MARKER: True,
                    "_candidate_reporting_week": candidate_week or clean_week,
                    "_candidate_run_id": lexical_path.parent.name,
                }
                candidates.append(
                    (
                        (2**63 - 1, lexical_path.parent.name, str(lexical_path.absolute())),
                        payload,
                        lexical_path.absolute(),
                        candidate_week or clean_week,
                        True,
                    )
                )
                continue
            path = resolved_path
            parse_failed = False
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                loaded = None
                parse_failed = True
            if isinstance(loaded, Mapping):
                payload = dict(loaded)
            else:
                payload = {}
                parse_failed = True
            invalid_candidate = parse_failed
            if not invalid_candidate:
                try:
                    validate_manifest(payload)
                except (TypeError, ValueError):
                    invalid_candidate = True
            if invalid_candidate:
                # Invalid identity cannot be trusted as a single filter key. Keep
                # conflicting/unassignable candidates fail-closed for explicit reads.
                week_clues = _manifest_candidate_week_clues(payload, path)
                candidate_weeks = set(week_clues)
                candidate_week = _majority_week_clue(week_clues)
                reliable_other_week = (
                    len(week_clues) >= 2 and len(candidate_weeks) == 1
                )
                if (
                    clean_week
                    and clean_week not in candidate_weeks
                    and reliable_other_week
                ):
                    continue
            else:
                candidate_week = str(payload["reporting_week"])
                if clean_week and clean_week != candidate_week:
                    continue
            try:
                path_stat = path.stat()
                parent_stat = path.parent.stat()
                freshness_ns = max(
                    path_stat.st_mtime_ns,
                    path_stat.st_ctime_ns,
                    parent_stat.st_mtime_ns,
                    parent_stat.st_ctime_ns,
                )
            except OSError:
                filesystem_freshness_ns = 0
            else:
                filesystem_freshness_ns = freshness_ns
            freshness_ns = (
                # Preserve canonical run ordering for valid concurrent runs; use
                # filesystem evidence only when the manifest cannot authenticate it.
                filesystem_freshness_ns
                if invalid_candidate
                else _manifest_generated_at_ns(payload)
            )
            run_id = str(payload.get("run_id") or path.parent.name)
            key = (
                freshness_ns,
                run_id,
                str(path.resolve()),
            )
            candidates.append(
                (key, payload, path.resolve(), candidate_week, invalid_candidate)
            )
        if not candidates:
            return None
        _key, manifest, path, candidate_week, invalid_candidate = max(
            candidates,
            key=lambda item: item[0],
        )
        if invalid_candidate:
            manifest[_INVALID_MANIFEST_MARKER] = True
            manifest["_candidate_reporting_week"] = candidate_week or clean_week
            manifest["_candidate_run_id"] = str(
                manifest.get("run_id") or path.parent.name
            )
        return manifest, path

    def _load_manifest_workbook(
        self,
        manifest: Mapping[str, Any],
        manifest_path: Path,
    ) -> dict | None:
        return self._load_manifest_reader_sidecar(
            manifest,
            manifest_path,
            stage_name="weekly_brief",
            artifact_type="weekly_intelligence_brief",
        )

    def _load_manifest_reader_sidecar(
        self,
        manifest: Mapping[str, Any],
        manifest_path: Path,
        *,
        stage_name: str,
        artifact_type: str,
    ) -> dict | None:
        """Load only a fully identity-bound Brief/Atlas sidecar and its HTML pair."""

        if manifest.get(_INVALID_MANIFEST_MARKER):
            return None
        run_dir = manifest_path.parent.resolve()
        try:
            checked_manifest = load_manifest(
                manifest_path,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )
        except (OSError, UnicodeError, TypeError, ValueError, WeeklyRunManifestError):
            return None
        if checked_manifest.get("run_id") != manifest.get("run_id"):
            return None
        manifest = checked_manifest
        if manifest.get("run_status") not in {"complete", "partial"}:
            return None
        stage = manifest["stages"][stage_name]
        if stage.get("status") != "succeeded":
            return None
        json_path = _manifest_artifact_path(manifest_path, stage.get("json_path"))
        html_path = _manifest_artifact_path(manifest_path, stage.get("html_path"))
        if json_path is None or html_path is None or not json_path.is_file() or not html_path.is_file():
            return None
        checksums = stage.get("checksums") if isinstance(stage.get("checksums"), Mapping) else {}
        try:
            verify_file_checksum(json_path, str(checksums.get("json_path") or ""))
            verify_file_checksum(html_path, str(checksums.get("html_path") or ""))
        except (WeeklyRunManifestError, UnicodeError):
            return None
        payload = _read_json_metadata(json_path)
        if not payload or payload.get("artifact_type") != artifact_type:
            return None
        if not isinstance(payload.get("partial"), bool):
            return None
        expected_identity = {
            "run_id": manifest.get("run_id"),
            "run_date": manifest.get("run_date"),
            "generated_at": manifest.get("generated_at"),
            "reporting_week": manifest.get("reporting_week"),
            "week_label": manifest.get("week_label"),
            "period_mode": manifest.get("period_mode"),
            "analysis_period_start": manifest.get("analysis_period_start"),
            "analysis_period_end": manifest.get("analysis_period_end"),
            "pipeline_profile": manifest.get("pipeline_profile"),
            "run_status": manifest.get("run_status"),
            "partial": manifest.get("partial"),
            "manifest_path": str(manifest_path.resolve()),
            "failed_stages": list(manifest.get("failed_stages") or []),
            "warnings": list(manifest.get("warnings") or []),
        }
        if any(payload.get(field) != value for field, value in expected_identity.items()):
            return None
        if not _path_identity_matches(payload.get("json_path"), json_path):
            return None
        if not _path_identity_matches(payload.get("html_path"), html_path):
            return None
        artifact_paths = payload.get("artifact_paths")
        if not isinstance(artifact_paths, Mapping):
            return None
        if not _path_identity_matches(artifact_paths.get("json"), json_path):
            return None
        if not _path_identity_matches(artifact_paths.get("html"), html_path):
            return None
        payload["_artifact_kind"] = artifact_type
        payload["_artifact_paths"] = {
            "json": str(json_path),
            "html": str(html_path),
        }
        return payload

    def _load_manifest_radar_payload(
        self,
        manifest: Mapping[str, Any],
        manifest_path: Path,
        week_label: str,
    ) -> dict | None:
        """Validate and load the immutable raw Radar artifact, never Brief-embedded data."""

        run_dir = manifest_path.parent.resolve()
        try:
            checked = load_manifest(
                manifest_path,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )
        except (WeeklyRunManifestError, UnicodeError):
            return None
        if checked.get("run_id") != manifest.get("run_id"):
            return None
        payload = load_bound_mvp_radar_reader(
            checked,
            path_base=run_dir,
            allowed_roots=(run_dir,),
        )
        if (
            payload.get("reader_state") not in {"available", "no_candidate"}
            or payload.get("reporting_week") != week_label
        ):
            return None
        return payload

    def _manifest_retrieval_items(
        self,
        manifest: Mapping[str, Any],
        manifest_path: Path,
    ) -> list:
        sidecars = [
            self._load_manifest_reader_sidecar(
                manifest,
                manifest_path,
                stage_name="weekly_brief",
                artifact_type="weekly_intelligence_brief",
            ),
            self._load_manifest_reader_sidecar(
                manifest,
                manifest_path,
                stage_name="knowledge_atlas",
                artifact_type="knowledge_atlas",
            ),
        ]
        return _dedupe_items(
            item
            for sidecar in sidecars
            if sidecar is not None
            for item in _items_from_workbook(sidecar)
        )

    def _manifest_artifact_status(
        self,
        clean_week: str,
        manifest: Mapping[str, Any],
        manifest_path: Path,
    ) -> dict:
        if manifest.get(_INVALID_MANIFEST_MARKER):
            return self._invalid_manifest_artifact_status(
                clean_week,
                manifest,
                manifest_path,
            )
        current_week = self._current_week_label()
        run_status = str(manifest.get("run_status") or "running")
        terminal_reader_run = run_status in {"complete", "partial"}
        validated_reader_sidecars = {
            "weekly_brief": self._load_manifest_reader_sidecar(
                manifest,
                manifest_path,
                stage_name="weekly_brief",
                artifact_type="weekly_intelligence_brief",
            ),
            "knowledge_atlas": self._load_manifest_reader_sidecar(
                manifest,
                manifest_path,
                stage_name="knowledge_atlas",
                artifact_type="knowledge_atlas",
            ),
        }
        radar_payload = (
            self._load_manifest_radar_payload(manifest, manifest_path, clean_week)
            if terminal_reader_run and manifest["stages"]["radar"]["status"] == "succeeded"
            else None
        )

        def stage_descriptor(
            stage_name: str,
            *,
            artifact_type: str,
            display_name: str,
            json_key: str,
            html_key: str | None,
            missing_message: str | None = None,
        ) -> dict:
            stage = manifest["stages"][stage_name]
            stage_status = str(stage.get("status") or "pending")
            json_path = _manifest_artifact_path(manifest_path, stage.get(json_key))
            html_path = (
                _manifest_artifact_path(manifest_path, stage.get(html_key))
                if html_key is not None
                else None
            )
            if stage_status == "disabled":
                authoritative = "disabled"
                message = RADAR_DISABLED_DISCLOSURE_RU
            elif stage_status in {"failed", "skipped_dependency", "cancelled"}:
                authoritative = "failed"
                message = missing_message or f"{display_name} failed in this weekly run."
            elif stage_status == "succeeded" and terminal_reader_run:
                artifact_is_valid = (
                    validated_reader_sidecars.get(stage_name) is not None
                    if stage_name in validated_reader_sidecars
                    else radar_payload is not None
                )
                if artifact_is_valid:
                    authoritative = "current"
                    message = f"{display_name} is bound to finalized run {manifest['run_id']}."
                else:
                    authoritative = "missing"
                    message = (
                        f"{display_name} failed authoritative identity, checksum, or file validation "
                        f"for run {manifest['run_id']}."
                    )
            else:
                authoritative = "pending"
                message = f"{display_name} is not finalized in run {manifest['run_id']}."
            return _artifact_descriptor(
                artifact_type=artifact_type,
                display_name=display_name,
                week_label=clean_week,
                current_week_label=current_week,
                json_path=json_path,
                html_path=html_path,
                missing_message=missing_message,
                authoritative_status=authoritative,
                authoritative_message=message,
            )

        weekly_brief = stage_descriptor(
            "weekly_brief",
            artifact_type="weekly_intelligence_brief",
            display_name="Weekly Brief",
            json_key="json_path",
            html_key="html_path",
        )
        knowledge_atlas = stage_descriptor(
            "knowledge_atlas",
            artifact_type="knowledge_atlas",
            display_name="Knowledge Atlas",
            json_key="json_path",
            html_key="html_path",
        )
        mvp_radar = stage_descriptor(
            "radar",
            artifact_type="mvp_radar",
            display_name="MVP Radar",
            json_key="artifact_path",
            html_key=None,
            missing_message="MVP Radar is unavailable in this run; do not infer build/focused permission.",
        )
        mvp_payload = radar_payload
        if mvp_radar["status"] == "disabled":
            mvp_payload = {"reader_state": "disabled", "status": "intentionally_disabled"}
        mvp_gate = _mvp_gate_status(mvp_payload)
        if mvp_radar["status"] not in {"missing", "failed", "disabled", "pending"} and mvp_gate["decision"] == "do_not_build":
            mvp_radar["warning"] = mvp_gate["warning"]
        artifacts = [weekly_brief, knowledge_atlas, mvp_radar]
        identity = _manifest_identity(manifest, manifest_path)
        return {
            "status": "ok" if run_status == "complete" else run_status,
            "week_label": clean_week,
            "current_week_label": current_week,
            **identity,
            "run_identity": identity,
            "weekly_brief": weekly_brief,
            "knowledge_atlas": knowledge_atlas,
            "mvp_radar": mvp_radar,
            "mvp_radar_gate": mvp_gate,
            "artifact_paths": _artifact_status_paths(artifacts),
            "evidence_boundaries": _evidence_boundaries(mvp_gate),
            "message": _artifact_status_message(artifacts),
        }

    def _invalid_manifest_artifact_status(
        self,
        clean_week: str,
        manifest: Mapping[str, Any],
        manifest_path: Path,
    ) -> dict:
        current_week = self._current_week_label()
        message = (
            "The latest weekly run manifest is invalid; older runs and legacy "
            "artifacts were not substituted."
        )
        artifacts = [
            _artifact_descriptor(
                artifact_type=artifact_type,
                display_name=display_name,
                week_label=clean_week,
                current_week_label=current_week,
                json_path=None,
                html_path=None,
                authoritative_status="invalid",
                authoritative_message=message,
            )
            for artifact_type, display_name in (
                ("weekly_intelligence_brief", "Weekly Brief"),
                ("knowledge_atlas", "Knowledge Atlas"),
                ("mvp_radar", "MVP Radar"),
            )
        ]
        weekly_brief, knowledge_atlas, mvp_radar = artifacts
        mvp_gate = _mvp_gate_status(None)
        identity = _manifest_identity(manifest, manifest_path)
        return {
            "status": "invalid",
            "week_label": clean_week,
            "current_week_label": current_week,
            **identity,
            "run_identity": identity,
            "weekly_brief": weekly_brief,
            "knowledge_atlas": knowledge_atlas,
            "mvp_radar": mvp_radar,
            "mvp_radar_gate": mvp_gate,
            "artifact_paths": _artifact_status_paths(artifacts),
            "evidence_boundaries": _evidence_boundaries(mvp_gate),
            "message": message,
        }

    def _split_artifact_paths(self, week_label: str, artifact_type: str) -> tuple[Path, Path]:
        if self._output_root is None:
            atlas_dir = DEFAULT_KNOWLEDGE_ATLAS_OUTPUT_DIR
            brief_dir = DEFAULT_WEEKLY_BRIEF_OUTPUT_DIR
        else:
            atlas_dir = self._output_root / "knowledge_atlas"
            brief_dir = self._output_root / "weekly_intelligence_briefs"
        if artifact_type == "knowledge_atlas":
            return (
                atlas_dir / f"{week_label}.knowledge-atlas.json",
                atlas_dir / f"{week_label}.knowledge-atlas.html",
            )
        return (
            brief_dir / f"{week_label}.weekly-brief.json",
            brief_dir / f"{week_label}.weekly-brief.html",
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
        manifest_selection = self._select_weekly_manifest(week_label)
        if manifest_selection is not None:
            manifest, manifest_path = manifest_selection
            sidecars = [
                self._load_manifest_reader_sidecar(
                    manifest,
                    manifest_path,
                    stage_name="knowledge_atlas",
                    artifact_type="knowledge_atlas",
                ),
                self._load_manifest_reader_sidecar(
                    manifest,
                    manifest_path,
                    stage_name="weekly_brief",
                    artifact_type="weekly_intelligence_brief",
                ),
            ]
            combined: list[dict] = []
            seen: set[str] = set()
            for sidecar in sidecars:
                for thread in _idea_threads_from_workbook(sidecar or {}):
                    slug = str(thread.get("slug") or "").strip()
                    if not slug or slug in seen:
                        continue
                    seen.add(slug)
                    combined.append(thread)
            return combined
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

    def _idea_thread_detail_from_manifest(
        self,
        slug: str,
        manifest: Mapping[str, Any],
        manifest_path: Path,
    ) -> dict | None:
        for stage_name, artifact_type in (
            ("knowledge_atlas", "knowledge_atlas"),
            ("weekly_brief", "weekly_intelligence_brief"),
        ):
            workbook = self._load_manifest_reader_sidecar(
                manifest,
                manifest_path,
                stage_name=stage_name,
                artifact_type=artifact_type,
            )
            detail = _idea_thread_detail_from_payload(workbook or {}, slug)
            if detail is not None:
                return detail
        return None

    def _idea_thread_detail_from_workbook(
        self,
        slug: str,
        *,
        week_label: str | None = None,
    ) -> dict | None:
        workbook = self._load_workbook(week_label)
        return _idea_thread_detail_from_payload(workbook or {}, slug)

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
            "artifact_type": None,
            "generated_at": None,
            "decision_brief": None,
            "strong_signals": [],
            "actions": [],
            "project_actions": [],
            "mvp_status": None,
            "mvp_radar_gate": _mvp_gate_status(None),
            "artifact_paths": {"html": None, "json": None},
            "artifact_status": None,
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
    if cards:
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
    contract = workbook.get("intelligence_contract") if isinstance(workbook.get("intelligence_contract"), Mapping) else {}
    canonical_claims = [claim for claim in contract.get("claims") or [] if isinstance(claim, Mapping)]
    return [
        {
            "id": claim.get("id"),
            "claim": claim.get("statement"),
            "summary": " ".join(_string_values(claim.get("uncertainty_reasons"))),
            "source_refs": list(claim.get("source_observation_ids") or []),
            "atom_ids": list(claim.get("atom_ids") or []),
            "evidence_tier": "decision_grade" if claim.get("decision_grade") is True else "insufficient_evidence",
            "verification_status": claim.get("verification_state"),
            "confidence": claim.get("confidence_band"),
        }
        for claim in canonical_claims
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
            "why_selected": card.get("why_selected"),
            "ranking_factors": [dict(item) for item in card.get("ranking_factors") or [] if isinstance(item, Mapping)],
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


def _mvp_status(
    payload: Mapping[str, Any] | None,
    week_label: str | None,
    *,
    authoritative: bool = False,
) -> dict:
    payload = payload or {}
    raw_candidate = _clean_text(
        payload.get("selected_candidate")
        or payload.get("selected_title")
        or payload.get("title")
    ) or None
    raw_dossier_status = _clean_text(payload.get("dossier_status")) or None
    raw_recommendation = _clean_text(payload.get("recommendation")) or None
    raw_reader_state = _clean_text(payload.get("reader_state")) or "unbound_legacy"
    strict_available = (
        authoritative
        and payload.get("schema_version") == "mvp_radar_reader.v1"
        and raw_reader_state == "available"
    )
    strict_no_candidate = (
        authoritative
        and payload.get("schema_version") == "mvp_radar_reader.v1"
        and raw_reader_state == "no_candidate"
    )
    reader_state = (
        raw_reader_state
        if strict_available
        or strict_no_candidate
        or raw_reader_state not in {"available", "no_candidate"}
        else "unbound_legacy"
    )
    proof = (
        _object_list(payload.get("matched_external_proof"))
        if strict_available
        else []
    )
    return {
        "status": (
            "ok"
            if strict_available
            else "no_candidate" if strict_no_candidate else reader_state
        ),
        "week_label": week_label,
        "reader_state": reader_state,
        "diagnostic_reader_state": (
            raw_reader_state if reader_state != raw_reader_state else ""
        ),
        "reader_decision": (
            _clean_text(payload.get("reader_decision")) or "unavailable"
            if strict_available
            else "unavailable"
        ),
        "candidate": raw_candidate if strict_available else None,
        "dossier_status": raw_dossier_status if strict_available else None,
        "recommendation": raw_recommendation if strict_available else None,
        "diagnostic_legacy_candidate": (
            raw_candidate if not strict_available and not strict_no_candidate else None
        ),
        "diagnostic_legacy_dossier_status": (
            raw_dossier_status
            if not strict_available and not strict_no_candidate
            else None
        ),
        "diagnostic_legacy_recommendation": (
            raw_recommendation
            if not strict_available and not strict_no_candidate
            else None
        ),
        "source_mix": (
            dict(payload.get("source_mix") or {})
            if strict_available and isinstance(payload.get("source_mix"), Mapping)
            else None
        ),
        "missing_evidence": _string_values(payload.get("missing_evidence")),
        "next_validation": _string_values(payload.get("next_validation")),
        "matched_external_evidence_count": len(proof),
        "matched_external_source_types": _matched_external_source_types(proof),
        "diagnostic_external_evidence_count": (
            len(_object_list(payload.get("matched_external_evidence")))
            if not strict_available
            else 0
        ),
        "market_context_status": (
            _market_context_status(payload) if strict_available else "context_only"
        ),
        "message": "",
    }


def _downgrade_unbound_mvp_payload(
    payload: Mapping[str, Any] | None, week_label: str | None
) -> dict | None:
    if not isinstance(payload, Mapping):
        return None
    expected_week = str(week_label or "")
    try:
        return adapt_legacy_mvp_radar_payload(
            payload,
            source_path=None,
            expected_week=expected_week,
        )
    except MvpRadarReaderError as exc:
        return invalid_mvp_radar_projection(
            expected_week,
            reason=f"MVP Radar JSON недействителен: {exc}",
        )


def _mvp_gate_status(payload: Mapping[str, Any] | None) -> dict:
    if not isinstance(payload, Mapping) or not payload:
        return {
            "decision": "do_not_build",
            "decision_label": "Do not build yet.",
            "radar_artifact_status": "missing",
            "matched_gate_evidence_count": 0,
            "matched_external_evidence_count": 0,
            "matched_external_source_types": [],
            "market_context_status": "context_only",
            "context_only_can_satisfy_gate": False,
            "matched_external_evidence_required": True,
            "warning": "MVP Radar artifact is missing; do not infer build/focused permission.",
        }
    reader_state = _clean_text(payload.get("reader_state")) or "unbound_legacy"
    if reader_state == "disabled":
        return {
            "decision": "do_not_build",
            "decision_label": "Do not build yet.",
            "radar_artifact_status": "disabled",
            "matched_gate_evidence_count": 0,
            "matched_external_evidence_count": 0,
            "matched_external_source_types": [],
            "market_context_status": "context_only",
            "context_only_can_satisfy_gate": False,
            "matched_external_evidence_required": True,
            "warning": RADAR_DISABLED_DISCLOSURE_RU,
        }
    matches = _object_list(payload.get("matched_external_evidence"))
    strict_authority = (
        payload.get("schema_version") == "mvp_radar_reader.v1"
        and reader_state == "available"
    )
    gate_matches = (
        [
            match
            for match in _object_list(payload.get("matched_external_proof"))
            if _strict_mvp_gate_match(match)
        ]
        if strict_authority
        else []
    )
    reader_decision = _clean_text(payload.get("reader_decision")) or "unavailable"
    dossier_status = _clean_text(payload.get("dossier_status"))
    source_types = _matched_external_source_types(gate_matches)
    source_mix = payload.get("source_mix") if isinstance(payload.get("source_mix"), Mapping) else {}
    proof_ready = len(gate_matches) >= 2 and len(source_types) >= 2
    kir_ready = source_mix.get("kir_required") is not True or source_mix.get("kir_gate_status") == "passed"
    artifact_status = "loaded" if reader_state in {"available", "no_candidate"} else reader_state
    if reader_decision == "build_allowed" and proof_ready and kir_ready:
        decision = "build_allowed"
        decision_label = "Radar allows the bounded build decision."
    elif (
        reader_decision == "investigate"
        and dossier_status == "focused_experiment"
        and proof_ready
        and kir_ready
    ):
        decision = "focused_experiment_allowed"
        decision_label = "Radar allows only a focused validation experiment."
    else:
        decision = "do_not_build"
        decision_label = "Do not build yet."
    if reader_state not in {"available", "no_candidate"}:
        warning = _clean_text(payload.get("decision_reason_ru")) or (
            "MVP Radar is not manifest-bound; do not infer build/focused permission."
        )
    else:
        warning = _clean_text(payload.get("decision_reason_ru")) or (
            "The strict same-run Radar projection controls this decision."
        )
    return {
        "decision": decision,
        "decision_label": decision_label,
        "radar_artifact_status": artifact_status,
        "matched_gate_evidence_count": len(gate_matches),
        "matched_external_evidence_count": len(matches),
        "matched_external_source_types": source_types,
        "market_context_status": _market_context_status(payload),
        "context_only_can_satisfy_gate": False,
        "matched_external_evidence_required": True,
        "warning": warning,
    }


def _strict_mvp_gate_match(match: Mapping[str, Any]) -> bool:
    return (
        match.get("gate_eligible") is True
        and match.get("supports_gate") is True
        and match.get("decision_grade") is True
        and match.get("context_only") is False
        and match.get("build_ready_evidence") is True
        and match.get("negative_signal") is False
    )


def _object_list(value: object) -> list[dict]:
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _matched_external_source_types(matches: Iterable[Mapping[str, Any]]) -> list[str]:
    return _unique(
        _clean_text(match.get("source_type"))
        for match in matches
        if _clean_text(match.get("source_type"))
    )


def _market_context_status(payload: Mapping[str, Any]) -> str:
    decision_context = payload.get("decision_context") if isinstance(payload.get("decision_context"), Mapping) else {}
    market_context = decision_context.get("market_context") if isinstance(decision_context.get("market_context"), Mapping) else {}
    return _clean_text(market_context.get("status")) or "context_only"


def _artifact_descriptor(
    *,
    artifact_type: str,
    display_name: str,
    week_label: str,
    current_week_label: str,
    json_path: Path | None,
    html_path: Path | None,
    missing_message: str | None = None,
    authoritative_status: str | None = None,
    authoritative_message: str | None = None,
) -> dict:
    generated_at = None
    json_exists = bool(json_path and json_path.exists())
    html_exists = bool(html_path and html_path.exists()) if html_path is not None else False
    if json_exists and json_path is not None:
        metadata = _read_json_metadata(json_path)
        generated_at = _clean_text(metadata.get("generated_at")) or None
    if authoritative_status == "current" and not json_exists:
        status = "missing"
        message = missing_message or f"{display_name} manifest path is missing."
    elif authoritative_status is not None:
        status = authoritative_status
        message = authoritative_message or f"{display_name}: {authoritative_status}."
    elif not json_exists:
        status = "missing"
        message = missing_message or f"{display_name} artifact is missing."
    elif week_label != current_week_label:
        status = "stale"
        message = f"{display_name} exists for {week_label}, but current week is {current_week_label}."
    else:
        status = "current"
        message = f"{display_name} is current for {week_label}."
    return {
        "artifact_type": artifact_type,
        "display_name": display_name,
        "week_label": week_label,
        "status": status,
        "generated_at": generated_at,
        "json_path": str(json_path) if json_path else None,
        "html_path": str(html_path) if html_path else None,
        "json_exists": json_exists,
        "html_exists": html_exists,
        "artifact_paths": {
            "json": str(json_path) if json_exists and json_path else None,
            "html": str(html_path) if html_exists and html_path else None,
        },
        "message": message,
    }


def _manifest_candidate_week_clues(
    manifest: Mapping[str, Any],
    manifest_path: Path,
) -> list[str]:
    clues: list[str] = []
    for field in ("reporting_week", "week_label"):
        value = manifest.get(field)
        if isinstance(value, str) and _ISO_WEEK_SEARCH_RE.fullmatch(value):
            clues.append(value)
    start_week = _week_clue_from_timestamp(manifest.get("analysis_period_start"))
    if start_week:
        clues.append(start_week)
    end_week = _week_clue_from_timestamp(
        manifest.get("analysis_period_end"),
        exclusive_end=True,
    )
    if end_week:
        clues.append(end_week)
    path_match = _ISO_WEEK_SEARCH_RE.search(manifest_path.parent.name)
    if path_match:
        clues.append(path_match.group(1))
    return clues


def _majority_week_clue(clues: Iterable[str]) -> str | None:
    values = list(clues)
    if not values:
        return None
    first_index = {value: values.index(value) for value in set(values)}
    return max(
        first_index,
        key=lambda value: (values.count(value), -first_index[value]),
    )


def _week_clue_from_timestamp(
    value: object,
    *,
    exclusive_end: bool = False,
) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        instant = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if instant.tzinfo is None:
        return None
    utc_instant = instant.astimezone(timezone.utc)
    if exclusive_end:
        utc_instant -= timedelta(microseconds=1)
    year, week, _weekday = utc_instant.isocalendar()
    return f"{year}-W{week:02d}"


def _manifest_generated_at_ns(manifest: Mapping[str, Any]) -> int:
    value = str(manifest["generated_at"])
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    instant = datetime.fromisoformat(normalized).astimezone(timezone.utc)
    delta = instant - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (
        (delta.days * 86_400 + delta.seconds) * 1_000_000
        + delta.microseconds
    ) * 1_000


def _manifest_identity(manifest: Mapping[str, Any], manifest_path: Path) -> dict[str, Any]:
    invalid = bool(manifest.get(_INVALID_MANIFEST_MARKER))
    return {
        "run_id": str(
            manifest.get("_candidate_run_id")
            or manifest.get("run_id")
            or manifest_path.parent.name
        ),
        "manifest_path": str(
            manifest_path.absolute()
            if manifest.get(_UNCONTAINED_MANIFEST_MARKER)
            else manifest_path.resolve()
        ),
        "run_status": "invalid" if invalid else str(manifest.get("run_status") or ""),
        "partial": bool(manifest.get("partial")),
        "pipeline_profile": str(manifest.get("pipeline_profile") or ""),
    }


def _manifest_artifact_path(manifest_path: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    run_dir = manifest_path.parent.resolve()
    candidate = Path(value)
    resolved = candidate.resolve() if candidate.is_absolute() else (run_dir / candidate).resolve()
    try:
        resolved.relative_to(run_dir)
    except ValueError:
        return None
    return resolved


def _path_identity_matches(value: object, expected: Path) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        return Path(value).resolve() == expected.resolve()
    except OSError:
        return False


def _read_json_metadata(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _artifact_status_paths(artifacts: Iterable[Mapping[str, Any]]) -> dict:
    paths: dict[str, str] = {}
    for artifact in artifacts:
        artifact_type = _clean_text(artifact.get("artifact_type"))
        artifact_paths = artifact.get("artifact_paths") if isinstance(artifact.get("artifact_paths"), Mapping) else {}
        for key, value in artifact_paths.items():
            clean = _clean_text(value)
            if clean:
                paths[f"{artifact_type}_{key}"] = clean
    return paths


def _artifact_status_message(artifacts: Iterable[Mapping[str, Any]]) -> str:
    parts = []
    for artifact in artifacts:
        detail = _clean_text(artifact.get("warning") or artifact.get("message"))
        suffix = (
            f" ({detail})"
            if artifact.get("status") in {"missing", "stale", "failed", "disabled", "pending"}
            and detail
            else ""
        )
        parts.append(f"{artifact.get('display_name')}: {artifact.get('status')}{suffix}")
    return "; ".join(parts)


def _evidence_boundaries(mvp_gate: Mapping[str, Any]) -> dict:
    return {
        "facts": "Use source-backed workbook/atom/Radar fields only.",
        "interpretation": "Hermes may summarize curated fields but must label uncertainty.",
        "model_background": "Model knowledge can explain terms only; it is not evidence.",
        "market_context": "context_only",
        "matched_external_evidence": (
            "available_for_gate"
            if int(mvp_gate.get("matched_gate_evidence_count") or 0) > 0
            else "missing_for_gate"
        ),
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


def _empty_strategy_review(week_label: str | None, status: str, message: str) -> dict:
    return {
        "status": status,
        "week_label": week_label,
        "generated_at": None,
        "suggestions": {"keep": [], "change": [], "demote": [], "test_next_week": []},
        "memory_only_updates": [],
        "approval_required": [],
        "codex_tasks": [],
        "reaction_pattern_proposals": [],
        "risks": [],
        "mutation_policy": {
            "source_code": "do_not_modify",
            "prompts": "do_not_modify",
            "thresholds": "do_not_modify",
            "profile": "do_not_modify",
            "projects": "do_not_modify",
        },
        "feedback_summary": {},
        "message": message,
    }


def _codex_task(task: Mapping[str, Any]) -> dict:
    return {
        "title": task.get("title"),
        "rationale": task.get("rationale"),
        "files": _string_values(task.get("files")),
        "acceptance_criteria": _string_values(task.get("acceptance_criteria")),
        "verification_commands": _string_values(task.get("verification_commands")),
        "requires_approval": bool(task.get("requires_approval", True)),
        "mutation_policy": _clean_text(task.get("mutation_policy")) or "suggestion_only_no_auto_edit",
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
    navigation = workbook.get("thread_navigation")
    navigation_threads = (
        navigation.get("threads")
        if isinstance(navigation, Mapping) and isinstance(navigation.get("threads"), list)
        else []
    )
    for item in navigation_threads:
        if not isinstance(item, Mapping):
            continue
        evidence_items = [
            evidence
            for evidence in item.get("evidence_items") or []
            if isinstance(evidence, Mapping)
        ]
        result.append(
            {
                "slug": item.get("slug"),
                "title": item.get("title") or item.get("slug"),
                "summary": item.get("current_understanding"),
                "status": item.get("status"),
                "momentum": item.get("momentum_30d"),
                "last_seen_at": item.get("last_seen_at"),
                "claims": list(item.get("claims") or []),
                "source_atom_ids": _unique(
                    [
                        *list(item.get("atom_ids") or []),
                        *[
                            evidence.get("atom_id")
                            for evidence in evidence_items
                            if evidence.get("atom_id") not in (None, "")
                        ],
                    ]
                ),
                "source_urls": _unique(
                    [
                        *_string_values(item.get("source_urls")),
                        *[
                            source_url
                            for evidence in evidence_items
                            for source_url in _string_values(evidence.get("source_urls"))
                        ],
                    ]
                ),
            }
        )
    for item in workbook.get("compressed_context") or []:
        if not isinstance(item, Mapping):
            continue
        if item.get("slug") and any(existing.get("slug") == item.get("slug") for existing in result):
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


def _idea_thread_detail_from_payload(workbook: Mapping[str, Any], slug: str) -> dict | None:
    for thread in _idea_threads_from_workbook(workbook):
        if thread.get("slug") != slug:
            continue
        return {
            "title": thread.get("title"),
            "summary": thread.get("summary"),
            "claims": [
                {
                    "claim": claim,
                    "atom_id": None,
                    "evidence_quote": None,
                    "source_urls": [],
                }
                for claim in thread.get("claims") or []
            ],
            "source_atom_ids": list(thread.get("source_atom_ids") or []),
            "source_urls": list(thread.get("source_urls") or []),
            "timeline": [],
        }
    return None


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
