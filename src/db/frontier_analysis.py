import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_required(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _json_array(values: Iterable[object] | None) -> str:
    return json.dumps(list(values or []), ensure_ascii=False)


def _json_object(value: dict | None) -> str:
    return json.dumps(dict(value or {}), ensure_ascii=False, sort_keys=True)


def _parse_json(value: str | None, fallback):
    try:
        parsed = json.loads(value or "")
    except json.JSONDecodeError:
        return fallback
    return parsed


def _row_to_analysis(columns: list[str], row: sqlite3.Row | tuple) -> dict:
    values = dict(zip(columns, row))
    return {
        "id": int(values["id"]),
        "week_label": values["week_label"],
        "generated_at": values["generated_at"],
        "model": values["model"],
        "prompt_version": values["prompt_version"],
        "lookback_weeks": int(values["lookback_weeks"] or 0),
        "threads_analyzed": int(values["threads_analyzed"] or 0),
        "atoms_analyzed": int(values["atoms_analyzed"] or 0),
        "executive_brief": values["executive_brief"] or "",
        "what_changed": _parse_json(values["what_changed_json"], []),
        "trend_narratives": _parse_json(values["trend_narratives_json"], []),
        "study_now": _parse_json(values["study_now_json"], []),
        "actions": _parse_json(values["actions_json"], []),
        "caveats": _parse_json(values["caveats_json"], []),
        "analysis": _parse_json(values["analysis_json"], {}),
        "created_at": values["created_at"],
        "updated_at": values["updated_at"],
    }


def upsert_frontier_analysis(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    generated_at: str | None = None,
    model: str,
    prompt_version: str,
    lookback_weeks: int,
    threads_analyzed: int,
    atoms_analyzed: int,
    executive_brief: str,
    what_changed: Iterable[object] | None,
    trend_narratives: Iterable[object] | None,
    study_now: Iterable[object] | None,
    actions: Iterable[object] | None,
    caveats: Iterable[object] | None,
    analysis: dict | None,
) -> dict:
    clean_week = _clean_required(week_label, "week_label")
    clean_model = _clean_required(model, "model")
    clean_prompt = _clean_required(prompt_version, "prompt_version")
    timestamp = generated_at or _now_iso()
    now = _now_iso()
    connection.execute(
        """
        INSERT INTO frontier_analyses (
            week_label,
            generated_at,
            model,
            prompt_version,
            lookback_weeks,
            threads_analyzed,
            atoms_analyzed,
            executive_brief,
            what_changed_json,
            trend_narratives_json,
            study_now_json,
            actions_json,
            caveats_json,
            analysis_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(week_label) DO UPDATE SET
            generated_at = excluded.generated_at,
            model = excluded.model,
            prompt_version = excluded.prompt_version,
            lookback_weeks = excluded.lookback_weeks,
            threads_analyzed = excluded.threads_analyzed,
            atoms_analyzed = excluded.atoms_analyzed,
            executive_brief = excluded.executive_brief,
            what_changed_json = excluded.what_changed_json,
            trend_narratives_json = excluded.trend_narratives_json,
            study_now_json = excluded.study_now_json,
            actions_json = excluded.actions_json,
            caveats_json = excluded.caveats_json,
            analysis_json = excluded.analysis_json,
            updated_at = excluded.updated_at
        """,
        (
            clean_week,
            _clean_required(timestamp, "generated_at"),
            clean_model,
            clean_prompt,
            max(1, int(lookback_weeks or 1)),
            max(0, int(threads_analyzed or 0)),
            max(0, int(atoms_analyzed or 0)),
            str(executive_brief or "").strip(),
            _json_array(what_changed),
            _json_array(trend_narratives),
            _json_array(study_now),
            _json_array(actions),
            _json_array(caveats),
            _json_object(analysis),
            now,
            now,
        ),
    )
    connection.commit()
    row = fetch_frontier_analysis(connection, week_label=clean_week)
    if not row:
        raise RuntimeError("frontier analysis could not be read back")
    return row


def fetch_frontier_analysis(connection: sqlite3.Connection, *, week_label: str) -> dict | None:
    cursor = connection.execute(
        """
        SELECT *
        FROM frontier_analyses
        WHERE week_label = ?
        LIMIT 1
        """,
        (_clean_required(week_label, "week_label"),),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [description[0] for description in cursor.description or []]
    return _row_to_analysis(columns, row)
