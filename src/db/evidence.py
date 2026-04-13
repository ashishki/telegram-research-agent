import json
import re
import sqlite3
from datetime import datetime, timezone


_QUALIFYING_TAGS = {"strong", "interesting", "try_in_project", "funny"}
_FEEDBACK_STATUS_MAP = {
    "acted_on": "acted_on",
    "skipped": "ignored",
    "marked_important": "acted_on",
}
_TRIAGE_STATUS_MAP = {
    "do_now": "acted_on",
    "backlog": "deferred",
    "reject_or_defer": "rejected",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _current_week_label() -> str:
    year, week, _ = datetime.now(timezone.utc).isocalendar()
    return f"{year}-W{week:02d}"


def _truncate(text: str | None, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip()


def _parse_project_names_json(raw_value: str | None) -> str:
    if not raw_value:
        return "[]"
    try:
        decoded = json.loads(raw_value)
    except (TypeError, ValueError):
        return "[]"
    if not isinstance(decoded, list):
        return "[]"

    project_names: list[str] = []
    for item in decoded:
        if isinstance(item, str):
            project_names.append(item)
            continue
        if isinstance(item, dict):
            name = item.get("project") or item.get("project_name") or item.get("name")
            if isinstance(name, str) and name.strip():
                project_names.append(name.strip())
    return json.dumps(project_names)


def _project_name_from_insight_title(title: str | None) -> str | None:
    if not title:
        return None
    match = re.match(r"\[(?:Implement|Build)\]\s+(.+?)\s+[—–-]\s+", str(title).strip(), re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def record_signal_evidence_for_scored_posts(
    connection: sqlite3.Connection,
    post_ids: list[int],
) -> None:
    if not post_ids:
        return

    placeholders = ",".join("?" * len(post_ids))
    rows = connection.execute(
        f"""
        SELECT p.id, p.raw_post_id, p.channel_username, p.content, p.posted_at, p.bucket,
               p.project_matches, r.message_url
        FROM posts p
        JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE p.id IN ({placeholders})
        """,
        post_ids,
    ).fetchall()

    week_label = _current_week_label()
    created_at = _now_iso()
    for row in rows:
        connection.execute(
            """
            INSERT OR IGNORE INTO signal_evidence_items (
                post_id,
                raw_post_id,
                week_label,
                evidence_kind,
                excerpt_text,
                source_channel,
                message_url,
                posted_at,
                topic_labels_json,
                project_names_json,
                selection_reason,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row[0],
                row[1],
                week_label,
                "strong_signal",
                _truncate(row[3], 500),
                row[2],
                row[7],
                row[4],
                "[]",
                _parse_project_names_json(row[6]),
                f"bucket={row[5]} (auto-scored)",
                created_at,
            ),
        )


def record_signal_evidence_for_manual_tag(
    connection: sqlite3.Connection,
    post_id: int,
    tag: str,
) -> None:
    if tag not in _QUALIFYING_TAGS:
        return

    row = connection.execute(
        """
        SELECT p.id, p.raw_post_id, p.channel_username, p.content, p.posted_at, r.message_url
        FROM posts p
        JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE p.id = ?
        """,
        (post_id,),
    ).fetchone()
    if row is None:
        return

    connection.execute(
        """
        INSERT OR IGNORE INTO signal_evidence_items (
            post_id,
            raw_post_id,
            week_label,
            evidence_kind,
            excerpt_text,
            source_channel,
            message_url,
            posted_at,
            topic_labels_json,
            project_names_json,
            selection_reason,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row[0],
            row[1],
            _current_week_label(),
            "manual_tag",
            _truncate(row[3], 500),
            row[2],
            row[5],
            row[4],
            "[]",
            "[]",
            f"user_tag={tag}",
            _now_iso(),
        ),
    )


def record_decision_for_feedback(
    connection: sqlite3.Connection,
    post_id: int,
    feedback: str,
) -> None:
    mapped_status = _FEEDBACK_STATUS_MAP.get(feedback)
    if mapped_status is None:
        return
    now_iso = _now_iso()

    connection.execute(
        """
        INSERT INTO decision_journal (
            decision_scope,
            subject_ref_type,
            subject_ref_id,
            status,
            reason,
            recorded_by,
            recorded_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "signal",
            "post_id",
            str(post_id),
            mapped_status,
            f"signal_feedback={feedback}",
            "user",
            now_iso,
        ),
    )


def record_decisions_for_triage(
    connection: sqlite3.Connection,
    week_label: str,
    insights: list[object],
) -> None:
    now_iso = _now_iso()
    for insight in insights:
        recommendation = getattr(insight, "recommendation", None)
        mapped_status = _TRIAGE_STATUS_MAP.get(recommendation)
        if mapped_status is None:
            continue

        title = getattr(insight, "title", "")
        reason = getattr(insight, "reason", None)
        triage_row = connection.execute(
            """
            SELECT id
            FROM insight_triage_records
            WHERE week_label = ? AND title = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (week_label, title),
        ).fetchone()
        if triage_row is None:
            subject_ref_id = f"week={week_label}:title={title[:80]}"
        else:
            subject_ref_id = str(triage_row[0])

        connection.execute(
            """
            INSERT INTO decision_journal (
                decision_scope,
                subject_ref_type,
                subject_ref_id,
                project_name,
                status,
                reason,
                recorded_by,
                recorded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "insight",
                "insight_triage_id",
                subject_ref_id,
                _project_name_from_insight_title(title),
                mapped_status,
                reason,
                "pipeline",
                now_iso,
            ),
        )


def record_study_completion_decision(
    connection: sqlite3.Connection,
    week_label: str,
) -> None:
    connection.execute(
        """
        INSERT INTO decision_journal (
            decision_scope,
            subject_ref_type,
            subject_ref_id,
            status,
            reason,
            recorded_by,
            recorded_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "study",
            "study_plan_week",
            week_label,
            "completed",
            f"study plan completed for {week_label}",
            "user",
            _now_iso(),
        ),
    )
