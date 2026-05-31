import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


EXTRACTION_VERSION = "deterministic-claim-v1"
LINK_EXTRACTOR_VERSION = "deterministic-link-v1"
NARRATIVE_EXTRACTOR_VERSION = "deterministic-narrative-v1"
PROJECTS_YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "projects.yaml"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _cursor_rows(cursor: sqlite3.Cursor) -> list[dict]:
    columns = [description[0] for description in cursor.description or []]
    return [dict(row) if isinstance(row, sqlite3.Row) else dict(zip(columns, row)) for row in cursor.fetchall()]


def _week_label_from_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    iso_year, iso_week, _ = parsed.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _split_group_concat(value: str | None) -> list[str]:
    if not value:
        return []
    return [item for item in str(value).split(",") if item]


def _project_names_from_matches(value: str | None) -> list[str]:
    names: list[str] = []
    for item in _parse_json_list(value):
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("project") or item.get("project_name")
            if name:
                names.append(str(name))
    return names


def _scope_key(project_name: str | None = None, topic_label: str | None = None) -> str:
    parts = []
    if project_name:
        parts.append(f"project:{project_name}")
    if topic_label:
        parts.append(f"topic:{topic_label}")
    return "|".join(parts) if parts else "global"


def _matches_scope(
    *,
    project_name: str | None,
    topic_label: str | None,
    project_names: list[str],
    topic_labels: list[str],
) -> bool:
    if project_name and project_name not in project_names:
        return False
    if topic_label and topic_label not in topic_labels:
        return False
    return True


def _normalize_claim_text(text: str) -> str:
    compact = " ".join(str(text or "").split())
    first_sentence = re.split(r"(?<=[.!?])\s+", compact, maxsplit=1)[0]
    normalized = re.sub(r"[^0-9a-zA-Zа-яА-ЯёЁ]+", " ", first_sentence.casefold())
    return " ".join(normalized.split())


def _claim_key(normalized_claim: str) -> str:
    digest = hashlib.sha256(normalized_claim.encode("utf-8")).hexdigest()[:24]
    return f"claim:{digest}"


def _stable_key(prefix: str, *parts: str | None) -> str:
    clean = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _classify_claim(occurrence_count: int, channel_count: int) -> tuple[str, str, str]:
    if occurrence_count < 2:
        return "single_occurrence", "weak", "weak"
    if channel_count >= 2:
        return "cross_channel_repeated", "repeated", "strong"
    return "same_channel_repeated", "repeated", "moderate"


def _fetch_scoped_evidence(
    connection: sqlite3.Connection,
    *,
    week_label: str | None = None,
    project_name: str | None = None,
    topic_label: str | None = None,
    limit: int = 500,
) -> list[dict]:
    clauses = []
    params: list[Any] = []
    if week_label:
        clauses.append("week_label = ?")
        params.append(week_label)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor = connection.execute(
        f"""
        SELECT id, post_id, week_label, excerpt_text, source_channel, message_url,
               posted_at, topic_labels_json, project_names_json
        FROM signal_evidence_items
        {where_sql}
        ORDER BY posted_at ASC, id ASC
        LIMIT ?
        """,
        (*params, max(1, int(limit or 500))),
    )
    columns = [description[0] for description in cursor.description or []]
    rows = cursor.fetchall()

    evidence_rows: list[dict] = []
    for row in rows:
        item = dict(row) if isinstance(row, sqlite3.Row) else dict(zip(columns, row))
        project_names = [str(value) for value in _parse_json_list(item.get("project_names_json"))]
        topic_labels = [str(value) for value in _parse_json_list(item.get("topic_labels_json"))]
        if project_name and project_name not in project_names:
            continue
        if topic_label and topic_label not in topic_labels:
            continue
        item["project_names"] = project_names
        item["topic_labels"] = topic_labels
        evidence_rows.append(item)
    return evidence_rows


def refresh_repeated_claims(
    connection: sqlite3.Connection,
    *,
    week_label: str | None = None,
    project_name: str | None = None,
    topic_label: str | None = None,
    extraction_version: str = EXTRACTION_VERSION,
    limit: int = 500,
) -> dict:
    evidence_rows = _fetch_scoped_evidence(
        connection,
        week_label=week_label,
        project_name=project_name,
        topic_label=topic_label,
        limit=limit,
    )
    grouped: dict[str, list[dict]] = {}
    normalized_text_by_key: dict[str, str] = {}

    for row in evidence_rows:
        normalized = _normalize_claim_text(str(row.get("excerpt_text") or ""))
        if not normalized:
            continue
        key = _claim_key(normalized)
        grouped.setdefault(key, []).append(row)
        normalized_text_by_key[key] = normalized

    now = _now_iso()
    refreshed_claim_ids: list[int] = []
    occurrence_rows = 0
    weak_claims = 0
    repeated_claims = 0

    for key, occurrences in grouped.items():
        channels = sorted({str(row.get("source_channel") or "") for row in occurrences if row.get("source_channel")})
        weeks = sorted({str(row.get("week_label") or "") for row in occurrences if row.get("week_label")})
        evidence_ids = [int(row["id"]) for row in occurrences]
        projects = sorted({
            project
            for row in occurrences
            for project in row.get("project_names", [])
            if project
        })
        topics = sorted({
            topic
            for row in occurrences
            for topic in row.get("topic_labels", [])
            if topic
        })
        claim_type, status, evidence_strength = _classify_claim(len(occurrences), len(channels))
        if status == "weak":
            weak_claims += 1
        else:
            repeated_claims += 1

        cursor = connection.execute(
            """
            INSERT INTO channel_repeated_claims (
                claim_key,
                normalized_claim,
                claim_type,
                status,
                evidence_strength,
                first_seen_week,
                last_seen_week,
                occurrence_count,
                channel_count,
                project_name,
                topic_label,
                entity_labels_json,
                evidence_item_ids_json,
                refresh_scope_json,
                extraction_version,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(claim_key) DO UPDATE SET
                normalized_claim = excluded.normalized_claim,
                claim_type = excluded.claim_type,
                status = excluded.status,
                evidence_strength = excluded.evidence_strength,
                first_seen_week = excluded.first_seen_week,
                last_seen_week = excluded.last_seen_week,
                occurrence_count = excluded.occurrence_count,
                channel_count = excluded.channel_count,
                project_name = excluded.project_name,
                topic_label = excluded.topic_label,
                evidence_item_ids_json = excluded.evidence_item_ids_json,
                refresh_scope_json = excluded.refresh_scope_json,
                extraction_version = excluded.extraction_version,
                updated_at = excluded.updated_at
            """,
            (
                key,
                normalized_text_by_key[key],
                claim_type,
                status,
                evidence_strength,
                weeks[0] if weeks else None,
                weeks[-1] if weeks else None,
                len(occurrences),
                len(channels),
                project_name or (projects[0] if len(projects) == 1 else None),
                topic_label or (topics[0] if len(topics) == 1 else None),
                "[]",
                json.dumps(evidence_ids, ensure_ascii=False),
                json.dumps(
                    {
                        "week_label": week_label,
                        "project_name": project_name,
                        "topic_label": topic_label,
                        "source_channels": channels,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                extraction_version,
                now,
                now,
            ),
        )
        claim_row = None
        if not cursor.lastrowid:
            claim_row = connection.execute(
                "SELECT id FROM channel_repeated_claims WHERE claim_key = ?",
                (key,),
            ).fetchone()
        claim_id = int(cursor.lastrowid or (claim_row["id"] if isinstance(claim_row, sqlite3.Row) else claim_row[0]))
        refreshed_claim_ids.append(claim_id)
        connection.execute(
            "DELETE FROM claim_occurrences WHERE claim_id = ? AND extraction_version = ?",
            (claim_id, extraction_version),
        )
        for occurrence in occurrences:
            connection.execute(
                """
                INSERT INTO claim_occurrences (
                    claim_id,
                    post_id,
                    signal_evidence_item_id,
                    week_label,
                    source_channel,
                    message_url,
                    posted_at,
                    occurrence_text,
                    extraction_reason,
                    project_name,
                    topic_label,
                    extraction_version,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    occurrence.get("post_id"),
                    occurrence.get("id"),
                    occurrence.get("week_label"),
                    occurrence.get("source_channel"),
                    occurrence.get("message_url"),
                    occurrence.get("posted_at"),
                    occurrence.get("excerpt_text"),
                    "deterministic normalized excerpt match",
                    project_name or (occurrence.get("project_names") or [None])[0],
                    topic_label or (occurrence.get("topic_labels") or [None])[0],
                    extraction_version,
                    now,
                ),
            )
            occurrence_rows += 1

    connection.commit()
    return {
        "evidence_rows": len(evidence_rows),
        "claim_count": len(grouped),
        "repeated_claims": repeated_claims,
        "weak_claims": weak_claims,
        "occurrence_rows": occurrence_rows,
        "claim_ids": refreshed_claim_ids,
    }


def _blank_observation(
    *,
    channel_username: str,
    week_label: str,
    scope_key: str,
    project_name: str | None,
    topic_label: str | None,
) -> dict:
    return {
        "channel_username": channel_username,
        "week_label": week_label,
        "scope_key": scope_key,
        "project_name": project_name,
        "topic_label": topic_label,
        "window_start": None,
        "window_end": None,
        "post_ids": set(),
        "scored_post_ids": set(),
        "evidence_ids": set(),
        "cited_evidence_ids": set(),
        "acted_post_ids": set(),
        "skipped_post_ids": set(),
        "rejected_post_ids": set(),
        "low_signal_post_ids": set(),
        "repeated_claim_ids": set(),
        "usefulness_log_ids": set(),
        "bucket_counts": {},
        "feedback_counts": {},
        "decision_counts": {},
        "tag_counts": {},
        "usefulness_counts": {"gaining_trust": 0, "losing_trust": 0},
    }


def _touch_window(observation: dict, timestamp: str | None) -> None:
    if not timestamp:
        return
    if observation["window_start"] is None or timestamp < observation["window_start"]:
        observation["window_start"] = timestamp
    if observation["window_end"] is None or timestamp > observation["window_end"]:
        observation["window_end"] = timestamp


def _increment(counter: dict, key: str | None) -> None:
    clean_key = str(key or "unknown")
    counter[clean_key] = int(counter.get(clean_key, 0)) + 1


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_curated_project_names() -> set[str]:
    try:
        data = yaml.safe_load(PROJECTS_YAML_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return set()
    projects = data.get("projects", [])
    return {
        str(project.get("name"))
        for project in projects
        if isinstance(project, dict) and project.get("name")
    }


def _active_project_names(connection: sqlite3.Connection) -> set[str]:
    curated_names = _load_curated_project_names()
    rows = _cursor_rows(
        connection.execute(
            """
            SELECT name
            FROM projects
            WHERE active = 1
            """
        )
    )
    db_names = {str(row["name"]) for row in rows if row.get("name")}
    if curated_names:
        return curated_names if not db_names else curated_names & db_names
    return db_names


def _observation_for(
    observations: dict[tuple[str, str, str], dict],
    *,
    channel_username: str,
    week_label: str,
    scope_key: str,
    project_name: str | None,
    topic_label: str | None,
) -> dict:
    key = (channel_username, week_label, scope_key)
    if key not in observations:
        observations[key] = _blank_observation(
            channel_username=channel_username,
            week_label=week_label,
            scope_key=scope_key,
            project_name=project_name,
            topic_label=topic_label,
        )
    return observations[key]


def _fetch_scoped_posts(
    connection: sqlite3.Connection,
    *,
    week_label: str | None,
    project_name: str | None,
    topic_label: str | None,
    limit: int,
) -> list[dict]:
    rows = _cursor_rows(
        connection.execute(
            """
            SELECT p.id,
                   p.channel_username,
                   p.posted_at,
                   p.bucket,
                   p.signal_score,
                   p.scored_at,
                   p.project_matches,
                   GROUP_CONCAT(DISTINCT pr.name) AS project_link_names,
                   GROUP_CONCAT(DISTINCT t.label) AS topic_labels
            FROM posts p
            LEFT JOIN post_project_links ppl ON ppl.post_id = p.id
            LEFT JOIN projects pr ON pr.id = ppl.project_id
            LEFT JOIN post_topics pt ON pt.post_id = p.id
            LEFT JOIN topics t ON t.id = pt.topic_id
            GROUP BY p.id
            ORDER BY p.posted_at ASC, p.id ASC
            LIMIT ?
            """,
            (max(1, int(limit or 1000)),),
        )
    )
    scoped = []
    for row in rows:
        row_week = _week_label_from_iso(row.get("posted_at"))
        if week_label and row_week != week_label:
            continue
        project_names = sorted(
            {
                *_project_names_from_matches(row.get("project_matches")),
                *_split_group_concat(row.get("project_link_names")),
            }
        )
        topic_labels = sorted(set(_split_group_concat(row.get("topic_labels"))))
        if not _matches_scope(
            project_name=project_name,
            topic_label=topic_label,
            project_names=project_names,
            topic_labels=topic_labels,
        ):
            continue
        row["week_label"] = row_week
        row["project_names"] = project_names
        row["topic_labels"] = topic_labels
        scoped.append(row)
    return scoped


def _apply_feedback_inputs(
    connection: sqlite3.Connection,
    observations: dict[tuple[str, str, str], dict],
    post_context: dict[int, dict],
    *,
    scope_key: str,
    project_name: str | None,
    topic_label: str | None,
) -> None:
    for row in _cursor_rows(
        connection.execute(
            """
            SELECT sf.id, sf.post_id, sf.feedback, sf.recorded_at
            FROM signal_feedback sf
            ORDER BY sf.recorded_at ASC, sf.id ASC
            """
        )
    ):
        post_id = _safe_int(row.get("post_id"))
        context = post_context.get(post_id) if post_id is not None else None
        if not context:
            continue
        observation = _observation_for(
            observations,
            channel_username=context["channel_username"],
            week_label=context["week_label"],
            scope_key=scope_key,
            project_name=project_name,
            topic_label=topic_label,
        )
        feedback = str(row.get("feedback") or "")
        _increment(observation["feedback_counts"], feedback)
        if feedback == "acted_on":
            observation["acted_post_ids"].add(post_id)
        elif feedback == "skipped":
            observation["skipped_post_ids"].add(post_id)
        elif feedback == "marked_important":
            observation["usefulness_log_ids"].add(f"feedback:{row.get('id')}")
        _touch_window(observation, row.get("recorded_at"))


def _apply_tag_inputs(
    connection: sqlite3.Connection,
    observations: dict[tuple[str, str, str], dict],
    post_context: dict[int, dict],
    *,
    scope_key: str,
    project_name: str | None,
    topic_label: str | None,
) -> None:
    for row in _cursor_rows(
        connection.execute(
            """
            SELECT id, post_id, tag, recorded_at
            FROM user_post_tags
            ORDER BY recorded_at ASC, id ASC
            """
        )
    ):
        post_id = _safe_int(row.get("post_id"))
        context = post_context.get(post_id) if post_id is not None else None
        if not context:
            continue
        observation = _observation_for(
            observations,
            channel_username=context["channel_username"],
            week_label=context["week_label"],
            scope_key=scope_key,
            project_name=project_name,
            topic_label=topic_label,
        )
        tag = str(row.get("tag") or "")
        _increment(observation["tag_counts"], tag)
        if tag == "low_signal":
            observation["low_signal_post_ids"].add(post_id)
        elif tag in {"strong", "interesting", "try_in_project"}:
            observation["usefulness_log_ids"].add(f"tag:{row.get('id')}")
        _touch_window(observation, row.get("recorded_at"))


def _apply_decision_inputs(
    connection: sqlite3.Connection,
    observations: dict[tuple[str, str, str], dict],
    post_context: dict[int, dict],
    *,
    scope_key: str,
    project_name: str | None,
    topic_label: str | None,
) -> None:
    for row in _cursor_rows(
        connection.execute(
            """
            SELECT id, subject_ref_type, subject_ref_id, status, recorded_at
            FROM decision_journal
            WHERE decision_scope = 'signal'
            ORDER BY recorded_at ASC, id ASC
            """
        )
    ):
        if str(row.get("subject_ref_type") or "") not in {"post", "post_id"}:
            continue
        post_id = _safe_int(row.get("subject_ref_id"))
        context = post_context.get(post_id) if post_id is not None else None
        if not context:
            continue
        observation = _observation_for(
            observations,
            channel_username=context["channel_username"],
            week_label=context["week_label"],
            scope_key=scope_key,
            project_name=project_name,
            topic_label=topic_label,
        )
        status = str(row.get("status") or "")
        _increment(observation["decision_counts"], status)
        if status == "acted_on":
            observation["acted_post_ids"].add(post_id)
        elif status in {"ignored", "deferred"}:
            observation["skipped_post_ids"].add(post_id)
        elif status == "rejected":
            observation["rejected_post_ids"].add(post_id)
        _touch_window(observation, row.get("recorded_at"))


def _apply_usefulness_inputs(
    connection: sqlite3.Connection,
    observations: dict[tuple[str, str, str], dict],
    *,
    week_label: str | None,
    scope_key: str,
    project_name: str | None,
    topic_label: str | None,
) -> None:
    rows = _cursor_rows(
        connection.execute(
            """
            SELECT id, week_label, channels_gaining_trust_json,
                   channels_losing_trust_json, recorded_at
            FROM weekly_usefulness_logs
            ORDER BY recorded_at ASC, id ASC
            """
        )
    )
    for row in rows:
        row_week = str(row.get("week_label") or "")
        if week_label and row_week != week_label:
            continue
        for channel in _parse_json_list(row.get("channels_gaining_trust_json")):
            observation = _observation_for(
                observations,
                channel_username=str(channel),
                week_label=row_week,
                scope_key=scope_key,
                project_name=project_name,
                topic_label=topic_label,
            )
            observation["usefulness_log_ids"].add(f"weekly_usefulness:{row.get('id')}")
            observation["usefulness_counts"]["gaining_trust"] += 1
            _touch_window(observation, row.get("recorded_at"))
        for channel in _parse_json_list(row.get("channels_losing_trust_json")):
            observation = _observation_for(
                observations,
                channel_username=str(channel),
                week_label=row_week,
                scope_key=scope_key,
                project_name=project_name,
                topic_label=topic_label,
            )
            observation["usefulness_counts"]["losing_trust"] += 1
            _touch_window(observation, row.get("recorded_at"))


def _apply_repeated_claim_inputs(
    connection: sqlite3.Connection,
    observations: dict[tuple[str, str, str], dict],
    *,
    week_label: str | None,
    scope_key: str,
    project_name: str | None,
    topic_label: str | None,
) -> None:
    rows = _cursor_rows(
        connection.execute(
            """
            SELECT co.claim_id, co.week_label, co.source_channel, co.posted_at,
                   co.project_name, co.topic_label,
                   crc.status
            FROM claim_occurrences co
            JOIN channel_repeated_claims crc ON crc.id = co.claim_id
            WHERE crc.status = 'repeated'
            ORDER BY co.week_label ASC, co.id ASC
            """
        )
    )
    for row in rows:
        row_week = str(row.get("week_label") or "")
        if week_label and row_week != week_label:
            continue
        if project_name and row.get("project_name") != project_name:
            continue
        if topic_label and row.get("topic_label") != topic_label:
            continue
        channel = str(row.get("source_channel") or "")
        if not channel:
            continue
        observation = _observation_for(
            observations,
            channel_username=channel,
            week_label=row_week,
            scope_key=scope_key,
            project_name=project_name,
            topic_label=topic_label,
        )
        observation["repeated_claim_ids"].add(int(row["claim_id"]))
        _touch_window(observation, row.get("posted_at"))


def refresh_source_observations(
    connection: sqlite3.Connection,
    *,
    week_label: str | None = None,
    project_name: str | None = None,
    topic_label: str | None = None,
    limit: int = 1000,
) -> dict:
    """Rebuild source observation counters from canonical local rows."""
    clean_scope_key = _scope_key(project_name=project_name, topic_label=topic_label)
    observations: dict[tuple[str, str, str], dict] = {}
    post_context: dict[int, dict] = {}
    post_rows = _fetch_scoped_posts(
        connection,
        week_label=week_label,
        project_name=project_name,
        topic_label=topic_label,
        limit=limit,
    )

    for row in post_rows:
        row_week = row.get("week_label")
        channel = str(row.get("channel_username") or "")
        post_id = _safe_int(row.get("id"))
        if not channel or not row_week or post_id is None:
            continue
        context = {
            "channel_username": channel,
            "week_label": row_week,
            "project_names": row.get("project_names") or [],
            "topic_labels": row.get("topic_labels") or [],
        }
        post_context[post_id] = context
        observation = _observation_for(
            observations,
            channel_username=channel,
            week_label=row_week,
            scope_key=clean_scope_key,
            project_name=project_name,
            topic_label=topic_label,
        )
        observation["post_ids"].add(post_id)
        if row.get("signal_score") is not None or row.get("bucket") or row.get("scored_at"):
            observation["scored_post_ids"].add(post_id)
        bucket = row.get("bucket")
        if bucket:
            _increment(observation["bucket_counts"], str(bucket))
        if bucket in {"noise", "low_signal"}:
            observation["low_signal_post_ids"].add(post_id)
        _touch_window(observation, row.get("posted_at"))

    evidence_rows = _fetch_scoped_evidence(
        connection,
        week_label=week_label,
        project_name=project_name,
        topic_label=topic_label,
        limit=limit,
    )
    for row in evidence_rows:
        row_week = str(row.get("week_label") or "")
        channel = str(row.get("source_channel") or "")
        evidence_id = _safe_int(row.get("id"))
        if not channel or not row_week or evidence_id is None:
            continue
        observation = _observation_for(
            observations,
            channel_username=channel,
            week_label=row_week,
            scope_key=clean_scope_key,
            project_name=project_name,
            topic_label=topic_label,
        )
        observation["evidence_ids"].add(evidence_id)
        if row.get("message_url"):
            observation["cited_evidence_ids"].add(evidence_id)
        _touch_window(observation, row.get("posted_at"))

    _apply_feedback_inputs(
        connection,
        observations,
        post_context,
        scope_key=clean_scope_key,
        project_name=project_name,
        topic_label=topic_label,
    )
    _apply_tag_inputs(
        connection,
        observations,
        post_context,
        scope_key=clean_scope_key,
        project_name=project_name,
        topic_label=topic_label,
    )
    _apply_decision_inputs(
        connection,
        observations,
        post_context,
        scope_key=clean_scope_key,
        project_name=project_name,
        topic_label=topic_label,
    )
    _apply_usefulness_inputs(
        connection,
        observations,
        week_label=week_label,
        scope_key=clean_scope_key,
        project_name=project_name,
        topic_label=topic_label,
    )
    _apply_repeated_claim_inputs(
        connection,
        observations,
        week_label=week_label,
        scope_key=clean_scope_key,
        project_name=project_name,
        topic_label=topic_label,
    )

    now = _now_iso()
    refreshed_ids: list[int] = []
    for observation in observations.values():
        counters_json = json.dumps(
            {
                "source_of_truth": [
                    "posts",
                    "signal_evidence_items",
                    "signal_feedback",
                    "user_post_tags",
                    "decision_journal",
                    "weekly_usefulness_logs",
                    "claim_occurrences",
                ],
                "post_ids": sorted(observation["post_ids"]),
                "scored_post_ids": sorted(observation["scored_post_ids"]),
                "evidence_ids": sorted(observation["evidence_ids"]),
                "cited_evidence_ids": sorted(observation["cited_evidence_ids"]),
                "acted_post_ids": sorted(observation["acted_post_ids"]),
                "skipped_post_ids": sorted(observation["skipped_post_ids"]),
                "rejected_post_ids": sorted(observation["rejected_post_ids"]),
                "low_signal_post_ids": sorted(observation["low_signal_post_ids"]),
                "repeated_claim_ids": sorted(observation["repeated_claim_ids"]),
                "usefulness_refs": sorted(observation["usefulness_log_ids"]),
                "bucket_counts": observation["bucket_counts"],
                "feedback_counts": observation["feedback_counts"],
                "decision_counts": observation["decision_counts"],
                "tag_counts": observation["tag_counts"],
                "usefulness_counts": observation["usefulness_counts"],
                "refresh_scope": {
                    "week_label": week_label,
                    "project_name": project_name,
                    "topic_label": topic_label,
                    "limit": limit,
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        cursor = connection.execute(
            """
            INSERT INTO source_observations (
                channel_username,
                week_label,
                scope_key,
                window_start,
                window_end,
                project_name,
                topic_label,
                post_count,
                scored_count,
                evidence_count,
                cited_count,
                acted_on_count,
                skipped_count,
                rejected_count,
                low_signal_count,
                repeated_claim_count,
                useful_count,
                counters_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_username, week_label, scope_key) DO UPDATE SET
                window_start = excluded.window_start,
                window_end = excluded.window_end,
                project_name = excluded.project_name,
                topic_label = excluded.topic_label,
                post_count = excluded.post_count,
                scored_count = excluded.scored_count,
                evidence_count = excluded.evidence_count,
                cited_count = excluded.cited_count,
                acted_on_count = excluded.acted_on_count,
                skipped_count = excluded.skipped_count,
                rejected_count = excluded.rejected_count,
                low_signal_count = excluded.low_signal_count,
                repeated_claim_count = excluded.repeated_claim_count,
                useful_count = excluded.useful_count,
                counters_json = excluded.counters_json,
                updated_at = excluded.updated_at
            """,
            (
                observation["channel_username"],
                observation["week_label"],
                observation["scope_key"],
                observation["window_start"],
                observation["window_end"],
                observation["project_name"],
                observation["topic_label"],
                len(observation["post_ids"]),
                len(observation["scored_post_ids"]),
                len(observation["evidence_ids"]),
                len(observation["cited_evidence_ids"]),
                len(observation["acted_post_ids"]),
                len(observation["skipped_post_ids"]),
                len(observation["rejected_post_ids"]),
                len(observation["low_signal_post_ids"]),
                len(observation["repeated_claim_ids"]),
                len(observation["usefulness_log_ids"]),
                counters_json,
                now,
                now,
            ),
        )
        observation_row = None
        if not cursor.lastrowid:
            observation_row = connection.execute(
                """
                SELECT id
                FROM source_observations
                WHERE channel_username = ? AND week_label = ? AND scope_key = ?
                """,
                (
                    observation["channel_username"],
                    observation["week_label"],
                    observation["scope_key"],
                ),
            ).fetchone()
        row_id = cursor.lastrowid or (
            observation_row["id"] if isinstance(observation_row, sqlite3.Row) else observation_row[0]
        )
        refreshed_ids.append(int(row_id))

    connection.commit()
    return {
        "source_observation_count": len(observations),
        "source_observation_ids": refreshed_ids,
        "post_rows": len(post_rows),
        "evidence_rows": len(evidence_rows),
        "scope_key": clean_scope_key,
    }


def _scoped_active_projects(
    row_project_names: list[str],
    *,
    active_project_names: set[str],
    project_name: str | None,
) -> list[str]:
    if project_name:
        return [project_name] if project_name in active_project_names and project_name in row_project_names else []
    return sorted({name for name in row_project_names if name in active_project_names})


def _upsert_entity_link(
    connection: sqlite3.Connection,
    *,
    entity_label: str,
    entity_type: str,
    linked_object_type: str,
    linked_object_id: str,
    project_name: str | None,
    topic_label: str | None,
    source_table: str,
    source_row_id: int | None,
    confidence: float,
    reason: str,
    extractor_version: str,
    week_label: str | None,
    created_at: str,
) -> int:
    connection.execute(
        """
        INSERT INTO intelligence_entity_links (
            entity_label,
            entity_type,
            linked_object_type,
            linked_object_id,
            project_name,
            topic_label,
            source_table,
            source_row_id,
            confidence,
            reason,
            extractor_version,
            week_label,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_label, entity_type, linked_object_type, linked_object_id, extractor_version)
        DO UPDATE SET
            project_name = excluded.project_name,
            topic_label = excluded.topic_label,
            source_table = excluded.source_table,
            source_row_id = excluded.source_row_id,
            confidence = excluded.confidence,
            reason = excluded.reason,
            week_label = excluded.week_label
        """,
        (
            entity_label,
            entity_type,
            linked_object_type,
            linked_object_id,
            project_name,
            topic_label,
            source_table,
            source_row_id,
            confidence,
            reason,
            extractor_version,
            week_label,
            created_at,
        ),
    )
    row = connection.execute(
        """
        SELECT id
        FROM intelligence_entity_links
        WHERE entity_label = ?
          AND entity_type = ?
          AND linked_object_type = ?
          AND linked_object_id = ?
          AND extractor_version = ?
        """,
        (entity_label, entity_type, linked_object_type, linked_object_id, extractor_version),
    ).fetchone()
    return int(row["id"] if isinstance(row, sqlite3.Row) else row[0])


def _upsert_project_link(
    connection: sqlite3.Connection,
    *,
    project_name: str,
    linked_object_type: str,
    linked_object_id: str,
    week_label: str | None,
    relevance_score: float,
    match_reason: str,
    evidence_item_ids: list[int],
    active_project: int,
    refresh_scope: dict,
    created_at: str,
) -> int:
    connection.execute(
        """
        INSERT INTO project_intelligence_links (
            project_name,
            linked_object_type,
            linked_object_id,
            week_label,
            relevance_score,
            match_reason,
            evidence_item_ids_json,
            active_project,
            refresh_scope_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_name, linked_object_type, linked_object_id, week_label)
        DO UPDATE SET
            relevance_score = excluded.relevance_score,
            match_reason = excluded.match_reason,
            evidence_item_ids_json = excluded.evidence_item_ids_json,
            active_project = excluded.active_project,
            refresh_scope_json = excluded.refresh_scope_json,
            updated_at = excluded.updated_at
        """,
        (
            project_name,
            linked_object_type,
            linked_object_id,
            week_label,
            relevance_score,
            match_reason,
            json.dumps(evidence_item_ids, ensure_ascii=False),
            active_project,
            json.dumps(refresh_scope, ensure_ascii=False, sort_keys=True),
            created_at,
            created_at,
        ),
    )
    row = connection.execute(
        """
        SELECT id
        FROM project_intelligence_links
        WHERE project_name = ?
          AND linked_object_type = ?
          AND linked_object_id = ?
          AND week_label IS ?
        """,
        (project_name, linked_object_type, linked_object_id, week_label),
    ).fetchone()
    return int(row["id"] if isinstance(row, sqlite3.Row) else row[0])


def _delete_previous_link_refresh(
    connection: sqlite3.Connection,
    *,
    week_label: str | None,
    project_name: str | None,
    topic_label: str | None,
    extractor_version: str,
) -> None:
    clauses = ["extractor_version = ?"]
    params: list[Any] = [extractor_version]
    if week_label:
        clauses.append("week_label = ?")
        params.append(week_label)
    if project_name:
        clauses.append("project_name = ?")
        params.append(project_name)
    if topic_label:
        clauses.append("topic_label = ?")
        params.append(topic_label)
    connection.execute(
        f"DELETE FROM intelligence_entity_links WHERE {' AND '.join(clauses)}",
        params,
    )

    project_clauses = ["refresh_scope_json LIKE ?"]
    project_params: list[Any] = [f"%{extractor_version}%"]
    if week_label:
        project_clauses.append("week_label = ?")
        project_params.append(week_label)
    if project_name:
        project_clauses.append("project_name = ?")
        project_params.append(project_name)
    connection.execute(
        f"DELETE FROM project_intelligence_links WHERE {' AND '.join(project_clauses)}",
        project_params,
    )


def refresh_intelligence_links(
    connection: sqlite3.Connection,
    *,
    week_label: str | None = None,
    project_name: str | None = None,
    topic_label: str | None = None,
    extractor_version: str = LINK_EXTRACTOR_VERSION,
    limit: int = 1000,
) -> dict:
    active_project_names = _active_project_names(connection)
    if project_name and project_name not in active_project_names:
        return {
            "entity_link_count": 0,
            "project_link_count": 0,
            "entity_link_ids": [],
            "project_link_ids": [],
            "active_project_names": sorted(active_project_names),
        }

    now = _now_iso()
    refresh_scope = {
        "week_label": week_label,
        "project_name": project_name,
        "topic_label": topic_label,
        "extractor_version": extractor_version,
        "limit": limit,
    }
    _delete_previous_link_refresh(
        connection,
        week_label=week_label,
        project_name=project_name,
        topic_label=topic_label,
        extractor_version=extractor_version,
    )

    entity_link_ids: set[int] = set()
    project_link_ids: set[int] = set()
    evidence_rows = _fetch_scoped_evidence(
        connection,
        week_label=week_label,
        project_name=project_name,
        topic_label=topic_label,
        limit=limit,
    )
    for row in evidence_rows:
        evidence_id = _safe_int(row.get("id"))
        if evidence_id is None:
            continue
        row_projects = _scoped_active_projects(
            row.get("project_names") or [],
            active_project_names=active_project_names,
            project_name=project_name,
        )
        for project in row_projects:
            project_entity_id = _upsert_entity_link(
                connection,
                entity_label=project,
                entity_type="project",
                linked_object_type="evidence",
                linked_object_id=str(evidence_id),
                project_name=project,
                topic_label=topic_label or ((row.get("topic_labels") or [None])[0]),
                source_table="signal_evidence_items",
                source_row_id=evidence_id,
                confidence=1.0,
                reason="project label from signal_evidence_items",
                extractor_version=extractor_version,
                week_label=row.get("week_label"),
                created_at=now,
            )
            entity_link_ids.add(project_entity_id)
            project_link_ids.add(
                _upsert_project_link(
                    connection,
                    project_name=project,
                    linked_object_type="entity",
                    linked_object_id=str(project_entity_id),
                    week_label=row.get("week_label"),
                    relevance_score=1.0,
                    match_reason="project entity link from scoped evidence",
                    evidence_item_ids=[evidence_id],
                    active_project=1,
                    refresh_scope=refresh_scope,
                    created_at=now,
                )
            )
            for topic in row.get("topic_labels") or []:
                topic_entity_id = _upsert_entity_link(
                    connection,
                    entity_label=topic,
                    entity_type="topic",
                    linked_object_type="evidence",
                    linked_object_id=str(evidence_id),
                    project_name=project,
                    topic_label=topic,
                    source_table="signal_evidence_items",
                    source_row_id=evidence_id,
                    confidence=1.0,
                    reason="topic label from signal_evidence_items",
                    extractor_version=extractor_version,
                    week_label=row.get("week_label"),
                    created_at=now,
                )
                entity_link_ids.add(topic_entity_id)
                project_link_ids.add(
                    _upsert_project_link(
                        connection,
                        project_name=project,
                        linked_object_type="entity",
                        linked_object_id=str(topic_entity_id),
                        week_label=row.get("week_label"),
                        relevance_score=0.9,
                        match_reason="topic entity link from scoped evidence",
                        evidence_item_ids=[evidence_id],
                        active_project=1,
                        refresh_scope=refresh_scope,
                        created_at=now,
                    )
                )

    claim_clauses = []
    claim_params: list[Any] = []
    if week_label:
        claim_clauses.append("(first_seen_week <= ? AND last_seen_week >= ?)")
        claim_params.extend([week_label, week_label])
    if project_name:
        claim_clauses.append("project_name = ?")
        claim_params.append(project_name)
    if topic_label:
        claim_clauses.append("topic_label = ?")
        claim_params.append(topic_label)
    claim_where = f"WHERE {' AND '.join(claim_clauses)}" if claim_clauses else ""
    claim_rows = _cursor_rows(
        connection.execute(
            f"""
            SELECT id, project_name, topic_label, evidence_item_ids_json,
                   first_seen_week, last_seen_week, status, evidence_strength
            FROM channel_repeated_claims
            {claim_where}
            ORDER BY id ASC
            LIMIT ?
            """,
            (*claim_params, max(1, int(limit or 1000))),
        )
    )
    for row in claim_rows:
        claim_project = str(row.get("project_name") or "")
        if not claim_project or claim_project not in active_project_names:
            continue
        claim_id = int(row["id"])
        claim_week = week_label or row.get("last_seen_week") or row.get("first_seen_week")
        evidence_ids = [int(value) for value in _parse_json_list(row.get("evidence_item_ids_json")) if _safe_int(value)]
        topic = row.get("topic_label")
        if topic:
            entity_link_ids.add(
                _upsert_entity_link(
                    connection,
                    entity_label=str(topic),
                    entity_type="topic",
                    linked_object_type="claim",
                    linked_object_id=str(claim_id),
                    project_name=claim_project,
                    topic_label=str(topic),
                    source_table="channel_repeated_claims",
                    source_row_id=claim_id,
                    confidence=0.85,
                    reason="topic label from repeated claim",
                    extractor_version=extractor_version,
                    week_label=claim_week,
                    created_at=now,
                )
            )
        project_link_ids.add(
            _upsert_project_link(
                connection,
                project_name=claim_project,
                linked_object_type="claim",
                linked_object_id=str(claim_id),
                week_label=claim_week,
                relevance_score=1.0 if row.get("status") == "repeated" else 0.5,
                match_reason="claim project scope from repeated-claim refresh",
                evidence_item_ids=evidence_ids,
                active_project=1,
                refresh_scope=refresh_scope,
                created_at=now,
            )
        )

    observation_clauses = []
    observation_params: list[Any] = []
    if week_label:
        observation_clauses.append("week_label = ?")
        observation_params.append(week_label)
    if project_name:
        observation_clauses.append("project_name = ?")
        observation_params.append(project_name)
    if topic_label:
        observation_clauses.append("topic_label = ?")
        observation_params.append(topic_label)
    observation_where = f"WHERE {' AND '.join(observation_clauses)}" if observation_clauses else ""
    observation_rows = _cursor_rows(
        connection.execute(
            f"""
            SELECT id, channel_username, week_label, project_name, topic_label,
                   evidence_count, acted_on_count, useful_count, repeated_claim_count,
                   low_signal_count, skipped_count, rejected_count
            FROM source_observations
            {observation_where}
            ORDER BY week_label ASC, id ASC
            LIMIT ?
            """,
            (*observation_params, max(1, int(limit or 1000))),
        )
    )
    for row in observation_rows:
        observation_project = str(row.get("project_name") or "")
        if not observation_project or observation_project not in active_project_names:
            continue
        positive = int(row.get("evidence_count") or 0) + int(row.get("acted_on_count") or 0) + int(row.get("useful_count") or 0)
        negative = int(row.get("low_signal_count") or 0) + int(row.get("skipped_count") or 0) + int(row.get("rejected_count") or 0)
        score = min(1.0, max(0.1, (positive + int(row.get("repeated_claim_count") or 0)) / max(1, positive + negative)))
        project_link_ids.add(
            _upsert_project_link(
                connection,
                project_name=observation_project,
                linked_object_type="source_observation",
                linked_object_id=str(row["id"]),
                week_label=row.get("week_label"),
                relevance_score=score,
                match_reason="source observation counters for active project scope",
                evidence_item_ids=[],
                active_project=1,
                refresh_scope=refresh_scope,
                created_at=now,
            )
        )

    connection.commit()
    return {
        "entity_link_count": len(entity_link_ids),
        "project_link_count": len(project_link_ids),
        "entity_link_ids": sorted(entity_link_ids),
        "project_link_ids": sorted(project_link_ids),
        "active_project_names": sorted(active_project_names),
    }


def _fetch_claim_occurrence_channels(
    connection: sqlite3.Connection,
    claim_ids: list[int],
) -> dict[int, set[str]]:
    if not claim_ids:
        return {}
    placeholders = ",".join("?" for _ in claim_ids)
    rows = _cursor_rows(
        connection.execute(
            f"""
            SELECT claim_id, source_channel
            FROM claim_occurrences
            WHERE claim_id IN ({placeholders})
            """,
            claim_ids,
        )
    )
    channels_by_claim: dict[int, set[str]] = {claim_id: set() for claim_id in claim_ids}
    for row in rows:
        claim_id = int(row["claim_id"])
        channel = str(row.get("source_channel") or "")
        if channel:
            channels_by_claim.setdefault(claim_id, set()).add(channel)
    return channels_by_claim


def _narrative_title(project_name: str, topic_label: str, week_label: str | None) -> str:
    if week_label:
        return f"{topic_label} signals for {project_name} in {week_label}"
    return f"{topic_label} signals for {project_name}"


def refresh_narrative_candidates(
    connection: sqlite3.Connection,
    *,
    week_label: str | None = None,
    project_name: str | None = None,
    topic_label: str | None = None,
    extractor_version: str = NARRATIVE_EXTRACTOR_VERSION,
    limit: int = 1000,
    max_evidence_items: int = 12,
    max_claims_per_narrative: int = 6,
    max_channels_per_narrative: int = 8,
) -> dict:
    active_project_names = _active_project_names(connection)
    if project_name and project_name not in active_project_names:
        return {
            "narrative_count": 0,
            "active_narratives": 0,
            "rejected_narratives": 0,
            "narrative_claim_links": 0,
            "narrative_ids": [],
        }

    clauses = ["status = 'repeated'", "project_name IS NOT NULL", "topic_label IS NOT NULL"]
    params: list[Any] = []
    if week_label:
        clauses.append("(first_seen_week <= ? AND last_seen_week >= ?)")
        params.extend([week_label, week_label])
    if project_name:
        clauses.append("project_name = ?")
        params.append(project_name)
    if topic_label:
        clauses.append("topic_label = ?")
        params.append(topic_label)
    rows = _cursor_rows(
        connection.execute(
            f"""
            SELECT id, project_name, topic_label, first_seen_week, last_seen_week,
                   occurrence_count, channel_count, evidence_item_ids_json,
                   evidence_strength
            FROM channel_repeated_claims
            WHERE {' AND '.join(clauses)}
            ORDER BY project_name ASC, topic_label ASC, id ASC
            LIMIT ?
            """,
            (*params, max(1, int(limit or 1000))),
        )
    )

    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        claim_project = str(row.get("project_name") or "")
        claim_topic = str(row.get("topic_label") or "")
        if claim_project not in active_project_names:
            continue
        narrative_week = week_label or str(row.get("last_seen_week") or row.get("first_seen_week") or "")
        if not claim_project or not claim_topic or not narrative_week:
            continue
        groups.setdefault((claim_project, claim_topic, narrative_week), []).append(row)

    now = _now_iso()
    narrative_ids: list[int] = []
    link_count = 0
    active_count = 0
    rejected_count = 0

    for (claim_project, claim_topic, narrative_week), claim_rows in groups.items():
        claim_ids = [int(row["id"]) for row in claim_rows]
        channels_by_claim = _fetch_claim_occurrence_channels(connection, claim_ids)
        evidence_ids = sorted(
            {
                int(value)
                for row in claim_rows
                for value in _parse_json_list(row.get("evidence_item_ids_json"))
                if _safe_int(value)
            }
        )
        source_channels = sorted({channel for channels in channels_by_claim.values() for channel in channels})
        first_seen_values = sorted(str(row.get("first_seen_week") or "") for row in claim_rows if row.get("first_seen_week"))
        last_seen_values = sorted(str(row.get("last_seen_week") or "") for row in claim_rows if row.get("last_seen_week"))
        over_aggregated = (
            len(evidence_ids) > max_evidence_items
            or len(claim_rows) > max_claims_per_narrative
            or len(source_channels) > max_channels_per_narrative
        )
        insufficient_evidence = len(evidence_ids) < 2
        status = "rejected" if over_aggregated or insufficient_evidence else "active"
        if status == "active":
            active_count += 1
        else:
            rejected_count += 1
        narrative_key = _stable_key(
            "narrative",
            extractor_version,
            claim_project,
            claim_topic,
            narrative_week,
        )
        refresh_scope = {
            "week_label": week_label,
            "project_name": project_name,
            "topic_label": topic_label,
            "extractor_version": extractor_version,
            "claim_ids": claim_ids,
            "over_aggregated": over_aggregated,
            "insufficient_evidence": insufficient_evidence,
            "max_evidence_items": max_evidence_items,
            "max_claims_per_narrative": max_claims_per_narrative,
            "max_channels_per_narrative": max_channels_per_narrative,
        }
        connection.execute(
            """
            INSERT INTO channel_narratives (
                narrative_key,
                title,
                summary,
                status,
                project_name,
                topic_label,
                first_seen_week,
                last_seen_week,
                supporting_post_count,
                supporting_channel_count,
                linked_claim_count,
                evidence_item_ids_json,
                source_channels_json,
                refresh_scope_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(narrative_key) DO UPDATE SET
                title = excluded.title,
                summary = excluded.summary,
                status = excluded.status,
                project_name = excluded.project_name,
                topic_label = excluded.topic_label,
                first_seen_week = excluded.first_seen_week,
                last_seen_week = excluded.last_seen_week,
                supporting_post_count = excluded.supporting_post_count,
                supporting_channel_count = excluded.supporting_channel_count,
                linked_claim_count = excluded.linked_claim_count,
                evidence_item_ids_json = excluded.evidence_item_ids_json,
                source_channels_json = excluded.source_channels_json,
                refresh_scope_json = excluded.refresh_scope_json,
                updated_at = excluded.updated_at
            """,
            (
                narrative_key,
                _narrative_title(claim_project, claim_topic, narrative_week),
                (
                    f"Deterministic candidate from {len(claim_rows)} repeated claims, "
                    f"{len(evidence_ids)} evidence rows, and {len(source_channels)} channels."
                ),
                status,
                claim_project,
                claim_topic,
                first_seen_values[0] if first_seen_values else narrative_week,
                last_seen_values[-1] if last_seen_values else narrative_week,
                len(evidence_ids),
                len(source_channels),
                len(claim_rows) if status == "active" else 0,
                json.dumps(evidence_ids, ensure_ascii=False),
                json.dumps(source_channels, ensure_ascii=False),
                json.dumps(refresh_scope, ensure_ascii=False, sort_keys=True),
                now,
                now,
            ),
        )
        narrative_row = connection.execute(
            "SELECT id FROM channel_narratives WHERE narrative_key = ?",
            (narrative_key,),
        ).fetchone()
        narrative_id = int(narrative_row["id"] if isinstance(narrative_row, sqlite3.Row) else narrative_row[0])
        narrative_ids.append(narrative_id)
        connection.execute("DELETE FROM narrative_claim_links WHERE narrative_id = ?", (narrative_id,))

        if status != "active":
            continue
        for row in claim_rows:
            claim_id = int(row["id"])
            claim_evidence_ids = {
                int(value)
                for value in _parse_json_list(row.get("evidence_item_ids_json"))
                if _safe_int(value)
            }
            shared_evidence_count = len(claim_evidence_ids & set(evidence_ids))
            connection.execute(
                """
                INSERT INTO narrative_claim_links (
                    narrative_id,
                    claim_id,
                    link_reason,
                    shared_evidence_count,
                    shared_entities_json,
                    confidence,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(narrative_id, claim_id) DO UPDATE SET
                    link_reason = excluded.link_reason,
                    shared_evidence_count = excluded.shared_evidence_count,
                    shared_entities_json = excluded.shared_entities_json,
                    confidence = excluded.confidence
                """,
                (
                    narrative_id,
                    claim_id,
                    "same active project and topic scope with supporting evidence rows",
                    shared_evidence_count,
                    json.dumps([claim_project, claim_topic], ensure_ascii=False),
                    min(1.0, 0.55 + (0.1 * shared_evidence_count)),
                    now,
                ),
            )
            link_count += 1
        _upsert_project_link(
            connection,
            project_name=claim_project,
            linked_object_type="narrative",
            linked_object_id=str(narrative_id),
            week_label=narrative_week,
            relevance_score=min(1.0, 0.5 + (0.05 * len(evidence_ids)) + (0.05 * len(claim_rows))),
            match_reason="narrative candidate from repeated claims in active project scope",
            evidence_item_ids=evidence_ids,
            active_project=1,
            refresh_scope=refresh_scope,
            created_at=now,
        )

    connection.commit()
    return {
        "narrative_count": len(groups),
        "active_narratives": active_count,
        "rejected_narratives": rejected_count,
        "narrative_claim_links": link_count,
        "narrative_ids": narrative_ids,
    }
