"""Autonomous workflow contracts and privacy-safe telemetry receipts.

PRM-17 defines contracts and aggregate telemetry only. This module does not
start scheduled jobs, read production databases, call providers, or write files.
"""

from __future__ import annotations

import copy
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


WORKFLOW_CONTRACT_SCHEMA_VERSION = "autonomous_workflow_contract.v1"
WORKFLOW_TELEMETRY_SCHEMA_VERSION = "workflow_telemetry_receipt.v1"

DEFAULT_WEEKLY_COST_LIMIT_USD = 10.0
DEFAULT_WEEKLY_MODEL_CALL_LIMIT = 500

WORKFLOW_CONTRACT_REQUIRED_FIELDS = (
    "workflow",
    "trigger",
    "inputs",
    "outputs",
    "idempotency_key",
    "retry_policy",
    "fallback",
    "receipt",
    "rollback",
)

REQUIRED_TELEMETRY_METRICS = (
    "index_freshness_seconds",
    "queue_age_seconds",
    "retrieval_latency_ms",
    "generation_latency_ms",
    "model_cost_usd",
    "model_calls",
    "tool_calls",
    "no_answer_rate",
)

FORBIDDEN_INPUT_KEYS = {
    "raw_post_text",
    "raw_text",
    "telegram_text",
    "message_text",
    "content",
    "provider_payload",
    "prompt",
    "completion",
    "llm_response",
}

FORBIDDEN_RECEIPT_KEYS = FORBIDDEN_INPUT_KEYS

_TOKEN_RE = re.compile(r"[^a-zA-Z0-9_.:-]+")
_WORKFLOW_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

_WORKFLOW_CONTRACTS: tuple[dict[str, object], ...] = (
    {
        "workflow": "telegram_ingestion",
        "trigger": "scheduled_or_manual_approved",
        "inputs": ["channel_allowlist", "since_cursor", "telegram_session_ref"],
        "outputs": ["raw_posts_upsert_counts", "ingestion_cursor_receipt"],
        "idempotency_key": "telegram_ingestion:{channel_set}:{cursor_window}",
        "retry_policy": {
            "max_retries": 1,
            "backoff": "bounded_linear_5m",
            "retryable_errors": ["telegram_rate_limit", "network_timeout"],
        },
        "fallback": "keep previous archive/search state available and mark ingestion freshness stale",
        "receipt": [
            "run_id",
            "channel_count",
            "new_post_count",
            "updated_post_count",
            "cursor_before",
            "cursor_after",
            "index_freshness_seconds",
        ],
        "rollback": "rerun the same cursor window idempotently; restore database backup only after approved maintenance",
    },
    {
        "workflow": "archive_indexing",
        "trigger": "after_ingestion_or_manual_approved",
        "inputs": ["raw_posts_count", "posts_count", "index_contract_version"],
        "outputs": ["posts_fts_count", "missing_fts_count", "index_freshness_receipt"],
        "idempotency_key": "archive_indexing:{index_contract_version}:{source_count}:{window}",
        "retry_policy": {
            "max_retries": 1,
            "backoff": "single_retry_after_backup_check",
            "retryable_errors": ["sqlite_busy", "transient_io"],
        },
        "fallback": "serve prior FTS index when integrity checks pass; otherwise degrade archive search only",
        "receipt": [
            "run_id",
            "source_row_count",
            "index_row_count",
            "missing_index_row_count",
            "index_freshness_seconds",
        ],
        "rollback": "restore previous derived index backup or rebuild derived FTS from canonical rows during approved maintenance",
    },
    {
        "workflow": "reaction_fast_lane",
        "trigger": "after_reaction_sync_or_manual_approved",
        "inputs": ["reaction_snapshot_ref", "archive_document_ids", "operator_feedback_counts"],
        "outputs": ["searchable_reacted_post_count", "enrichment_queue_count", "reaction_receipt"],
        "idempotency_key": "reaction_fast_lane:{snapshot_ref}:{archive_contract_version}",
        "retry_policy": {
            "max_retries": 1,
            "backoff": "bounded_linear_5m",
            "retryable_errors": ["sqlite_busy"],
        },
        "fallback": "preserve archive search and mark reaction personalization stale",
        "receipt": [
            "run_id",
            "reaction_count",
            "resolved_post_count",
            "queued_enrichment_count",
            "queue_age_seconds",
        ],
        "rollback": "append compensating queue/receipt events; do not delete operator reactions",
    },
    {
        "workflow": "selective_enrichment",
        "trigger": "scheduled_or_manual_approved",
        "inputs": ["priority_queue_snapshot", "budget_limits", "extractor_version"],
        "outputs": ["enrichment_receipts", "queue_age_receipt", "cost_receipt"],
        "idempotency_key": "selective_enrichment:{queue_snapshot}:{budget_window}:{extractor_version}",
        "retry_policy": {
            "max_retries": 1,
            "backoff": "retry_failed_items_once",
            "retryable_errors": ["provider_timeout", "rate_limit"],
        },
        "fallback": "stop on budget or extractor failure; archive search remains available",
        "receipt": [
            "run_id",
            "attempted_count",
            "succeeded_count",
            "failed_count",
            "model_cost_usd",
            "model_calls",
            "queue_age_seconds",
        ],
        "rollback": "disable generated enrichment projection or append compensating events; never mutate raw posts",
    },
    {
        "workflow": "weekly_brief_v3",
        "trigger": "scheduled_or_manual_approved",
        "inputs": ["watch_topics", "reactions", "questions", "saved_notes", "projects", "experiments", "feedback"],
        "outputs": ["weekly_brief_v3_json", "weekly_brief_v3_html", "visual_contract_receipt"],
        "idempotency_key": "weekly_brief_v3:{week_id}:{context_snapshot_hash}",
        "retry_policy": {
            "max_retries": 1,
            "backoff": "rerender_static_projection_once",
            "retryable_errors": ["renderer_error"],
        },
        "fallback": "skip Brief V3 delivery while keeping assistant, archive search, and Knowledge Library available",
        "receipt": [
            "run_id",
            "week_id",
            "source_ref_count",
            "generation_latency_ms",
            "tool_calls",
            "no_answer_rate",
        ],
        "rollback": "discard generated Brief V3 artifacts; source memory and archive rows are unchanged",
    },
    {
        "workflow": "knowledge_library_projection",
        "trigger": "manual_query_or_confirmed_watch_topic",
        "inputs": ["topic", "bounded_archive_hits", "confirmed_memory_events"],
        "outputs": ["topic_page_json", "topic_page_html", "visual_contract_receipt"],
        "idempotency_key": "knowledge_library_projection:{topic_id}:{context_snapshot_hash}",
        "retry_policy": {
            "max_retries": 1,
            "backoff": "rerender_static_projection_once",
            "retryable_errors": ["renderer_error"],
        },
        "fallback": "leave existing topic pages intact and mark requested page unavailable",
        "receipt": [
            "run_id",
            "topic_id",
            "source_ref_count",
            "retrieval_latency_ms",
            "generation_latency_ms",
        ],
        "rollback": "discard regenerated derived page; confirmed memory and archive rows are unchanged",
    },
    {
        "workflow": "backup_snapshot",
        "trigger": "before_approved_migration_reindex_or_rollback",
        "inputs": ["database_path_ref", "source_row_counts", "schema_version"],
        "outputs": ["backup_ref", "backup_sha256", "aggregate_count_receipt"],
        "idempotency_key": "backup_snapshot:{database_ref}:{schema_version}:{started_at}",
        "retry_policy": {
            "max_retries": 1,
            "backoff": "stop_on_second_failure",
            "retryable_errors": ["transient_io"],
        },
        "fallback": "block the maintenance action when backup cannot be verified",
        "receipt": ["run_id", "backup_ref", "backup_sha256", "source_row_counts", "finished_at"],
        "rollback": "use only verified backup refs; never overwrite canonical rows without approval",
    },
    {
        "workflow": "rollback_reindex_dry_run",
        "trigger": "manual_approved_maintenance",
        "inputs": ["backup_ref", "aggregate_counts", "index_contract_version", "dry_run_flag"],
        "outputs": ["dry_run_receipt", "integrity_check_counts", "rollback_decision"],
        "idempotency_key": "rollback_reindex_dry_run:{backup_ref}:{index_contract_version}:{dry_run_flag}",
        "retry_policy": {
            "max_retries": 0,
            "backoff": "no_retry_without_human_review",
            "retryable_errors": [],
        },
        "fallback": "leave production state unchanged and require human review",
        "receipt": ["run_id", "dry_run", "source_row_counts", "index_row_counts", "error_class"],
        "rollback": "dry-run only unless a separate approved maintenance receipt exists",
    },
)


class WorkflowTelemetryValidationError(ValueError):
    """Raised when a workflow contract or telemetry receipt is unsafe."""


def get_autonomous_workflow_contracts() -> list[dict[str, object]]:
    """Return deep copies of the PRM-17 workflow contract registry."""

    return copy.deepcopy(list(_WORKFLOW_CONTRACTS))


def validate_autonomous_workflow_contracts(
    contracts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, object]:
    values = list(contracts) if contracts is not None else get_autonomous_workflow_contracts()
    errors: list[str] = []
    seen: set[str] = set()
    for index, contract in enumerate(values):
        if not isinstance(contract, Mapping):
            errors.append(f"contracts[{index}] must be an object")
            continue
        missing = [field for field in WORKFLOW_CONTRACT_REQUIRED_FIELDS if field not in contract]
        if missing:
            errors.append(f"{contract.get('workflow') or index} missing fields: {', '.join(missing)}")
        workflow = _clean_text(contract.get("workflow"))
        if not workflow or not _WORKFLOW_RE.fullmatch(workflow):
            errors.append(f"contracts[{index}].workflow is invalid")
        elif workflow in seen:
            errors.append(f"duplicate workflow: {workflow}")
        seen.add(workflow)
        for field in ("inputs", "outputs", "receipt"):
            value = contract.get(field)
            if not isinstance(value, list) or not value:
                errors.append(f"{workflow}.{field} must be a non-empty list")
        retry_policy = contract.get("retry_policy")
        if not isinstance(retry_policy, Mapping):
            errors.append(f"{workflow}.retry_policy must be an object")
        elif "max_retries" not in retry_policy:
            errors.append(f"{workflow}.retry_policy.max_retries is required")
        for field in ("trigger", "idempotency_key", "fallback", "rollback"):
            if not _clean_text(contract.get(field)):
                errors.append(f"{workflow}.{field} is required")
    if errors:
        raise WorkflowTelemetryValidationError("; ".join(errors))
    return {
        "schema_version": WORKFLOW_CONTRACT_SCHEMA_VERSION,
        "workflow_count": len(values),
        "workflows": sorted(seen),
        "status": "passed",
    }


def build_workflow_telemetry_receipt(
    *,
    workflow: str,
    run_id: str,
    idempotency_key: str,
    metrics: Mapping[str, Any],
    observed_at: str | None = None,
    error: BaseException | Mapping[str, Any] | str | None = None,
    weekly_cost_limit_usd: float = DEFAULT_WEEKLY_COST_LIMIT_USD,
    weekly_model_call_limit: int = DEFAULT_WEEKLY_MODEL_CALL_LIMIT,
) -> dict[str, object]:
    """Build a privacy-safe aggregate workflow telemetry receipt."""

    workflow_id = _clean_workflow(workflow)
    allowed = _workflow_ids()
    if workflow_id not in allowed:
        raise WorkflowTelemetryValidationError(f"unknown workflow: {workflow_id}")

    redacted_fields = sorted(
        set(_collect_forbidden_input_paths(metrics)) | ({"error.message"} if error is not None else set())
    )
    no_answer_count = _nonnegative_int(metrics.get("no_answer_count"), default=0)
    answered_count = _nonnegative_int(metrics.get("answered_count", metrics.get("answer_count")), default=0)
    no_answer_rate = _rate(metrics.get("no_answer_rate"), no_answer_count=no_answer_count, answered_count=answered_count)
    model_calls = _nonnegative_int(metrics.get("model_calls"), default=0)
    tool_calls = _nonnegative_int(metrics.get("tool_calls"), default=0)
    model_cost = _nonnegative_float(metrics.get("model_cost_usd"), default=0.0)
    weekly_cost = _nonnegative_float(metrics.get("weekly_cost_usd"), default=model_cost)
    weekly_model_calls = _nonnegative_int(metrics.get("weekly_model_calls"), default=model_calls)
    error_class = _error_class(error, metrics)

    receipt = {
        "schema_version": WORKFLOW_TELEMETRY_SCHEMA_VERSION,
        "workflow": workflow_id,
        "run_id": _token(run_id, fallback="run-unknown"),
        "idempotency_key": _bounded_text(idempotency_key, 160),
        "observed_at": observed_at or _now_iso(),
        "status": "failed" if error_class != "none" else "succeeded",
        "metrics": {
            "index_freshness_seconds": _nonnegative_float(metrics.get("index_freshness_seconds"), default=0.0),
            "queue_age_seconds": _nonnegative_float(metrics.get("queue_age_seconds"), default=0.0),
            "retrieval_latency_ms": _nonnegative_float(metrics.get("retrieval_latency_ms"), default=0.0),
            "generation_latency_ms": _nonnegative_float(metrics.get("generation_latency_ms"), default=0.0),
            "model_cost_usd": model_cost,
            "model_calls": model_calls,
            "tool_calls": tool_calls,
            "no_answer_count": no_answer_count,
            "answered_count": answered_count,
            "no_answer_rate": no_answer_rate,
        },
        "error": {
            "class": error_class,
            "retryable": _bool(metrics.get("retryable_error")),
            "message_logged": False,
        },
        "budget": {
            "weekly_cost_usd": weekly_cost,
            "weekly_cost_limit_usd": float(weekly_cost_limit_usd),
            "weekly_model_calls": weekly_model_calls,
            "weekly_model_call_limit": int(weekly_model_call_limit),
            "approval_required": bool(
                weekly_cost > float(weekly_cost_limit_usd)
                or weekly_model_calls > int(weekly_model_call_limit)
            ),
        },
        "privacy": {
            "raw_post_text_logged": False,
            "provider_payload_logged": False,
            "raw_telegram_corpus_egress": False,
            "redaction_provenance": "deterministic_key_allowlist",
            "redacted_fields": redacted_fields,
        },
    }
    return validate_workflow_telemetry_receipt(receipt)


def validate_workflow_telemetry_receipt(receipt: Mapping[str, Any]) -> dict[str, object]:
    errors: list[str] = []
    if receipt.get("schema_version") != WORKFLOW_TELEMETRY_SCHEMA_VERSION:
        errors.append("schema_version is invalid")
    workflow = _clean_text(receipt.get("workflow"))
    if workflow not in _workflow_ids():
        errors.append("workflow is unknown")
    if not _clean_text(receipt.get("run_id")):
        errors.append("run_id is required")
    if not _clean_text(receipt.get("idempotency_key")):
        errors.append("idempotency_key is required")

    metrics = receipt.get("metrics")
    if not isinstance(metrics, Mapping):
        errors.append("metrics must be an object")
    else:
        for field in REQUIRED_TELEMETRY_METRICS:
            if field not in metrics:
                errors.append(f"metrics.{field} is required")
        for field, value in metrics.items():
            if field in {"model_calls", "tool_calls", "no_answer_count", "answered_count"}:
                if not _is_nonnegative_int(value):
                    errors.append(f"metrics.{field} must be a non-negative integer")
            elif field == "no_answer_rate":
                if not _is_finite_number(value) or not 0.0 <= float(value) <= 1.0:
                    errors.append("metrics.no_answer_rate must be between 0 and 1")
            elif not _is_finite_number(value) or float(value) < 0:
                errors.append(f"metrics.{field} must be a non-negative number")

    error = receipt.get("error")
    if not isinstance(error, Mapping):
        errors.append("error must be an object")
    elif not _clean_text(error.get("class")):
        errors.append("error.class is required")

    budget = receipt.get("budget")
    if not isinstance(budget, Mapping):
        errors.append("budget must be an object")
    else:
        budget_number_fields = ("weekly_cost_usd", "weekly_cost_limit_usd")
        for field in budget_number_fields:
            if not _is_finite_number(budget.get(field)) or float(budget.get(field, 0.0)) < 0:
                errors.append(f"budget.{field} must be a non-negative number")
        budget_int_fields = ("weekly_model_calls", "weekly_model_call_limit")
        for field in budget_int_fields:
            if not _is_nonnegative_int(budget.get(field)):
                errors.append(f"budget.{field} must be a non-negative integer")
        if not errors and bool(budget.get("approval_required")) and not (
            float(budget["weekly_cost_usd"]) > float(budget["weekly_cost_limit_usd"])
            or int(budget["weekly_model_calls"]) > int(budget["weekly_model_call_limit"])
        ):
            errors.append("budget.approval_required must correspond to a budget breach")

    privacy = receipt.get("privacy")
    if not isinstance(privacy, Mapping):
        errors.append("privacy must be an object")
    else:
        if privacy.get("raw_post_text_logged") is not False:
            errors.append("privacy.raw_post_text_logged must be false")
        if privacy.get("provider_payload_logged") is not False:
            errors.append("privacy.provider_payload_logged must be false")
        if privacy.get("raw_telegram_corpus_egress") is not False:
            errors.append("privacy.raw_telegram_corpus_egress must be false")
        if privacy.get("redaction_provenance") != "deterministic_key_allowlist":
            errors.append("privacy.redaction_provenance is invalid")

    forbidden_paths = _collect_forbidden_receipt_paths(receipt)
    if forbidden_paths:
        errors.append("forbidden raw payload keys in receipt: " + ", ".join(sorted(forbidden_paths)))
    if errors:
        raise WorkflowTelemetryValidationError("; ".join(errors))
    return copy.deepcopy(dict(receipt))


def assert_no_private_telemetry_text(
    receipt: Mapping[str, Any],
    forbidden_texts: Sequence[str],
) -> dict[str, object]:
    serialized = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
    hits = [text for text in forbidden_texts if _clean_text(text) and _clean_text(text) in serialized]
    if hits:
        raise WorkflowTelemetryValidationError("private text leaked into telemetry receipt")
    return {"status": "passed", "checked_text_count": len([text for text in forbidden_texts if _clean_text(text)])}


def _workflow_ids() -> set[str]:
    return {str(contract["workflow"]) for contract in _WORKFLOW_CONTRACTS}


def _collect_forbidden_input_paths(value: object, *, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, raw_value in value.items():
            key = _clean_text(raw_key)
            path = f"{prefix}.{key}" if prefix else key
            if _is_forbidden_input_key(key):
                paths.append(path)
                continue
            paths.extend(_collect_forbidden_input_paths(raw_value, prefix=path))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            paths.extend(_collect_forbidden_input_paths(item, prefix=f"{prefix}[{index}]"))
    return paths


def _collect_forbidden_receipt_paths(value: object, *, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, raw_value in value.items():
            key = _clean_text(raw_key)
            path = f"{prefix}.{key}" if prefix else key
            if key.lower() in FORBIDDEN_RECEIPT_KEYS:
                paths.append(path)
                continue
            paths.extend(_collect_forbidden_receipt_paths(raw_value, prefix=path))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            paths.extend(_collect_forbidden_receipt_paths(item, prefix=f"{prefix}[{index}]"))
    return paths


def _is_forbidden_input_key(key: str) -> bool:
    lower = key.lower()
    return lower in FORBIDDEN_INPUT_KEYS or lower.endswith("_raw_text") or lower.endswith("_payload")


def _error_class(error: BaseException | Mapping[str, Any] | str | None, metrics: Mapping[str, Any]) -> str:
    metric_class = _clean_text(metrics.get("error_class"))
    if metric_class:
        return _token(metric_class, fallback="WorkflowError")
    if error is None:
        return "none"
    if isinstance(error, Mapping):
        return _token(error.get("class") or error.get("type") or "WorkflowError", fallback="WorkflowError")
    if isinstance(error, BaseException):
        return _token(type(error).__name__, fallback="WorkflowError")
    return "WorkflowError"


def _rate(raw: object, *, no_answer_count: int, answered_count: int) -> float:
    if raw is not None:
        value = _nonnegative_float(raw, default=0.0)
        return min(1.0, value)
    total = no_answer_count + answered_count
    if total <= 0:
        return 0.0
    return round(no_answer_count / total, 6)


def _nonnegative_float(raw: object, *, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(value) or value < 0:
        return float(default)
    return float(value)


def _nonnegative_int(raw: object, *, default: int) -> int:
    if isinstance(raw, bool):
        return int(default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return int(default)
    return value if value >= 0 else int(default)


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _clean_workflow(value: object) -> str:
    return _token(value, fallback="unknown").lower()


def _token(value: object, *, fallback: str) -> str:
    text = _clean_text(value)
    if not text:
        return fallback
    return _TOKEN_RE.sub("_", text)[:96] or fallback


def _bounded_text(value: object, limit: int) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 12)].rstrip() + "...<truncated>"


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
