"""Intent-specific source-first answer contract for archive research."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from assistant.archive_relevance import canonical_query_variants, rank_archive_items

ARCHIVE_RESPONSE_INTENTS = frozenset({"archive_lookup", "archive_synthesis", "archive_to_action"})
ARCHIVE_RESPONSE_CONTRACTS = frozenset({"archive_lookup.v2", "archive_research.v2"})


def apply_archive_response_contract(
    payload: Mapping[str, Any],
    *,
    question: str,
    route: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(payload)
    archive = _mapping(result.get("archive_evidence"))
    ranked = rank_archive_items(question, _mappings(archive.get("items")))
    archive = {**archive, "items": ranked}
    result["archive_evidence"] = archive

    contract = build_archive_response_contract(
        question=question,
        archive_items=ranked,
        primary_intent=str(route.get("primary_intent") or "archive_synthesis"),
        response_contract_id=str(route.get("response_contract_id") or "archive_research.v2"),
        explicit_project=str(route.get("project_name") or ""),
        external_verification_required=bool(route.get("external_verification_required")),
    )
    result.update(
        {
            "question": question,
            "primary_intent": contract["primary_intent"],
            "response_contract_id": contract["response_contract_id"],
            "archive_contract": contract,
            "direct_answer": contract["direct_answer"],
        }
    )
    # Project packets may still exist in older orchestration internals.  They are
    # suppressed from the user-facing payload when project mapping was not
    # explicitly requested.
    if not bool(route.get("project_context_required")):
        result["project_fit"] = {}
        result["project_decision"] = {}
        professional = _mapping(result.get("professional_answer"))
        if professional:
            result["professional_answer"] = {
                **professional,
                "project_context": {},
                "project_implication": "",
                "recommended_action": _first_applicability(contract),
                "short_answer": contract["direct_answer"],
                "answer_status": contract["answer_status"],
            }
    return result


def build_archive_response_contract(
    *,
    question: str,
    archive_items: Sequence[Mapping[str, Any]],
    primary_intent: str,
    response_contract_id: str,
    explicit_project: str = "",
    external_verification_required: bool = False,
) -> dict[str, Any]:
    direct = [_finding(item) for item in archive_items if item.get("relevance_label") == "direct"]
    partial = [_finding(item) for item in archive_items if item.get("relevance_label") == "partial"]
    adjacent = [_finding(item) for item in archive_items if item.get("relevance_label") == "adjacent"]
    unrelated_count = sum(1 for item in archive_items if item.get("relevance_label") == "unrelated")
    direct_answer = _direct_answer(question, direct=direct, partial=partial, adjacent=adjacent)
    actionable = [finding for finding in direct if finding.get("supports_action")]
    applicability = (
        _applicability(actionable, explicit_project=explicit_project)
        if primary_intent == "archive_to_action"
        else []
    )
    limitations = _limitations(
        direct=direct,
        partial=partial,
        adjacent=adjacent,
        external_verification_required=external_verification_required,
    )
    sources = _sources([*direct, *partial, *adjacent])
    answer_status = "supported" if direct else "partial" if partial or adjacent else "insufficient_evidence"
    return {
        "schema_version": "prm_archive_answer.v2",
        "response_contract_id": response_contract_id if response_contract_id in ARCHIVE_RESPONSE_CONTRACTS else "archive_research.v2",
        "primary_intent": primary_intent,
        "question_scope": "local_archive",
        "direct_answer": direct_answer,
        "answer_status": answer_status,
        "result_summary": {
            "direct_count": len(direct),
            "partial_count": len(partial),
            "adjacent_count": len(adjacent),
            "unrelated_count": unrelated_count,
            "selected_count": len(direct) + len(partial) + len(adjacent),
            "actionable_count": len(actionable),
        },
        "direct_findings": direct[:4],
        "partial_findings": partial[:3],
        "adjacent_findings": adjacent[:3],
        "applicability": applicability[:4],
        "limitations": limitations[:3],
        "sources": sources[:8],
        "search_refinements": canonical_query_variants(question, max_variants=8),
        "project_mapping": {
            "requested": bool(explicit_project),
            "project_name": explicit_project or None,
            "dominates_archive_answer": False,
        },
        "external_verification": {
            "required": bool(external_verification_required),
            "triggered_by_word_now_alone": False,
        },
        "write_performed": False,
    }


def _finding(item: Mapping[str, Any]) -> dict[str, Any]:
    summary = _short(item.get("snippet") or item.get("summary") or item.get("content") or item.get("text"), 260)
    source_url = str(item.get("source_url") or item.get("telegram_url") or item.get("message_url") or "").strip()
    evidence_id = str(
        item.get("archive_document_id")
        or item.get("post_archive_document_id")
        or item.get("post_id")
        or source_url
        or ""
    )
    return {
        "evidence_id": evidence_id,
        "title": _title(item, summary),
        "posted_at": str(item.get("posted_at") or ""),
        "channel_username": str(item.get("channel_username") or "").lstrip("@"),
        "source_url": source_url,
        "summary": summary,
        "relevance_label": str(item.get("relevance_label") or "unrelated"),
        "directness_score": float(item.get("directness_score") or 0.0),
        "relevance_reason": str(item.get("relevance_reason") or ""),
        "matched_query_variant": str(item.get("matched_query_variant") or ""),
        "source_role": str(item.get("source_role") or "commentary"),
        "supports_action": bool(item.get("supports_action")),
        "source_role_reason": str(item.get("source_role_reason") or ""),
    }


def _direct_answer(
    question: str,
    *,
    direct: Sequence[Mapping[str, Any]],
    partial: Sequence[Mapping[str, Any]],
    adjacent: Sequence[Mapping[str, Any]],
) -> str:
    topic = "agent evals" if "agent" in question.casefold() and ("eval" in question.casefold() or "оцен" in question.casefold()) else "запрошенной теме"
    if direct:
        suffix = "материал" if len(direct) == 1 else "материала" if len(direct) < 5 else "материалов"
        return f"В архиве найдено {len(direct)} прямых {suffix} по теме {topic}. Смежные источники отделены ниже и не выдаются за прямые."
    if partial:
        return f"Прямых материалов именно про {topic} я не нашёл. Есть {len(partial)} частично совпадающих материала; их выводы нужно использовать осторожно."
    if adjacent:
        suffix = "материал" if len(adjacent) == 1 else "материала" if len(adjacent) < 5 else "материалов"
        return f"Прямых материалов именно про {topic} я не нашёл. Есть {len(adjacent)} смежных {suffix}, но они не содержат прямой практики по запрошенной теме."
    return f"Прямых или смежных материалов по теме {topic} в текущей выдаче не найдено. Я не буду додумывать содержимое архива."


def _applicability(findings: Sequence[Mapping[str, Any]], *, explicit_project: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for finding in findings:
        text = f"{finding.get('title') or ''} {finding.get('summary') or ''}".casefold()
        candidates: list[tuple[str, str]] = []
        if any(marker in text for marker in ("groundedness", "grounded", "citation", "цитат")):
            candidates.append(("groundedness", "Добавить проверку groundedness и полноты цитирования для ответа агента."))
        if any(marker in text for marker in ("task success", "task-success", "успешност", "выполнение задачи")):
            candidates.append(("task_success", "Фиксировать task success на replayable задачах, а не только качество текста ответа."))
        if any(marker in text for marker in ("tool-call", "tool call", "tool use", "вызов инструмент")):
            candidates.append(("tool_correctness", "Проверять корректность выбора инструмента, аргументов и результата tool call."))
        if any(marker in text for marker in ("benchmark", "regression", "gold label", "baseline", "бенчмарк", "регресс")):
            candidates.append(("regression_fixture", "Собрать небольшой regression fixture с ожидаемым результатом и стабильным baseline."))
        if any(marker in text for marker in ("judge calibration", "human review", "калибров", "ручн")):
            candidates.append(("judge_calibration", "Калибровать автоматический judge на небольшой human-reviewed holdout."))
        for practice_id, recommendation in candidates:
            if any(item["practice_id"] == practice_id for item in result):
                continue
            result.append(
                {
                    "practice_id": practice_id,
                    "recommendation": recommendation,
                    "target_project": explicit_project or None,
                    "basis_evidence_id": finding.get("evidence_id"),
                    "inference": True,
                    "confidence": "medium",
                }
            )
    if not result and findings:
        first = findings[0]
        result.append(
            {
                "practice_id": "bounded_replay_case",
                "recommendation": "Выделить из прямого источника один failure mode и превратить его в небольшой replayable regression case.",
                "target_project": explicit_project or None,
                "basis_evidence_id": first.get("evidence_id"),
                "inference": True,
                "confidence": "low",
            }
        )
    return result


def _limitations(
    *,
    direct: Sequence[Mapping[str, Any]],
    partial: Sequence[Mapping[str, Any]],
    adjacent: Sequence[Mapping[str, Any]],
    external_verification_required: bool,
) -> list[str]:
    result: list[str] = []
    if not direct:
        result.append("Прямое совпадение не найдено; частичные и смежные материалы не считаются ответом на точный запрос.")
    elif not any(item.get("supports_action") for item in direct):
        result.append("Прямые тематические упоминания не содержат достаточно конкретной практики для рекомендации действия.")
    if adjacent:
        result.append("Смежный материал показывает контекст, но не доказывает наличие конкретной практики оценки агентов.")
    if external_verification_required:
        result.append("Актуальный внешний факт требует отдельной проверки первоисточника.")
    else:
        result.append("Практическая применимость — аналитический вывод по локальному архиву, а не подтверждённый внешний факт.")
    return result


def _sources(findings: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for finding in findings:
        url = str(finding.get("source_url") or "").strip()
        identity = url or str(finding.get("evidence_id") or "")
        if not identity or identity in seen:
            continue
        seen.add(identity)
        result.append(
            {
                "evidence_id": finding.get("evidence_id"),
                "posted_at": finding.get("posted_at"),
                "channel_username": finding.get("channel_username"),
                "source_url": url,
                "relevance_label": finding.get("relevance_label"),
            }
        )
    return result


def _first_applicability(contract: Mapping[str, Any]) -> str | None:
    values = _mappings(contract.get("applicability"))
    return str(values[0].get("recommendation") or "") if values else None


def _title(item: Mapping[str, Any], summary: str) -> str:
    title = _short(item.get("title"), 100)
    if title:
        return title
    if summary:
        return _short(summary.split(".", 1)[0], 100)
    return "Архивный материал"


def _short(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, Mapping)]
