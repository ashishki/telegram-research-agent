from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Sequence

from db.archive_documents import archive_documents_for_row


REACTION_FAST_LANE_SCHEMA_VERSION = "reaction_fast_lane.v1"
DEFAULT_REACTION_SOURCE = "telegram_reaction"


class ReactionFastLaneError(ValueError):
    """Raised when a reaction fast-lane receipt is malformed."""


@dataclass(frozen=True)
class ReactionSemantics:
    interest_state: str
    positive_implicit_interest: bool
    negative_interest: bool
    post_level_interest_signals: int
    emoji_count: int
    emoji_interpretation: str
    interest_strength: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "interest_state": self.interest_state,
            "positive_implicit_interest": self.positive_implicit_interest,
            "negative_interest": self.negative_interest,
            "post_level_interest_signals": self.post_level_interest_signals,
            "emoji_count": self.emoji_count,
            "emoji_interpretation": self.emoji_interpretation,
            "interest_strength": self.interest_strength,
            "reasons": list(self.reasons),
        }


def classify_reaction_semantics(raw_emojis: Sequence[object] | None) -> ReactionSemantics:
    """Classify personal reaction semantics without interpreting emoji sentiment."""

    clean_emojis = {
        str(value).strip()
        for value in raw_emojis or ()
        if str(value).strip()
    }
    if not clean_emojis:
        return ReactionSemantics(
            interest_state="unknown",
            positive_implicit_interest=False,
            negative_interest=False,
            post_level_interest_signals=0,
            emoji_count=0,
            emoji_interpretation="not_applicable",
            interest_strength="none",
            reasons=("reaction_absence_is_unknown",),
        )

    reasons = ["emoji_type_is_audit_metadata_only"]
    if len(clean_emojis) > 1:
        reasons.append("multiple_emoji_deduplicate_to_one_post_signal")
    return ReactionSemantics(
        interest_state="positive_implicit_interest",
        positive_implicit_interest=True,
        negative_interest=False,
        post_level_interest_signals=1,
        emoji_count=len(clean_emojis),
        emoji_interpretation="audit_metadata_only",
        interest_strength="weak",
        reasons=tuple(reasons),
    )


def build_reaction_fast_lane_receipt(
    connection: sqlite3.Connection,
    *,
    source: str | None = DEFAULT_REACTION_SOURCE,
    ranking_receipts: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Build a read-only receipt for reacted-post archive search readiness.

    PRM-5's fast lane is intentionally independent from Knowledge Atoms. This
    receipt proves that reacted posts resolve to retained archive rows and FTS
    documents first, then records missing downstream enrichment/topic/ranking
    stages as incomplete reasons.
    """

    reasons: Counter[str] = Counter()
    if not _table_exists(connection, "reaction_sync_state"):
        reasons["reaction_sync_state_missing"] = 1
        return _receipt(
            counts=_base_counts(),
            stage_statuses={
                "reaction_detection": "unavailable",
                "source_resolution": "not_attempted",
                "archive_index": "not_attempted",
                "enrichment": "not_attempted",
                "topic_linkage": "not_attempted",
                "assistant_search": "not_attempted",
                "ranking": "not_attempted",
            },
            search_available=False,
            incomplete_stage_reasons=reasons,
        )

    reaction_rows = _reaction_rows(connection, source=source)
    matched_rows = _matched_post_rows(connection, reaction_rows)
    reaction_events = sum(int(row["reaction_event_count"] or 0) for row in reaction_rows)
    unique_reaction_refs = len(reaction_rows)
    matched_post_ids = {int(row["post_id"]) for row in matched_rows}

    unmatched_posts = max(0, unique_reaction_refs - len(matched_post_ids))
    if unmatched_posts:
        reasons["post_not_found"] = unmatched_posts

    indexed_posts: set[int] = set()
    archive_document_count = 0
    archive_exclusion_count = 0
    for row in matched_rows:
        post_id = int(row["post_id"])
        documents, exclusion = archive_documents_for_row(row)
        if exclusion is not None:
            archive_exclusion_count += 1
            reasons[exclusion.reason] += 1
            continue
        if not documents:
            archive_exclusion_count += 1
            reasons["archive_document_missing"] += 1
            continue
        if not _fts_row_exists(connection, post_id):
            reasons["archive_fts_row_missing"] += 1
            continue
        indexed_posts.add(post_id)
        archive_document_count += len(documents)

    atom_linked_post_ids, unique_atom_count = _atom_links(connection, indexed_posts)
    enrichment_attempts = len(indexed_posts)
    enrichment_successes = len(atom_linked_post_ids)
    enrichment_failures = max(0, enrichment_attempts - enrichment_successes)
    if enrichment_failures:
        reasons["knowledge_atom_not_extracted"] = enrichment_failures

    topic_linked_post_ids = _topic_linked_posts(connection, indexed_posts)
    topic_link_attempts = len(indexed_posts)
    topic_link_successes = len(topic_linked_post_ids)
    topic_link_failures = max(0, topic_link_attempts - topic_link_successes)
    if topic_link_failures:
        reasons["topic_not_linked"] = topic_link_failures

    ranking_effects = _ranking_effects(ranking_receipts)
    if indexed_posts and ranking_effects == 0:
        reasons["ranking_not_evaluated"] = len(indexed_posts)

    counts = _base_counts()
    counts.update(
        {
            "personal_reaction_events_detected": reaction_events,
            "unique_reacted_posts": unique_reaction_refs,
            "posts_resolved": len(matched_post_ids),
            "archive_posts_indexed": len(indexed_posts),
            "searchable_archive_posts": len(indexed_posts),
            "archive_documents_indexed": archive_document_count,
            "indexed_documents": archive_document_count,
            "searchable_archive_documents": archive_document_count,
            "archive_documents_excluded": archive_exclusion_count,
            "enrichment_attempts": enrichment_attempts,
            "enrichment_successes": enrichment_successes,
            "enrichment_failures": enrichment_failures,
            "unique_atoms_linked": unique_atom_count,
            "topic_link_attempts": topic_link_attempts,
            "topic_link_successes": topic_link_successes,
            "topic_link_failures": topic_link_failures,
            "topic_links": topic_link_successes,
            "ranking_effects": ranking_effects,
            "post_level_interest_signals": len(indexed_posts),
        }
    )
    stage_statuses = {
        "reaction_detection": _status(unique_reaction_refs, unique_reaction_refs, attempted=True),
        "source_resolution": _status(len(matched_post_ids), unique_reaction_refs, attempted=bool(unique_reaction_refs)),
        "archive_index": _status(len(indexed_posts), len(matched_post_ids), attempted=bool(matched_post_ids)),
        "enrichment": _status(enrichment_successes, enrichment_attempts, attempted=bool(enrichment_attempts)),
        "topic_linkage": _status(topic_link_successes, topic_link_attempts, attempted=bool(topic_link_attempts)),
        "assistant_search": _status(len(indexed_posts), len(matched_post_ids), attempted=bool(matched_post_ids)),
        "ranking": "complete" if ranking_effects else "not_evaluated",
    }
    return _receipt(
        counts=counts,
        stage_statuses=stage_statuses,
        search_available=archive_document_count > 0,
        incomplete_stage_reasons=reasons,
    )


def validate_reaction_fast_lane_receipt(receipt: Mapping[str, object]) -> dict[str, object]:
    if receipt.get("schema_version") != REACTION_FAST_LANE_SCHEMA_VERSION:
        raise ReactionFastLaneError("reaction fast-lane receipt schema_version is invalid")
    counts = receipt.get("counts")
    if not isinstance(counts, Mapping):
        raise ReactionFastLaneError("reaction fast-lane receipt counts must be an object")
    for field in _base_counts():
        _nonnegative_int(counts.get(field), f"counts.{field}")
    stages = receipt.get("stage_statuses")
    if not isinstance(stages, Mapping):
        raise ReactionFastLaneError("reaction fast-lane stage_statuses must be an object")
    for stage in (
        "reaction_detection",
        "source_resolution",
        "archive_index",
        "enrichment",
        "topic_linkage",
        "assistant_search",
        "ranking",
    ):
        if stage not in stages:
            raise ReactionFastLaneError(f"missing reaction fast-lane stage: {stage}")
    reasons = receipt.get("incomplete_stage_reasons")
    if not isinstance(reasons, Mapping):
        raise ReactionFastLaneError("incomplete_stage_reasons must be an object")
    for reason, count in reasons.items():
        if not isinstance(reason, str) or not reason.strip():
            raise ReactionFastLaneError("incomplete reason keys must be non-empty strings")
        _nonnegative_int(count, f"incomplete_stage_reasons.{reason}")
    privacy = receipt.get("privacy")
    if not isinstance(privacy, Mapping) or privacy.get("raw_text_included") is not False:
        raise ReactionFastLaneError("reaction fast-lane receipt must exclude raw text")
    return dict(receipt)


def build_operator_reaction_receipt(receipt: Mapping[str, object]) -> dict[str, object]:
    """Project a fast-lane receipt for the operator without sensitive reaction data."""

    validated = validate_reaction_fast_lane_receipt(receipt)
    counts = validated["counts"]
    reasons = validated["incomplete_stage_reasons"]
    return {
        "schema_version": "prm_operator_reaction_receipt.v1",
        "status": "ok" if validated["stage_statuses"]["reaction_detection"] == "complete" else "partial",
        "detected_reactions": counts["personal_reaction_events_detected"],
        "resolved_posts": counts["posts_resolved"],
        "already_searchable_posts": counts["searchable_archive_posts"],
        "newly_indexed_posts": 0,
        "enrichment": {
            "queued": counts["enrichment_attempts"],
            "completed": counts["enrichment_successes"],
            "failed": counts["enrichment_failures"],
        },
        "provisional_links": {
            "topics": counts["topic_links"],
            "projects": 0,
        },
        "ranking_effects": counts["ranking_effects"],
        "no_effect_reasons": dict(reasons),
        "privacy": {
            "raw_text_included": False,
            "source_urls_included": False,
            "emoji_semantics_included": False,
        },
    }


def render_operator_reaction_receipt(receipt: Mapping[str, object]) -> str:
    """Render a privacy-safe grouped reaction-recall view from a supplied receipt."""

    operator = build_operator_reaction_receipt(receipt)
    enrichment = operator["enrichment"]
    links = operator["provisional_links"]
    lines = [
        "Реакции в архиве",
        f"Найдено личных реакций: {operator['detected_reactions']}.",
        f"Связано с постами: {operator['resolved_posts']}; доступно в поиске: {operator['already_searchable_posts']}.",
        f"Обогащение: готово {enrichment['completed']} из {enrichment['queued']}; ошибок: {enrichment['failed']}.",
        f"Временные связи с темами: {links['topics']}.",
    ]
    reasons = operator["no_effect_reasons"]
    if reasons:
        lines.append("Ограничения: " + ", ".join(sorted(str(reason) for reason in reasons)))
    lines.append("Реакции — слабый временный сигнал; предпочтения не менялись.")
    return "\n".join(lines)


def build_reaction_preference_proposal(receipt: Mapping[str, object], *, threshold: int = 2) -> dict[str, object]:
    """Suggest, but never infer or write, a preference from repeated reactions."""

    validated = validate_reaction_fast_lane_receipt(receipt)
    count = int(validated["counts"]["unique_reacted_posts"])
    required = max(2, int(threshold))
    if count < required:
        return {
            "status": "insufficient_signal",
            "write_performed": False,
            "confirmation_required": False,
            "unique_reacted_posts": count,
        }
    return {
        "status": "needs_confirmation",
        "write_performed": False,
        "confirmation_required": True,
        "proposal": {
            "kind": "reaction_interest_preference",
            "summary": f"Повторный интерес к {count} материалам; предложить настройку предпочтения.",
            "source_count": count,
        },
    }


def _receipt(
    *,
    counts: Mapping[str, int],
    stage_statuses: Mapping[str, str],
    search_available: bool,
    incomplete_stage_reasons: Counter[str],
) -> dict[str, object]:
    return {
        "schema_version": REACTION_FAST_LANE_SCHEMA_VERSION,
        "counts": dict(counts),
        "stage_statuses": dict(stage_statuses),
        "search_availability": {
            "backend": "sqlite_fts",
            "assistant_archive_search_available": bool(search_available),
            "requires_knowledge_atoms": False,
        },
        "semantics": {
            "reaction_absence": classify_reaction_semantics(()).as_dict(),
            "emoji_values": "audit_metadata_only",
            "post_signal_strength": "weak",
        },
        "incomplete_stage_reasons": dict(sorted(incomplete_stage_reasons.items())),
        "privacy": {
            "raw_text_included": False,
            "emoji_values_included": False,
            "source_urls_included": False,
        },
    }


def _base_counts() -> dict[str, int]:
    return {
        "personal_reaction_events_detected": 0,
        "unique_reacted_posts": 0,
        "posts_resolved": 0,
        "archive_posts_indexed": 0,
        "searchable_archive_posts": 0,
        "archive_documents_indexed": 0,
        "indexed_documents": 0,
        "searchable_archive_documents": 0,
        "archive_documents_excluded": 0,
        "enrichment_attempts": 0,
        "enrichment_successes": 0,
        "enrichment_failures": 0,
        "unique_atoms_linked": 0,
        "topic_link_attempts": 0,
        "topic_link_successes": 0,
        "topic_link_failures": 0,
        "topic_links": 0,
        "ranking_effects": 0,
        "post_level_interest_signals": 0,
    }


def _reaction_rows(
    connection: sqlite3.Connection,
    *,
    source: str | None,
) -> list[dict[str, object]]:
    where = ""
    params: list[object] = []
    if source is not None:
        where = "WHERE source = ?"
        params.append(source)
    return _fetch_mappings(
        connection,
        f"""
        SELECT
            lower(ltrim(channel_username, '@')) AS channel_key,
            min(channel_username) AS channel_username,
            message_id,
            COUNT(*) AS reaction_event_count,
            COUNT(DISTINCT emoji) AS emoji_count
        FROM reaction_sync_state
        {where}
        GROUP BY lower(ltrim(channel_username, '@')), message_id
        ORDER BY lower(ltrim(channel_username, '@')), message_id
        """,
        params,
    )


def _matched_post_rows(
    connection: sqlite3.Connection,
    reaction_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    if not _table_exists(connection, "raw_posts") or not _table_exists(connection, "posts"):
        return []
    channel_id_sql = "r.channel_id" if _column_exists(connection, "raw_posts", "channel_id") else "0"
    message_url_sql = "r.message_url" if _column_exists(connection, "raw_posts", "message_url") else "''"
    forward_from_sql = "r.forward_from" if _column_exists(connection, "raw_posts", "forward_from") else "''"
    content_sql = "p.content" if _column_exists(connection, "posts", "content") else "''"
    language_sql = (
        "p.language_detected"
        if _column_exists(connection, "posts", "language_detected")
        else "'unknown'"
    )
    rows_by_post_id: dict[int, dict[str, object]] = {}
    for reaction in reaction_rows:
        rows = _fetch_mappings(
            connection,
            f"""
            SELECT
                p.id AS post_id,
                p.raw_post_id,
                p.channel_username,
                p.posted_at,
                {content_sql} AS content,
                {language_sql} AS language_detected,
                {channel_id_sql} AS channel_id,
                r.message_id,
                {message_url_sql} AS message_url,
                {forward_from_sql} AS forward_from
            FROM raw_posts r
            JOIN posts p ON p.raw_post_id = r.id
            WHERE lower(ltrim(r.channel_username, '@')) = ?
              AND r.message_id = ?
            ORDER BY p.id
            LIMIT 1
            """,
            [reaction["channel_key"], reaction["message_id"]],
        )
        for row in rows:
            row["reaction_event_count"] = int(reaction["reaction_event_count"] or 0)
            row["emoji_count"] = int(reaction["emoji_count"] or 0)
            rows_by_post_id[int(row["post_id"])] = row
    return [rows_by_post_id[post_id] for post_id in sorted(rows_by_post_id)]


def _fts_row_exists(connection: sqlite3.Connection, post_id: int) -> bool:
    if not _table_exists(connection, "posts_fts"):
        return False
    row = connection.execute(
        "SELECT 1 FROM posts_fts WHERE rowid = ? LIMIT 1",
        (int(post_id),),
    ).fetchone()
    return row is not None


def _atom_links(
    connection: sqlite3.Connection,
    post_ids: set[int],
) -> tuple[set[int], int]:
    if not post_ids or not _table_exists(connection, "knowledge_atoms"):
        return set(), 0
    linked_posts: set[int] = set()
    linked_atoms: set[int] = set()
    for row in _fetch_mappings(
        connection,
        "SELECT id, source_post_ids_json FROM knowledge_atoms ORDER BY id",
    ):
        atom_post_ids = {
            int(value)
            for value in _json_array(row.get("source_post_ids_json"))
            if str(value).strip().lstrip("-").isdigit()
        }
        matched = atom_post_ids.intersection(post_ids)
        if not matched:
            continue
        linked_posts.update(matched)
        linked_atoms.add(int(row["id"]))
    return linked_posts, len(linked_atoms)


def _topic_linked_posts(connection: sqlite3.Connection, post_ids: set[int]) -> set[int]:
    if not post_ids or not _table_exists(connection, "post_topics"):
        return set()
    placeholders = ",".join("?" for _ in post_ids)
    rows = _fetch_mappings(
        connection,
        f"""
        SELECT DISTINCT post_id
        FROM post_topics
        WHERE post_id IN ({placeholders})
        """,
        sorted(post_ids),
    )
    return {int(row["post_id"]) for row in rows}


def _ranking_effects(ranking_receipts: Sequence[Mapping[str, object]]) -> int:
    total = 0
    for receipt in ranking_receipts:
        counts = receipt.get("counts") if isinstance(receipt, Mapping) else None
        if not isinstance(counts, Mapping):
            continue
        total += _nonnegative_int(
            counts.get("selected_signals_influenced", 0),
            "counts.selected_signals_influenced",
        )
    return total


def _status(successes: int, attempts: int, *, attempted: bool) -> str:
    if not attempted:
        return "not_attempted"
    if attempts <= 0:
        return "complete"
    if successes >= attempts:
        return "complete"
    if successes > 0:
        return "partial"
    return "incomplete"


def _json_array(value: object) -> list[object]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _fetch_mappings(
    connection: sqlite3.Connection,
    sql: str,
    params: Sequence[object] = (),
) -> list[dict[str, object]]:
    cursor = connection.execute(sql, tuple(params))
    columns = [description[0] for description in cursor.description or ()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _column_exists(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row[1]) == column_name for row in rows)


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ReactionFastLaneError(f"{field} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ReactionFastLaneError(f"{field} must be a non-negative integer") from exc
    if result < 0:
        raise ReactionFastLaneError(f"{field} must be a non-negative integer")
    return result
