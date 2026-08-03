from __future__ import annotations

from typing import Any, Mapping


PROVIDER_EGRESS_REQUIRED_MESSAGE = (
    "LLM chat requires --allow-provider-egress before bounded Telegram snippets "
    "can be sent to a provider. No provider call was made. Re-run with that "
    "switch or use local memory ask."
)

INTERACTIVE_EXIT_COMMANDS = frozenset({"/exit", "/quit", ":q", "exit", "quit"})


def provider_egress_required_message() -> str:
    return PROVIDER_EGRESS_REQUIRED_MESSAGE


def build_prm_chat_receipt(result: Mapping[str, Any], *, mode: str = "llm-approved") -> dict[str, Any]:
    contract = _mapping(result.get("answer_contract"))
    evidence = _mapping(result.get("evidence"))
    trace = _mapping(result.get("trace"))
    telemetry = _mapping(result.get("telemetry"))
    privacy_boundary = _mapping(trace.get("privacy_boundary"))
    telemetry_privacy = _mapping(telemetry.get("privacy"))

    source_links = _strings(contract.get("source_links"))
    if not source_links:
        source_links = _strings(evidence.get("source_refs"))
    atom_ids = _strings(evidence.get("atom_ids"))
    thread_slugs = _strings(evidence.get("thread_slugs"))
    artifact_paths = _mapping(evidence.get("artifact_paths"))
    sources = _unique(
        [
            *source_links,
            *[f"atom:{atom_id}" for atom_id in atom_ids],
            *[f"thread:{slug}" for slug in thread_slugs],
            *[f"artifact:{name}={path}" for name, path in artifact_paths.items() if str(path).strip()],
        ]
    )

    external_verification = _mapping(contract.get("external_verification"))
    archive_support = _archive_support(contract, source_links, external_verification)
    unknowns = _strings(contract.get("unknowns"))
    write_performed = _bool(
        privacy_boundary.get("write_performed"),
        default=_bool(telemetry_privacy.get("write_performed"), default=False),
    )
    termination_reason = str(trace.get("termination_reason") or "")
    pending_confirmation = termination_reason == "needs_confirmation"
    model_calls = _model_calls(telemetry)
    estimated_cost_usd = _estimated_cost_usd(telemetry)
    bounded_snippet_egress = _bool(
        telemetry_privacy.get("bounded_telegram_snippet_provider_egress"),
        default=_bool(privacy_boundary.get("bounded_telegram_snippet_provider_egress"), default=False),
    )
    raw_corpus_egress = _bool(
        telemetry_privacy.get("raw_telegram_corpus_egress"),
        default=_bool(privacy_boundary.get("raw_telegram_corpus_egress"), default=False),
    )

    return {
        "schema_version": "prm_chat_display.v1",
        "status": str(result.get("status") or "unknown"),
        "mode": mode,
        "answer": str(result.get("answer") or "").strip(),
        "archive_support": archive_support,
        "sources": sources[:10],
        "unknowns": unknowns[:10],
        "external_verification": {
            "required": _bool(external_verification.get("required"), default=False),
            "status": str(external_verification.get("status") or "not_required"),
            "category": external_verification.get("category"),
            "reason": external_verification.get("reason"),
            "external_source_links": _strings(external_verification.get("external_source_links"))[:10],
        },
        "write_status": {
            "write_performed": write_performed,
            "pending_confirmation": pending_confirmation,
            "confirmation_gated_write": _bool(
                privacy_boundary.get("confirmation_gated_write"),
                default=write_performed,
            ),
            "termination_reason": termination_reason or "unknown",
        },
        "privacy": {
            "mode": mode,
            "model_calls": model_calls,
            "estimated_cost_usd": estimated_cost_usd,
            "bounded_telegram_snippet_provider_egress": bounded_snippet_egress,
            "raw_telegram_corpus_egress": raw_corpus_egress,
            "durable_writes": write_performed,
        },
    }


def render_prm_chat_answer(
    result: Mapping[str, Any],
    *,
    mode: str = "llm-approved",
    max_answer_chars: int = 2200,
) -> str:
    receipt = build_prm_chat_receipt(result, mode=mode)
    answer = _truncate(str(receipt["answer"] or "No answer returned."), max(240, max_answer_chars))
    lines = [
        "PRM Chat",
        "",
        "Answer",
        answer,
        "",
        "Sources",
    ]
    sources = receipt["sources"]
    if sources:
        lines.extend(f"- {source}" for source in sources[:8])
    else:
        lines.append("- insufficient evidence")

    archive = receipt["archive_support"]
    lines.extend(
        [
            "",
            f"Archive support: status={archive['status']}; source_count={archive['source_count']}",
        ]
    )

    external = receipt["external_verification"]
    lines.append(
        "External verification: "
        f"status={external['status']}; required={_bool_text(external['required'])}"
        + (f"; category={external['category']}" if external.get("category") else "")
    )
    if external.get("reason"):
        lines.append(f"External reason: {_truncate(str(external['reason']), 280)}")

    unknowns = receipt["unknowns"]
    if unknowns:
        lines.append("Unknowns")
        lines.extend(f"- {_truncate(item, 180)}" for item in unknowns[:6])
    else:
        lines.append("Unknowns: none")

    write_status = receipt["write_status"]
    lines.append(
        "Write status: "
        f"write_performed={_bool_text(write_status['write_performed'])}; "
        f"pending_confirmation={_bool_text(write_status['pending_confirmation'])}; "
        f"confirmation_gated_write={_bool_text(write_status['confirmation_gated_write'])}"
    )

    privacy = receipt["privacy"]
    lines.append(
        "Privacy: "
        f"mode={privacy['mode']}; "
        f"model_calls={privacy['model_calls']}; "
        f"estimated_cost_usd={_format_cost(privacy['estimated_cost_usd'])}; "
        "bounded_telegram_snippet_provider_egress="
        f"{_bool_text(privacy['bounded_telegram_snippet_provider_egress'])}; "
        f"raw_telegram_corpus_egress={_bool_text(privacy['raw_telegram_corpus_egress'])}; "
        f"durable_writes={_bool_text(privacy['durable_writes'])}"
    )
    return "\n".join(lines).rstrip()


def _archive_support(
    contract: Mapping[str, Any],
    source_links: list[str],
    external_verification: Mapping[str, Any],
) -> dict[str, Any]:
    if _bool(external_verification.get("required"), default=False):
        status = "verification_required"
    else:
        raw_support = _mapping(contract.get("archive_support"))
        raw_status = str(raw_support.get("status") or "").strip()
        if raw_status == "available":
            status = "supported"
        elif source_links:
            status = "partial"
        else:
            status = "not_found"
    return {
        "status": status,
        "source_count": len(source_links),
    }


def _model_calls(telemetry: Mapping[str, Any]) -> int:
    total = 0
    for section_name in ("planning", "generation"):
        section = _mapping(telemetry.get(section_name))
        total += _int(section.get("model_calls"))
    return total


def _estimated_cost_usd(telemetry: Mapping[str, Any]) -> float:
    total = 0.0
    for section_name in ("planning", "generation"):
        section = _mapping(telemetry.get(section_name))
        value = section.get("estimated_cost_usd")
        if value is None:
            continue
        try:
            total += float(value)
        except (TypeError, ValueError):
            continue
    return round(total, 8)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
        return default
    return bool(value)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def _format_cost(value: Any) -> str:
    try:
        cost = float(value or 0.0)
    except (TypeError, ValueError):
        return "0"
    if cost == 0.0:
        return "0"
    return f"{cost:.8f}"


def _truncate(text: str, limit: int) -> str:
    compact = str(text or "").strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 15].rstrip() + "\n...[truncated]"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique
