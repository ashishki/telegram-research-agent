"""Fixture-first professional research projections; no retrieval, provider, or write calls."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def build_professional_answer(payload: Mapping[str, Any], *, workflow: str) -> dict[str, Any]:
    """Return the deterministic, citation-bound MAT-4 reader DTO."""

    gate = _mapping(payload.get("answer_gate"))
    archive = _mapping(payload.get("archive_evidence"))
    sources = _sources({"archive_evidence": archive})
    verification_required = bool(gate.get("external_verification_required"))
    answer = " ".join(str(payload.get("direct_answer") or "").split())
    return {
        "schema_version": "professional_answer.v1",
        "interaction_id": str(payload.get("interaction_id") or ""),
        "primary_workflow": workflow,
        "professional_lens": _mapping(payload.get("professional_lens")).get("selected", "neutral"),
        "answer_status": "verification_required" if verification_required else ("supported" if sources else "insufficient_evidence"),
        "short_answer": answer if not verification_required else "Требуется внешняя проверка актуального факта.",
        "key_findings": [{"claim": item["snippet"], "citation": item["source_url"]} for item in sources],
        "project_context": _mapping(payload.get("project_fit")),
        "recommended_action": None if verification_required else _first_action(payload),
        "uncertainty": _strings(payload.get("unknowns")),
        "citations": [{"source_url": item["source_url"]} for item in sources],
        "external_verification": {"required": verification_required},
        "write_performed": False,
    }


def _first_action(payload: Mapping[str, Any]) -> str | None:
    steps = payload.get("next_steps")
    if isinstance(steps, Mapping):
        for group in ("apply", "watch", "study"):
            values = steps.get(group)
            if isinstance(values, Sequence) and not isinstance(values, str) and values:
                return str(values[0])
    return None


def _strings(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def build_ai_systems_project_application_workflow(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Project bounded AI-systems evidence into one non-persisted work item."""

    answer_gate = _mapping(payload.get("answer_gate"))
    project_fit = _mapping(payload.get("project_fit"))
    sources = _sources(payload)
    text = " ".join(item["snippet"] for item in sources).casefold()
    taxonomy = [
        label
        for label, terms in {
            "eval_gap": ("eval", "evaluation", "regression"),
            "retrieval_gap": ("rag", "retrieval", "citation"),
            "context_gap": ("context", "memory"),
            "runtime_safety": ("tool", "permission", "safety", "failure"),
        }.items()
        if any(term in text for term in terms)
    ]
    if not taxonomy:
        taxonomy = ["insufficient_evidence"]
    direct_project_evidence = str(project_fit.get("relevance_label") or "") == "direct_implication"
    current_boundary = bool(answer_gate.get("external_verification_required"))
    action = None
    eval_case = None
    if direct_project_evidence and not current_boundary:
        action = "Добавить один regression case для подтвержденного failure mode."
        eval_case = "Fixture: воспроизвести failure mode и проверить, что guardrail блокирует неверный ответ."
    return {
        "schema_version": "prm_ai_systems_project_application.v1",
        "failure_taxonomy": taxonomy,
        "cited_cases": sources,
        "project_implication": project_fit.get("guidance") or "Прямое применение к проекту не подтверждено.",
        "project_action": action,
        "eval_case": eval_case,
        "uncertainty": ["недостаточно данных для более сильного вывода"] if not sources else [],
        "external_verification_required": current_boundary,
        "answer_first_boundary": (
            "Внешняя проверка нужна: текущие факты не подтверждены локально." if current_boundary else ""
        ),
        "write_performed": False,
    }


def build_writer_editor_brief_workflow(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a bounded, source-backed editor input without publishing a draft."""

    answer_gate = _mapping(payload.get("answer_gate"))
    sources = _sources(payload)
    direct_answer = " ".join(str(payload.get("direct_answer") or "").split())
    thesis = direct_answer or "Локальных источников недостаточно для сильного тезиса."
    verification_required = bool(answer_gate.get("external_verification_required"))
    cases = [
        {
            "claim": source["snippet"],
            "source_url": source["source_url"],
        }
        for source in sources
    ]
    return {
        "schema_version": "prm_writer_editor_brief.v1",
        "thesis": thesis,
        "cases": cases,
        "counterargument": (
            "Локальные Telegram-источники дают направление, но не заменяют проверку "
            "актуальных внешних фактов."
        ),
        "practical_conclusion": _practical_conclusion(payload, verification_required=verification_required),
        "sources": [{"source_url": source["source_url"]} for source in sources],
        "claims_requiring_external_verification": (
            ["Актуальные внешние факты и их выводы перед публикацией."] if verification_required else []
        ),
        "ready_for_final_post": False,
        "write_performed": False,
    }


def build_enterprise_ai_adoption_workflow(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Project local discovery evidence into a non-build-ready adoption brief."""

    sources = _sources(payload)
    project_fit = _mapping(payload.get("project_fit"))
    evidence_text = " ".join(item["snippet"] for item in sources).casefold()
    direct_project_evidence = str(project_fit.get("relevance_label") or "") == "direct_implication"
    return {
        "schema_version": "prm_enterprise_ai_adoption.v1",
        "pain_pattern": _enterprise_pain_pattern(evidence_text),
        "evidence_maturity": "telegram_discovery_only",
        "buyer_owner_signal": _enterprise_owner_signal(evidence_text),
        "relevant_project": project_fit.get("project_name") if direct_project_evidence else None,
        "project_implication": project_fit.get("guidance") or "Прямое применение к проекту не подтверждено.",
        "validation_step": "Проверить гипотезу с первичным источником или целевым пользователем до build-решения.",
        "do_not_build_boundary": "Не начинать реализацию и не считать Telegram-сигнал подтвержденным спросом.",
        "project_action": "Сформулировать одну проверяемую гипотезу для активного проекта." if direct_project_evidence else None,
        "guidance": "action" if direct_project_evidence else "watch_or_reference",
        "sources": [{"source_url": source["source_url"]} for source in sources],
        "write_performed": False,
    }


def build_learning_experiment_workflow(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Offer one non-persisted learning experiment from bounded local evidence."""

    sources = _sources(payload)
    project_fit = _mapping(payload.get("project_fit"))
    concept = str(payload.get("concept") or "контекст-инжиниринг").strip()
    return {
        "schema_version": "prm_learning_experiment.v1",
        "plain_explanation": (
            f"{concept.capitalize()} — это явный отбор и проверка информации, "
            "которую система получает перед ответом."
        ),
        "analogy": "Как рабочая папка: в нее кладут только материалы, нужные для текущей задачи.",
        "source_evidence": [{"source_url": source["source_url"], "snippet": source["snippet"]} for source in sources],
        "existing_knowledge_relation": project_fit.get("guidance") or "Связь с подтвержденным проектом пока неизвестна.",
        "experiment_proposal": "Собрать один fixture с лишним контекстом и сравнить ответ с ограниченным context pack.",
        "success_criterion": "Ответ сохраняет цитату к релевантному источнику и не использует лишний контекст.",
        "reflection_question": "Какой элемент context pack изменил ответ и почему?",
        "learning_state": "unknown",
        "persistence": {"requires_confirmation": True, "write_performed": False},
    }


def build_career_portfolio_gap_workflow(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Compare local career signals with approved portfolio evidence without inventing proof."""

    sources = _sources(payload)
    project_fit = _mapping(payload.get("project_fit"))
    answer_gate = _mapping(payload.get("answer_gate"))
    direct_project_evidence = str(project_fit.get("relevance_label") or "") == "direct_implication"
    current_market_boundary = bool(answer_gate.get("external_verification_required"))
    requirement = _career_requirement(" ".join(source["snippet"] for source in sources).casefold())
    portfolio_evidence = project_fit.get("guidance") if direct_project_evidence else "unknown"
    missing_proof = None if direct_project_evidence else "Подтвержденного portfolio-доказательства в локальном контексте нет."
    return {
        "schema_version": "prm_career_portfolio_gap.v1",
        "recurring_requirement": requirement,
        "source_evidence": [{"source_url": source["source_url"], "snippet": source["snippet"]} for source in sources],
        "current_portfolio_evidence": portfolio_evidence,
        "missing_proof": missing_proof,
        "next_portfolio_action": (
            None
            if current_market_boundary or not direct_project_evidence
            else "Добавить один проверяемый case, который демонстрирует требование на активном проекте."
        ),
        "external_verification_required": current_market_boundary,
        "market_boundary": (
            "Актуальные требования рынка нужно проверить по первичным источникам вакансий до рекомендации."
            if current_market_boundary
            else ""
        ),
        "write_performed": False,
    }


def _career_requirement(evidence_text: str) -> str:
    if any(term in evidence_text for term in ("eval", "evaluation", "evaluation")):
        return "Умение строить воспроизводимые evaluation-петли."
    if any(term in evidence_text for term in ("agent", "rag", "retrieval")):
        return "Умение обосновывать надежные agent/RAG-системы."
    return "Локальных источников недостаточно для устойчивого требования."


def _enterprise_pain_pattern(evidence_text: str) -> str:
    if any(term in evidence_text for term in ("workflow", "process", "ручн", "manual", "workaround")):
        return "Повторяющийся рабочий процесс требует ручного обхода или доработки."
    return "Локальных сигналов недостаточно, чтобы утверждать устойчивую enterprise-боль."


def _enterprise_owner_signal(evidence_text: str) -> str:
    if any(term in evidence_text for term in ("buyer", "owner", "manager", "команд", "заказчик")):
        return "В источниках есть сигнал владельца или покупателя проблемы."
    return "Владелец проблемы не подтвержден локальными источниками."


def _practical_conclusion(payload: Mapping[str, Any], *, verification_required: bool) -> str:
    if verification_required:
        return "Сначала проверить актуальные внешние факты по первичным источникам; это не финальный пост."
    next_steps = payload.get("next_steps")
    if isinstance(next_steps, Mapping):
        next_steps = [item for values in next_steps.values() if isinstance(values, Sequence) and not isinstance(values, str) for item in values]
    if isinstance(next_steps, Sequence) and not isinstance(next_steps, str) and next_steps:
        return " ".join(str(next_steps[0]).split())
    return "Использовать это как входной бриф и сверить тезис с указанными источниками."


def _sources(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    archive = _mapping(payload.get("archive_evidence"))
    sources: list[dict[str, str]] = []
    for item in archive.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        source_url = str(item.get("source_url") or "").strip()
        if source_url:
            sources.append({"source_url": source_url, "snippet": " ".join(str(item.get("snippet") or "").split())[:220]})
    return sources[:3]


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
