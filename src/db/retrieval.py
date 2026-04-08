import json
import logging
import sqlite3
from datetime import datetime, timedelta


LOGGER = logging.getLogger(__name__)


def _row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row | tuple) -> dict:
    columns = [description[0] for description in cursor.description or []]
    return dict(zip(columns, row))


def _fetchall_as_dicts(cursor: sqlite3.Cursor) -> list[dict]:
    rows = cursor.fetchall()
    return [_row_to_dict(cursor, row) for row in rows]


def _fetchone_as_dict(cursor: sqlite3.Cursor) -> dict | None:
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(cursor, row)


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _week_label_for(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def fetch_evidence_items(
    connection,
    *,
    project_name=None,
    week_label=None,
    week_range=None,
    source_channel=None,
    evidence_kind=None,
    exclude_statuses=None,
    limit=30,
) -> list[dict]:
    where_clauses: list[str] = []
    params: list[object] = []

    if project_name:
        where_clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM json_each(signal_evidence_items.project_names_json)
                WHERE json_each.value = ?
            )
            """
        )
        params.append(project_name)

    if week_label and week_range and len(week_range) == 2:
        where_clauses.append("(week_label = ? OR week_label BETWEEN ? AND ?)")
        params.extend([week_label, week_range[0], week_range[1]])
    elif week_label:
        where_clauses.append("week_label = ?")
        params.append(week_label)
    elif week_range and len(week_range) == 2:
        where_clauses.append("week_label BETWEEN ? AND ?")
        params.extend([week_range[0], week_range[1]])
    elif week_range:
        LOGGER.warning("Ignoring invalid week_range=%r", week_range)

    if source_channel:
        where_clauses.append("source_channel = ?")
        params.append(source_channel)

    if evidence_kind:
        where_clauses.append("evidence_kind = ?")
        params.append(evidence_kind)

    if exclude_statuses:
        status_values = [status for status in exclude_statuses if status]
        if status_values:
            placeholders = ",".join("?" * len(status_values))
            where_clauses.append(
                f"""
                NOT EXISTS (
                    SELECT 1
                    FROM decision_journal
                    WHERE decision_scope = 'signal'
                      AND subject_ref_id = CAST(signal_evidence_items.post_id AS TEXT)
                      AND status IN ({placeholders})
                )
                """
            )
            params.extend(status_values)

    query = "SELECT * FROM signal_evidence_items"
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    query += " ORDER BY posted_at DESC LIMIT ?"
    params.append(limit)

    cursor = connection.execute(query, params)
    items = _fetchall_as_dicts(cursor)

    item_ids = [item["id"] for item in items if item.get("id") is not None]
    if item_ids:
        placeholders = ",".join("?" * len(item_ids))
        connection.execute(
            f"""
            UPDATE signal_evidence_items
            SET last_used_at = ?
            WHERE id IN ({placeholders})
            """,
            [_now_iso(), *item_ids],
        )

    return items


def fetch_decisions(
    connection,
    *,
    project_name=None,
    decision_scope=None,
    status=None,
    subject_ref_type=None,
    limit=20,
) -> list[dict]:
    where_clauses: list[str] = []
    params: list[object] = []

    if project_name:
        where_clauses.append("project_name = ?")
        params.append(project_name)
    if decision_scope:
        where_clauses.append("decision_scope = ?")
        params.append(decision_scope)
    if status:
        where_clauses.append("status = ?")
        params.append(status)
    if subject_ref_type:
        where_clauses.append("subject_ref_type = ?")
        params.append(subject_ref_type)

    query = "SELECT * FROM decision_journal"
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    query += " ORDER BY recorded_at DESC LIMIT ?"
    params.append(limit)

    cursor = connection.execute(query, params)
    return _fetchall_as_dicts(cursor)


def fetch_suppression_context(connection, title_fingerprint: str) -> dict:
    rejection_cursor = connection.execute(
        """
        SELECT *
        FROM insight_rejection_memory
        WHERE title_fingerprint = ?
        """,
        (title_fingerprint,),
    )
    rejection_memory = _fetchone_as_dict(rejection_cursor)

    recent_decisions: list[dict] = []
    if rejection_memory is not None:
        title = rejection_memory.get("title")
        if title:
            triage_cursor = connection.execute(
                """
                SELECT id
                FROM insight_triage_records
                WHERE title = ?
                ORDER BY id DESC
                LIMIT 10
                """,
                (title,),
            )
            triage_ids = [str(row[0]) for row in triage_cursor.fetchall()]

            if triage_ids:
                placeholders = ",".join("?" * len(triage_ids))
                recent_cursor = connection.execute(
                    f"""
                    SELECT *
                    FROM decision_journal
                    WHERE decision_scope = 'insight'
                      AND status = 'rejected'
                      AND subject_ref_type = 'insight_triage_id'
                      AND subject_ref_id IN ({placeholders})
                    ORDER BY recorded_at DESC
                    LIMIT 5
                    """,
                    triage_ids,
                )
                recent_decisions = _fetchall_as_dicts(recent_cursor)

    return {
        "rejection_memory": rejection_memory,
        "recent_decisions": recent_decisions,
    }


def fetch_stale_snapshots(connection, weeks_threshold=2) -> list[dict]:
    cutoff_label = _week_label_for(datetime.utcnow() - timedelta(weeks=weeks_threshold))
    cursor = connection.execute(
        """
        SELECT *
        FROM project_context_snapshots
        WHERE snapshot_week_label IS NULL
           OR snapshot_week_label < ?
        ORDER BY updated_at ASC
        """,
        (cutoff_label,),
    )
    return _fetchall_as_dicts(cursor)


def fetch_project_snapshot(connection, project_name: str) -> dict | None:
    cursor = connection.execute(
        """
        SELECT *
        FROM project_context_snapshots
        WHERE project_name = ?
        """,
        (project_name,),
    )
    return _fetchone_as_dict(cursor)
