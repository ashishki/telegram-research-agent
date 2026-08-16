"""Reader-facing rendering independent from Telegram transport."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def render_payload(payload: Mapping[str, Any], *, mode: str) -> str:
    gate = _mapping(payload.get("answer_gate"))
    if bool(gate.get("external_verification_required")) and not bool(gate.get("current_claim_allowed", True)):
        return _render_current_boundary(payload)
    decision = _mapping(payload.get("project_decision"))
    project_fit = _mapping(payload.get("project_fit"))
    if decision and str(project_fit.get("project_name") or "").strip():
        return _render_project_decision(payload)
    if mode == "brief":
        return _render_brief(payload)
    return _render_research(payload)


def render_project_clarification(project_names: Sequence[str] = ()) -> str:
    choices = [name for name in project_names if str(name).strip()][:3]
    if not choices:
        choices = ["telegram-research-agent", "AI_workflow_playbook", "Agent-Runtime-Grid"]
    return "\n".join(["К какому проекту применить находки?", "", *[f"[{name}]" for name in choices], "[Другой]"])


def _render_research(payload: Mapping[str, Any]) -> str:
    professional = _mapping(payload.get("professional_answer"))
    findings = _findings(professional, payload)
    project = _mapping(payload.get("project_fit"))
    action = _text(professional.get("recommended_action")) or _first_step(payload)
    unknowns = _strings(professional.get("uncertainty")) or _strings(payload.get("unknowns"))
    lines = [
        "Короткий вывод", _text(professional.get("short_answer")) or _text(payload.get("direct_answer")) or "Недостаточно данных для уверенного вывода.", "",
        "Что найдено", *(findings or ["- Релевантных локальных источников не найдено."]), "",
        "Почему это важно тебе", _project_relation(project), "",
        "Что сделать", action or "Не превращать сигнал в действие без более точных доказательств.", "",
        "Где доказательства слабые", *[f"- {_localize_unknown(item)}" for item in (unknowns[:3] or ["Нужна дополнительная проверка."])], "",
        "Источники", *(_source_lines(payload) or ["- локальных источников нет"]),
    ]
    return _compact(lines)


def _render_brief(payload: Mapping[str, Any]) -> str:
    professional = _mapping(payload.get("professional_answer"))
    workflow = _mapping(professional.get("workflow_section"))
    cases = _findings(professional, payload)[:3]
    lines = [
        "Тезис", _text(workflow.get("thesis")) or _text(professional.get("short_answer")) or _text(payload.get("direct_answer")), "",
        "Кейсы", *(cases or ["- Сильный кейс в локальном архиве не найден."]), "",
        "Контраргумент", _text(workflow.get("counterargument")) or "Повтор Telegram-сигнала не является независимым подтверждением.", "",
        "Практический вывод", _text(workflow.get("practical_conclusion")) or _text(professional.get("recommended_action")) or "Проверить первоисточник перед сильным публичным утверждением.", "",
        "Что проверить", "Свежесть, первичность и независимость источников.", "",
        "Источники", *(_source_lines(payload) or ["- локальных источников нет"]),
    ]
    return _compact(lines)


def _render_project_decision(payload: Mapping[str, Any]) -> str:
    decision = _mapping(payload.get("project_decision"))
    project = _mapping(payload.get("project_fit"))
    claims = _mappings(_mapping(payload.get("claim_ledger")).get("claims"))
    claim_lines = [f"- {_text(item.get('claim_text'))}" for item in claims[:4] if _text(item.get("claim_text"))]
    recommendation = _text(decision.get("grounded_recommendation")) or "Не принимать проектное решение: прямой связи с источниками недостаточно."
    next_action = _text(decision.get("next_action"))
    lines = [
        "Решение", recommendation, "",
        "Что найдено в источниках", *(claim_lines or ["- Поддержанных утверждений для проектного решения нет."]), "",
        "Контекст проекта", _project_relation(project), "",
        "Цель проекта", _localize_project_goal(_text(decision.get("project_goal"))) or "не зафиксирована", "",
        "Главный риск", _text(decision.get("current_blocker")) or "не зафиксирован", "",
        "Критерий успеха", _text(decision.get("acceptance_criterion")) or "Есть наблюдаемый результат, связанный с цитируемым источником.", "",
        "Что изменило бы решение", _text(decision.get("next_proof")) or "Новый прямой источник или результат ограниченного эксперимента.", "",
        "Где доказательства слабые", *[f"- {_localize_unknown(item)}" for item in (_strings(payload.get("unknowns"))[:3] or ["Независимость источников не подтверждена."])], "",
        "Источники", *(_source_lines(payload) or ["- локальных источников нет"]),
    ]
    if next_action and next_action != recommendation:
        insert_at = lines.index("Критерий успеха")
        lines[insert_at:insert_at] = ["Следующий шаг", next_action, ""]
    return _compact(lines)


def _render_current_boundary(payload: Mapping[str, Any]) -> str:
    return _compact([
        "Я не могу подтвердить актуальный факт по локальному архиву.",
        "Внешняя проверка не запускалась, поэтому архивный контекст не выдается за текущую истину.", "",
        "Что есть в архиве", *(_findings({}, payload) or ["- Релевантного исторического контекста нет."]), "",
        "Что нужно для точного ответа", "Отдельно разрешить проверку официального первоисточника.", "",
        "Источники из архива", *(_source_lines(payload) or ["- локальных источников нет"]),
    ])


def _findings(professional: Mapping[str, Any], payload: Mapping[str, Any]) -> list[str]:
    result = []
    for item in _mappings(professional.get("key_findings"))[:4]:
        claim = _text(item.get("claim"))
        citation = _text(item.get("citation"))
        if claim:
            result.append(f"- {claim}" + (f" {citation}" if citation else ""))
    if result:
        return result
    archive = _mapping(payload.get("archive_evidence"))
    for item in _mappings(archive.get("items"))[:4]:
        snippet = _text(item.get("snippet") or item.get("content"))[:260]
        url = _text(item.get("source_url") or item.get("telegram_url"))
        if snippet:
            result.append(f"- {snippet}" + (f" {url}" if url else ""))
    return result


def _source_lines(payload: Mapping[str, Any]) -> list[str]:
    archive = _mapping(payload.get("archive_evidence"))
    result = []
    for item in _mappings(archive.get("items"))[:6]:
        date = _text(item.get("posted_at"))[:10] or "дата неизвестна"
        channel = _text(item.get("channel_username")).lstrip("@") or "источник"
        url = _text(item.get("source_url") or item.get("telegram_url"))
        result.append(f"- {date} @{channel}" + (f": {url}" if url else ""))
    return result


def _project_relation(project: Mapping[str, Any]) -> str:
    name = _text(project.get("project_name"))
    label = _text(project.get("relevance_label"))
    guidance = _text(project.get("guidance"))
    if not name:
        return "Проект не указан. Можно задать следующий вопрос с названием репозитория."
    if label == "direct_implication":
        return guidance or f"Есть прямая связь с {name}."
    if label in {"weak_watch", "learning_relevance"}:
        return guidance or f"Для {name} это сигнал для изучения, но действие не доказано."
    return guidance or f"Для {name} прямая связь пока не доказана."


def _first_step(payload: Mapping[str, Any]) -> str:
    steps = _mapping(payload.get("next_steps"))
    for key in ("apply", "watch", "study", "ignore"):
        values = _strings(steps.get(key))
        if values:
            return values[0]
    return ""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_text(item) for item in value if _text(item)]


def _localize_unknown(value: str) -> str:
    return {
        "approved linked-source text": "нет утверждённого текста связанного первоисточника",
        "live external freshness": "не проверена актуальность вне локального архива",
        "matching project descriptor": "не найдено точное описание проекта",
        "external verification before current claims": "нужна внешняя проверка перед текущими утверждениями",
        "current-claim freshness": "не подтверждена свежесть текущего утверждения",
        "direct project implication": "прямое влияние на проект не доказано",
        "local Telegram archive support": "слабая поддержка в локальном Telegram-архиве",
        "sufficient cited proof for the requested claim": "недостаточно цитируемого доказательства для запрошенного утверждения",
        "target project selection": "нужно выбрать целевой проект",
    }.get(value, value)


def _localize_project_goal(value: str) -> str:
    replacements = {
        "support triage": "разбор обращений",
        "guardrails": "защитные ограничения",
        "human approval": "подтверждение человеком",
        "evaluation": "оценка качества",
    }
    result = value
    for source, target in replacements.items():
        result = result.replace(source, target)
    return result


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _compact(lines: Sequence[str]) -> str:
    output = []
    previous_blank = False
    for value in lines:
        line = str(value or "").strip()
        blank = not line
        if blank and previous_blank:
            continue
        output.append(line)
        previous_blank = blank
    return "\n".join(output).strip()
