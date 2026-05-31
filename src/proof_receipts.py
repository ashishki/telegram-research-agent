import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROOF_RECEIPT_SCHEMA_VERSION = "entropy_core.product_receipt.v1"
PRODUCT_ID = "telegram-research-agent"


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
