import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROOF_RECEIPT_SCHEMA_VERSION = "entropy_core.product_receipt.v1"
PRODUCT_ID = "telegram-research-agent"
CORE_EVIDENCE_CHECK_METHOD = "deterministic_core_evidence_lookup"
SIGNAL_EVIDENCE_REF_RE = re.compile(r"^signal_evidence_item:(\d+)$")
TELEGRAM_POST_URL_RE = re.compile(
    r"^https://t\.me/(?:[A-Za-z0-9_]+/\d+|c/\d+/\d+)(?:\?[^\s#]+)?$"
)


def build_core_research_brief_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Convert a local Research Brief receipt row into a Core-compatible receipt."""
    receipt_id = _required(receipt, "receipt_id")
    evidence_refs = _evidence_refs(receipt)
    verifier_status = _map_status(str(receipt.get("verification_status") or "pending"))
    verifier_notes = []
    if verifier_status != "passed":
        verifier_notes.append(str(receipt.get("verifier_notes") or "receipt not verified"))
    artifact_ref = _artifact_ref(receipt)
    return {
        "type": "research_brief_receipt",
        "schema_version": PROOF_RECEIPT_SCHEMA_VERSION,
        "product_id": PRODUCT_ID,
        "receipt_id": receipt_id,
        "week_label": _required(receipt, "week_label"),
        "artifact_ref": artifact_ref,
        "artifact_sha256": _artifact_hash(artifact_ref),
        "generated_at": receipt.get("generated_at") or _now_iso(),
        "evidence_refs": evidence_refs,
        "verifier_status": verifier_status,
        "verifier_notes": verifier_notes,
        "entropy_core_level": "evidence_lookup_compatible",
    }


def core_receipt_sha256(core_receipt: dict[str, Any]) -> str:
    payload = json.dumps(
        core_receipt,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_core_research_brief_evidence_refs(
    connection: sqlite3.Connection,
    core_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Verify Core-compatible evidence refs against local product evidence."""
    evidence_refs = core_receipt.get("evidence_refs")
    failures: list[str] = []
    review_notes: list[str] = []
    signal_evidence_item_ids: list[int] = []
    telegram_source_links: list[str] = []

    if not isinstance(evidence_refs, list) or not evidence_refs:
        failures.append("Core receipt evidence_refs are missing")
        return _core_evidence_result(
            checked_ref_count=0,
            resolved_signal_evidence_item_ids=[],
            checked_telegram_source_links=[],
            failures=failures,
            review_notes=review_notes,
        )

    for index, evidence_ref in enumerate(evidence_refs, start=1):
        if not isinstance(evidence_ref, dict):
            failures.append(f"evidence_ref[{index}] is not an object")
            continue

        ref_type = str(evidence_ref.get("ref_type") or "").strip()
        ref_id = str(evidence_ref.get("ref_id") or "").strip()
        if not ref_type or not ref_id:
            failures.append(f"evidence_ref[{index}] is missing ref_type or ref_id")
            continue

        checksum = str(evidence_ref.get("checksum_sha256") or "").strip()
        if checksum and checksum != _hash_text(ref_id):
            failures.append(f"checksum mismatch for {ref_id}")
        elif not checksum:
            review_notes.append(f"checksum missing for {ref_id}")

        if ref_type == "signal_evidence_item":
            match = SIGNAL_EVIDENCE_REF_RE.match(ref_id)
            if not match:
                failures.append(f"malformed signal_evidence_item ref: {ref_id}")
                continue
            signal_evidence_item_ids.append(int(match.group(1)))
            continue

        if ref_type == "telegram_source_link":
            if not TELEGRAM_POST_URL_RE.match(ref_id):
                failures.append(f"malformed Telegram source link: {ref_id}")
                continue
            telegram_source_links.append(ref_id)
            continue

        failures.append(f"unsupported Core evidence ref_type: {ref_type}")

    resolved_signal_ids = _resolve_signal_evidence_item_ids(connection, signal_evidence_item_ids)
    missing_signal_ids = [
        item_id for item_id in sorted(set(signal_evidence_item_ids)) if item_id not in resolved_signal_ids
    ]
    if missing_signal_ids:
        failures.append(
            "missing signal_evidence_item refs: "
            + ", ".join(str(item_id) for item_id in missing_signal_ids)
        )

    return _core_evidence_result(
        checked_ref_count=len(evidence_refs),
        resolved_signal_evidence_item_ids=sorted(resolved_signal_ids),
        checked_telegram_source_links=telegram_source_links,
        failures=failures,
        review_notes=review_notes,
    )


def summarize_research_brief_evidence(
    connection: sqlite3.Connection,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Build a reader-facing evidence/source-mix summary from a local receipt."""
    source_set = receipt.get("source_set") if isinstance(receipt.get("source_set"), dict) else {}
    evidence_ids = _coerce_int_values(source_set.get("source_evidence_item_ids"))
    telegram_link_values = source_set.get("telegram_source_links")
    if not isinstance(telegram_link_values, list):
        telegram_link_values = []
    telegram_links = [
        str(url).strip()
        for url in telegram_link_values
        if str(url).strip()
    ]
    post_counts = receipt.get("post_counts") if isinstance(receipt.get("post_counts"), dict) else {}
    failures: list[str] = []
    review_notes: list[str] = []

    try:
        core_receipt = build_core_research_brief_receipt(receipt)
        lookup = verify_core_research_brief_evidence_refs(connection, core_receipt)
        lookup_status = str(lookup.get("status") or "needs_review")
        resolved_evidence_ids = list(lookup.get("resolved_signal_evidence_item_ids") or [])
        checked_telegram_links = list(lookup.get("checked_telegram_source_links") or [])
        failures = [str(item) for item in lookup.get("failures", [])]
        review_notes = [str(item) for item in lookup.get("review_notes", [])]
    except ValueError as exc:
        lookup_status = "failed"
        resolved_evidence_ids = []
        checked_telegram_links = []
        failures = [str(exc)]
    except Exception as exc:  # pragma: no cover - defensive receipt summarization
        lookup_status = "needs_review"
        resolved_evidence_ids = []
        checked_telegram_links = []
        review_notes = [f"evidence lookup unavailable: {exc}"]

    top_channels = _top_receipt_channels(connection, source_set)
    confidence_level, confidence_sentence = _evidence_confidence(
        lookup_status=lookup_status,
        post_counts=post_counts,
        local_evidence_row_count=len(resolved_evidence_ids),
        telegram_source_link_count=len(checked_telegram_links) or len(telegram_links),
    )
    fallback_used = bool(receipt.get("fallback_delivery_used"))
    fallback_delivery = str(receipt.get("fallback_delivery") or "").strip()
    return {
        "status": lookup_status,
        "receipt_id": str(receipt.get("receipt_id") or ""),
        "week_label": str(receipt.get("week_label") or ""),
        "local_evidence_row_count": len(resolved_evidence_ids),
        "declared_evidence_ref_count": len(evidence_ids),
        "telegram_source_link_count": len(checked_telegram_links) or len(telegram_links),
        "declared_telegram_source_link_count": len(telegram_links),
        "top_channels": top_channels,
        "fallback_delivery_used": fallback_used,
        "fallback_delivery": fallback_delivery if fallback_used else "not_used",
        "confidence_level": confidence_level,
        "confidence_sentence": confidence_sentence,
        "failures": failures,
        "review_notes": review_notes,
        "runtime_dependency": False,
    }


def _evidence_refs(receipt: dict[str, Any]) -> list[dict[str, str]]:
    source_set = receipt.get("source_set") or {}
    refs: list[dict[str, str]] = []
    for item_id in source_set.get("source_evidence_item_ids") or []:
        ref_id = f"signal_evidence_item:{item_id}"
        refs.append(
            {
                "ref_id": ref_id,
                "ref_type": "signal_evidence_item",
                "supports": str(receipt.get("week_label") or "research_brief"),
                "checksum_sha256": _hash_text(ref_id),
            }
        )
    for url in source_set.get("telegram_source_links") or []:
        refs.append(
            {
                "ref_id": str(url),
                "ref_type": "telegram_source_link",
                "supports": str(receipt.get("week_label") or "research_brief"),
                "checksum_sha256": _hash_text(str(url)),
            }
        )
    if not refs:
        raise ValueError("Research Brief core receipt requires source evidence refs")
    return refs


def _artifact_ref(receipt: dict[str, Any]) -> str:
    for field in ("markdown_path", "html_path", "json_path", "telegraph_url"):
        value = str(receipt.get(field) or "").strip()
        if value:
            return value
    raise ValueError("Research Brief core receipt requires an artifact reference")


def _artifact_hash(artifact_ref: str) -> str:
    path = Path(artifact_ref)
    if path.exists() and path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return hashlib.sha256(artifact_ref.encode("utf-8")).hexdigest()


def _map_status(status: str) -> str:
    if status in {"verified", "waived"}:
        return "passed"
    if status == "failed":
        return "failed"
    return "needs_review"


def _required(receipt: dict[str, Any], field: str) -> str:
    value = str(receipt.get(field) or "").strip()
    if not value:
        raise ValueError(f"Research Brief core receipt requires {field}")
    return value


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _core_evidence_result(
    *,
    checked_ref_count: int,
    resolved_signal_evidence_item_ids: list[int],
    checked_telegram_source_links: list[str],
    failures: list[str],
    review_notes: list[str],
) -> dict[str, Any]:
    if failures:
        status = "failed"
    elif review_notes:
        status = "needs_review"
    else:
        status = "passed"
    return {
        "method": CORE_EVIDENCE_CHECK_METHOD,
        "status": status,
        "checked_ref_count": checked_ref_count,
        "resolved_signal_evidence_item_ids": resolved_signal_evidence_item_ids,
        "checked_telegram_source_links": checked_telegram_source_links,
        "failures": failures,
        "review_notes": review_notes,
        "runtime_dependency": False,
    }


def _resolve_signal_evidence_item_ids(
    connection: sqlite3.Connection,
    evidence_item_ids: list[int],
) -> set[int]:
    unique_ids = sorted(set(evidence_item_ids))
    if not unique_ids:
        return set()
    if not _table_exists(connection, "signal_evidence_items"):
        return set()
    placeholders = ",".join("?" for _ in unique_ids)
    rows = connection.execute(
        f"SELECT id FROM signal_evidence_items WHERE id IN ({placeholders})",
        unique_ids,
    ).fetchall()
    return {int(row[0]) for row in rows}


def _coerce_int_values(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    result: list[int] = []
    for value in values:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            continue
    return result


def _top_receipt_channels(connection: sqlite3.Connection, source_set: dict[str, Any]) -> list[dict[str, Any]]:
    post_ids = _coerce_int_values(source_set.get("source_post_ids"))
    if post_ids and _table_exists(connection, "posts"):
        placeholders = ",".join("?" for _ in post_ids)
        try:
            rows = connection.execute(
                f"""
                SELECT COALESCE(channel_username, '') AS channel_username, COUNT(*) AS count
                FROM posts
                WHERE id IN ({placeholders})
                GROUP BY COALESCE(channel_username, '')
                ORDER BY count DESC, channel_username ASC
                LIMIT 3
                """,
                post_ids,
            ).fetchall()
        except sqlite3.Error:
            rows = []
        channels = [
            {
                "channel": str(row["channel_username"] if isinstance(row, sqlite3.Row) else row[0]).strip(),
                "count": int(row["count"] if isinstance(row, sqlite3.Row) else row[1]),
            }
            for row in rows
            if str(row["channel_username"] if isinstance(row, sqlite3.Row) else row[0]).strip()
        ]
        if channels:
            return channels

    channel_values = source_set.get("channels")
    if not isinstance(channel_values, list):
        channel_values = []
    fallback_channels = [str(channel).strip() for channel in channel_values if str(channel).strip()]
    counts = Counter(fallback_channels)
    return [
        {"channel": channel, "count": count}
        for channel, count in counts.most_common(3)
    ]


def _evidence_confidence(
    *,
    lookup_status: str,
    post_counts: dict[str, Any],
    local_evidence_row_count: int,
    telegram_source_link_count: int,
) -> tuple[str, str]:
    strong_count = int(post_counts.get("strong_count") or 0)
    watch_count = int(post_counts.get("watch_count") or 0)
    actionable_count = strong_count + watch_count
    if lookup_status == "failed":
        return "low", "low - receipt evidence lookup failed; review source links before acting."
    if actionable_count <= 0:
        return "low", "low - no strong/watch signals were available this week."
    if lookup_status == "needs_review":
        return "medium-low", "medium-low - source refs exist but receipt lookup needs review."
    if local_evidence_row_count <= 0:
        return "medium-low", "medium-low - Telegram links resolved, but no local evidence rows were available."
    if telegram_source_link_count < actionable_count:
        return "medium", "medium - local evidence resolved, but not every signal has a Telegram source link."
    return "medium", "medium - local evidence rows and Telegram source links resolved."


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
