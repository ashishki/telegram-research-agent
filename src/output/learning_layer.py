from collections import Counter
from typing import Any, Iterable, Mapping

from output.project_relevance import _tokenize


PROJECT_LEARNING_PROJECTION_VERSION = "project-learning-projection.v1"
LEARNING_STAGES = (
    "read",
    "understood",
    "explained",
    "reproduced",
    "implemented",
    "tested",
    "project-applied",
    "measured",
    "stale",
    "prerequisite_gap",
)

_BROAD_PROJECT_TERMS = {
    "ai",
    "agent",
    "agents",
    "automation",
    "evidence",
    "implementation",
    "memory",
    "research",
    "signal",
    "signals",
    "tool",
    "tools",
    "workflow",
}


def extract_learning_gaps(posts: list[dict], projects: list[dict]) -> list[dict]:
    relevant_posts = [
        post for post in posts
        if post.get("bucket") in {"strong", "watch"}
    ]

    keyword_counts: Counter[str] = Counter()
    for post in relevant_posts:
        keyword_counts.update(_tokenize(str(post.get("content") or "")))

    covered_keywords: set[str] = set()
    for project in projects:
        description = str(project.get("description") or "")
        focus = str(project.get("focus") or "")
        covered_keywords.update(_tokenize(f"{description} {focus}"))

    gaps = [
        {
            "topic": topic,
            "frequency": frequency,
            "rationale": f"Appeared {frequency} times in strong/watch posts, not in any project focus",
            "linked_project": None,
        }
        for topic, frequency in keyword_counts.most_common()
        if frequency >= 2 and topic not in covered_keywords
    ]
    return gaps[:5]


def build_project_learning_projection(
    context: Mapping[str, Any],
    *,
    actions: Iterable[Mapping[str, Any]] | None = None,
    project_diagnostic: Mapping[str, Any] | None = None,
    decision_cards: Iterable[Mapping[str, Any]] | None = None,
    feedback_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project source-backed project and learning state without claiming mastery."""
    clean_actions = [action for action in actions or [] if isinstance(action, Mapping)]
    diagnostic = project_diagnostic if isinstance(project_diagnostic, Mapping) else {}
    feedback = feedback_context if isinstance(feedback_context, Mapping) else context.get("feedback_context") or {}
    project_intelligence = _project_intelligence(context, diagnostic, clean_actions, decision_cards or [])
    learning_intelligence = _learning_intelligence(context, clean_actions, project_intelligence, feedback)
    return {
        "schema_version": PROJECT_LEARNING_PROJECTION_VERSION,
        "week_label": context.get("week_label"),
        "source_policy": {
            "confirmed_project_implication": "requires project-specific evidence and source refs",
            "broad_overlap": "rejected_not_confirmed",
            "market_business_context": "context_only",
            "no_feedback_semantics": "unknown",
            "passive_reading": "not_mastery",
        },
        "project_intelligence": project_intelligence,
        "learning_intelligence": learning_intelligence,
    }


def _project_intelligence(
    context: Mapping[str, Any],
    diagnostic: Mapping[str, Any],
    actions: list[Mapping[str, Any]],
    decision_cards: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    confirmed = [_confirmed_implication(item) for item in _mapping_items(diagnostic.get("confirmed_leads"))]
    confirmed = [item for item in confirmed if item and not _broad_only_terms(item.get("shared_terms"))]
    weak_watches = [_weak_watch(item) for item in _mapping_items(diagnostic.get("project_watch"))]
    weak_watches.extend(_weak_close_signal(item) for item in _mapping_items(diagnostic.get("close_but_not_enough_signals"))[:4])
    tiny_pr_ideas = [_tiny_pr_idea(item) for item in _mapping_items(diagnostic.get("implementation_suggestions"))]
    return {
        "external_signals": _external_signals(context),
        "confirmed_implications": confirmed[:6],
        "weak_watches": [item for item in weak_watches if item][:8],
        "rejected_overlaps": _rejected_overlaps(diagnostic),
        "tiny_pr_ideas": [item for item in tiny_pr_ideas if item][:6],
        "stale_decisions": _stale_decisions(decision_cards),
        "research_debt": _research_debt(diagnostic),
        "repeated_themes_without_action": _repeated_themes_without_action(context, actions),
        "no_confirmed_leads_reason": str(diagnostic.get("no_confirmed_leads_reason") or "").strip(),
    }


def _learning_intelligence(
    context: Mapping[str, Any],
    actions: list[Mapping[str, Any]],
    project_intelligence: Mapping[str, Any],
    feedback: Mapping[str, Any],
) -> dict[str, Any]:
    objectives = _source_learning_objectives(context)
    objectives.extend(_action_learning_objectives(actions))
    objectives.extend(_project_learning_objectives(project_intelligence))
    objectives = _dedupe_by_id(objectives)[:16]
    stage_counts = {stage: 0 for stage in LEARNING_STAGES}
    for objective in objectives:
        stage = str(objective.get("stage") or "prerequisite_gap")
        stage_counts[stage if stage in stage_counts else "prerequisite_gap"] += 1
    return {
        "allowed_stages": list(LEARNING_STAGES),
        "stage_definitions": _stage_definitions(),
        "stage_counts": stage_counts,
        "objectives": objectives,
        "experiments": _experiment_projections(actions),
        "outcomes": _outcome_projections(actions),
        "feedback_state": "unknown" if int(feedback.get("event_count") or 0) <= 0 else "observed",
        "mastery_policy": "read is source exposure, not mastery; higher stages require feedback, outcome evidence, or test evidence",
    }


def _external_signals(context: Mapping[str, Any]) -> list[dict]:
    rows = []
    for thread, atom in _thread_atoms(context):
        source_refs = _string_values(atom.get("source_urls"))
        rows.append(
            {
                "id": f"external-signal:{atom.get('id') or len(rows) + 1}",
                "title": _clean_text(atom.get("claim")) or _clean_text(atom.get("summary")) or "Source signal",
                "thread_slug": _clean_text(thread.get("slug")),
                "atom_type": _clean_text(atom.get("atom_type")) or "unknown",
                "context_policy": _context_policy(atom),
                "source_atom_ids": _int_values([atom.get("id")]),
                "source_refs": source_refs,
                "evidence_state": "source_ref_available" if source_refs else "missing_source_ref",
            }
        )
    rows.sort(
        key=lambda item: (
            item["evidence_state"] == "source_ref_available",
            item["context_policy"] != "context_only",
            item["title"],
        ),
        reverse=True,
    )
    return rows[:10]


def _confirmed_implication(item: Mapping[str, Any]) -> dict | None:
    source_refs = _string_values(item.get("evidence_urls") or item.get("source_refs") or item.get("source_urls"))
    source_atom_ids = _int_values(item.get("source_atom_ids"))
    if not source_refs and not source_atom_ids:
        return None
    return {
        "project": _clean_text(item.get("project")) or "unknown-project",
        "repo": _clean_text(item.get("repo")),
        "thread_slug": _clean_text(item.get("thread_slug")),
        "thread_title": _clean_text(item.get("thread_title")),
        "confidence": _clean_text(item.get("confidence")) or "unknown",
        "why": _clean_text(item.get("why")),
        "next_step": _clean_text(item.get("next_step")),
        "source_refs": source_refs,
        "source_atom_ids": source_atom_ids,
        "shared_terms": _string_values(item.get("shared_terms")),
        "confirmation_state": "confirmed",
        "source_policy": "project-specific evidence with source refs required",
    }


def _weak_watch(item: Mapping[str, Any]) -> dict:
    return {
        "project": _clean_text(item.get("project")) or "unknown-project",
        "repo": _clean_text(item.get("repo")),
        "thread_slug": _clean_text(item.get("thread_slug")),
        "thread_title": _clean_text(item.get("thread_title")),
        "confidence": _clean_text(item.get("confidence")) or "watch",
        "why": _clean_text(item.get("why")),
        "next_step": _clean_text(item.get("next_step")),
        "source_refs": _string_values(item.get("evidence_urls") or item.get("source_refs") or item.get("source_urls")),
        "source_atom_ids": _int_values(item.get("source_atom_ids")),
        "shared_terms": _string_values(item.get("shared_terms")),
        "confirmation_state": "weak_watch",
        "source_policy": "not enough project-specific evidence for a confirmed lead",
    }


def _weak_close_signal(item: Mapping[str, Any]) -> dict:
    return {
        "project": _clean_text(item.get("project")) or "unknown-project",
        "thread_slug": _clean_text(item.get("thread_slug")),
        "thread_title": _clean_text(item.get("thread_title")),
        "rejected_terms": _string_values(item.get("rejected_terms")),
        "reason": _clean_text(item.get("reason")),
        "needed_evidence": _clean_text(item.get("needed_evidence")),
        "confirmation_state": "insufficient_specificity",
        "source_policy": "broad overlap is not a project lead",
    }


def _rejected_overlaps(diagnostic: Mapping[str, Any]) -> list[dict]:
    result = []
    for index, item in enumerate(_as_list(diagnostic.get("rejected_broad_overlaps")), start=1):
        if isinstance(item, Mapping):
            result.append(
                {
                    "project": _clean_text(item.get("project")) or "unknown-project",
                    "term": _clean_text(item.get("term")) or _clean_text(item.get("rejected_term")) or f"term-{index}",
                    "reason": _clean_text(item.get("reason")) or "broad_overlap_suppressed",
                    "confirmation_state": "rejected",
                }
            )
        elif str(item or "").strip():
            result.append(
                {
                    "project": "unknown-project",
                    "term": str(item).strip(),
                    "reason": "broad_overlap_suppressed",
                    "confirmation_state": "rejected",
                }
            )
    return result[:12]


def _tiny_pr_idea(item: Mapping[str, Any]) -> dict | None:
    source_refs = _string_values(item.get("source_urls") or item.get("source_refs"))
    source_atom_ids = _int_values(item.get("source_atom_ids"))
    if not source_refs and not source_atom_ids:
        return None
    return {
        "id": _clean_text(item.get("id")) or "project-idea",
        "project": _clean_text(item.get("project")) or "unknown-project",
        "title": _clean_text(item.get("title")) or _clean_text(item.get("next_step")) or "Tiny project idea",
        "suggestion_type": _clean_text(item.get("suggestion_type")) or "backlog",
        "effort": _clean_text(item.get("effort")) or "unknown",
        "next_step": _clean_text(item.get("next_step")),
        "acceptance_criteria": _string_values(item.get("acceptance_criteria")),
        "risk_caveat": _clean_text(item.get("risk_caveat")),
        "source_refs": source_refs,
        "source_atom_ids": source_atom_ids,
        "source_policy": _clean_text(item.get("source_policy")) or "source refs required before project work",
    }


def _stale_decisions(decision_cards: Iterable[Mapping[str, Any]]) -> list[dict]:
    result = []
    for index, decision in enumerate(decision_cards, start=1):
        if not isinstance(decision, Mapping):
            continue
        verdict = _clean_text(decision.get("verdict")) or "unknown"
        stale = _clean_text(decision.get("staleness_status")) == "stale" or bool(decision.get("stale"))
        if not stale and verdict not in {"defer", "watch", "verify_first"}:
            continue
        result.append(
            {
                "id": _clean_text(decision.get("id")) or f"decision-{index}",
                "title": _clean_text(decision.get("title")) or f"Decision {index}",
                "verdict": verdict,
                "review_reason": "stale_or_unresolved_watch",
                "evidence_atom_ids": _int_values(decision.get("evidence_atom_ids")),
                "next_action": _clean_text(decision.get("next_action")),
            }
        )
    return result[:8]


def _research_debt(diagnostic: Mapping[str, Any]) -> list[dict]:
    result = []
    for item in _string_values(diagnostic.get("missing_evidence")):
        result.append({"debt_type": "missing_evidence", "description": item})
    for item in _string_values(diagnostic.get("missing_config_suggestions")):
        result.append({"debt_type": "project_config_gap", "description": item})
    reason = _clean_text(diagnostic.get("no_confirmed_leads_reason"))
    if reason:
        result.append({"debt_type": "no_confirmed_project_lead", "description": reason})
    return result[:10]


def _repeated_themes_without_action(context: Mapping[str, Any], actions: list[Mapping[str, Any]]) -> list[dict]:
    action_text = " ".join(
        str(value)
        for action in actions
        for value in (action.get("title"), action.get("body"), action.get("next_step"))
        if value
    ).lower()
    counts: Counter[str] = Counter()
    atom_ids_by_term: dict[str, list[int]] = {}
    for _thread, atom in _thread_atoms(context):
        text = " ".join(
            str(value)
            for value in (
                atom.get("claim"),
                atom.get("summary"),
                atom.get("why_it_matters"),
                " ".join(_string_values(atom.get("tools"))),
                " ".join(_string_values(atom.get("practices"))),
            )
            if value
        )
        terms = _tokenize(text)
        for term in terms:
            counts[term] += 1
            atom_id = _safe_int(atom.get("id"))
            if atom_id:
                atom_ids_by_term.setdefault(term, [])
                if atom_id not in atom_ids_by_term[term]:
                    atom_ids_by_term[term].append(atom_id)
    result = []
    for term, frequency in counts.most_common():
        if frequency < 2 or term in action_text or term in _BROAD_PROJECT_TERMS:
            continue
        result.append(
            {
                "theme": term,
                "frequency": frequency,
                "source_atom_ids": atom_ids_by_term.get(term, [])[:8],
                "reason": "appears repeatedly in source atoms but has no matching action text",
            }
        )
        if len(result) >= 8:
            break
    return result


def _source_learning_objectives(context: Mapping[str, Any]) -> list[dict]:
    objectives = []
    for _thread, atom in _thread_atoms(context):
        atom_id = _safe_int(atom.get("id"))
        source_refs = _string_values(atom.get("source_urls"))
        stale = _clean_text(atom.get("staleness_status")) == "stale"
        objectives.append(
            {
                "id": f"learning-objective:atom:{atom_id or len(objectives) + 1}",
                "topic": _clean_text(atom.get("claim")) or _clean_text(atom.get("summary")) or "Source-backed topic",
                "stage": "stale" if stale else ("read" if source_refs else "prerequisite_gap"),
                "target_stage": _target_stage_for_atom(atom),
                "stage_evidence": "source atom with source refs" if source_refs else "missing source refs",
                "source_atom_ids": [atom_id] if atom_id else [],
                "source_refs": source_refs,
                "feedback_state": "unknown",
                "mastery_claim": "not_claimed",
            }
        )
    return objectives[:8]


def _action_learning_objectives(actions: list[Mapping[str, Any]]) -> list[dict]:
    objectives = []
    for index, action in enumerate(actions, start=1):
        action_id = _clean_text(action.get("id") or action.get("target_ref")) or f"action-{index}"
        source_refs = _string_values(action.get("source_urls") or action.get("source_refs"))
        atom_ids = _int_values(action.get("source_atom_ids") or action.get("evidence_atom_ids"))
        objectives.append(
            {
                "id": f"learning-objective:action:{action_id}",
                "topic": _clean_text(action.get("title")) or f"Action {index}",
                "stage": _stage_from_action(action),
                "target_stage": _target_stage_for_action(action),
                "stage_evidence": _stage_evidence_for_action(action),
                "source_atom_ids": atom_ids,
                "source_refs": source_refs,
                "feedback_state": "observed" if _feedback_types(action) else "unknown",
                "mastery_claim": "not_claimed" if not _feedback_types(action) else "evidence_bounded",
            }
        )
    return objectives


def _project_learning_objectives(project_intelligence: Mapping[str, Any]) -> list[dict]:
    objectives = []
    for idea in _mapping_items(project_intelligence.get("tiny_pr_ideas")):
        objectives.append(
            {
                "id": f"learning-objective:project:{_clean_text(idea.get('id')) or len(objectives) + 1}",
                "topic": _clean_text(idea.get("title")) or "Project application",
                "stage": "prerequisite_gap",
                "target_stage": "project-applied",
                "stage_evidence": "project idea exists, but no implementation/test feedback is recorded",
                "source_atom_ids": _int_values(idea.get("source_atom_ids")),
                "source_refs": _string_values(idea.get("source_refs")),
                "feedback_state": "unknown",
                "mastery_claim": "not_claimed",
            }
        )
    return objectives


def _experiment_projections(actions: list[Mapping[str, Any]]) -> list[dict]:
    result = []
    for index, action in enumerate(actions, start=1):
        if _clean_text(action.get("action_kind")) != "experiment" and _clean_text(action.get("scope")) != "experiment":
            continue
        action_id = _clean_text(action.get("id")) or f"action-{index}"
        result.append(
            {
                "id": f"experiment:{action_id}",
                "action_id": action_id,
                "title": _clean_text(action.get("title")) or f"Experiment {index}",
                "success_criterion": _clean_text(action.get("success_criterion")),
                "status": "observed_feedback" if _feedback_types(action) else "planned_unknown_outcome",
                "source_atom_ids": _int_values(action.get("source_atom_ids") or action.get("evidence_atom_ids")),
                "source_refs": _string_values(action.get("source_urls") or action.get("source_refs")),
                "outcome_policy": _clean_text(action.get("outcome_policy")) or "no outcome without feedback",
            }
        )
    return result[:8]


def _outcome_projections(actions: list[Mapping[str, Any]]) -> list[dict]:
    result = []
    for index, action in enumerate(actions, start=1):
        feedback_types = _feedback_types(action)
        outcome_evidence = _string_values(action.get("outcome_evidence"))
        measured = any(kind in feedback_types for kind in {"useful", "applied_to_project", "tested", "measured"}) or bool(outcome_evidence)
        action_id = _clean_text(action.get("id")) or f"action-{index}"
        result.append(
            {
                "id": f"outcome:{action_id}",
                "action_id": action_id,
                "title": _clean_text(action.get("title")) or f"Outcome {index}",
                "outcome_state": "observed" if measured else "unknown",
                "feedback_types": feedback_types,
                "evidence": outcome_evidence,
                "no_feedback_semantics": "unknown_not_negative" if not feedback_types else "observed_feedback",
            }
        )
    return result[:8]


def _stage_from_action(action: Mapping[str, Any]) -> str:
    explicit = _clean_text(action.get("learning_stage") or action.get("stage"))
    if explicit in LEARNING_STAGES and (explicit in {"read", "prerequisite_gap"} or _has_completion_evidence(action)):
        return explicit
    if _clean_text(action.get("staleness_status")) == "stale" or bool(action.get("stale")):
        return "stale"
    feedback_types = _feedback_types(action)
    if "measured" in feedback_types:
        return "measured"
    if "applied_to_project" in feedback_types or "project-applied" in feedback_types:
        return "project-applied"
    if "tested" in feedback_types:
        return "tested"
    if "implemented" in feedback_types:
        return "implemented"
    if "reproduced" in feedback_types or "tried" in feedback_types:
        return "reproduced"
    if "explained" in feedback_types:
        return "explained"
    if "understood" in feedback_types or "useful" in feedback_types:
        return "understood"
    if "read" in feedback_types:
        return "read"
    if not _string_values(action.get("source_urls") or action.get("source_refs")) and not _int_values(
        action.get("source_atom_ids") or action.get("evidence_atom_ids")
    ):
        return "prerequisite_gap"
    return "read"


def _target_stage_for_action(action: Mapping[str, Any]) -> str:
    text = " ".join(
        str(value or "").lower()
        for value in (action.get("title"), action.get("body"), action.get("next_step"), action.get("success_criterion"))
    )
    if "measure" in text or "metric" in text:
        return "measured"
    if "test" in text or "pytest" in text or "benchmark" in text:
        return "tested"
    if "project" in text or "repo" in text:
        return "project-applied"
    if "implement" in text or "patch" in text or "code" in text:
        return "implemented"
    if "explain" in text or "note" in text:
        return "explained"
    if "try" in text or "reproduce" in text:
        return "reproduced"
    return "understood"


def _target_stage_for_atom(atom: Mapping[str, Any]) -> str:
    atom_type = _clean_text(atom.get("atom_type")) or ""
    if atom_type in {"engineering_practice", "tool_capability"}:
        return "implemented"
    if atom_type in {"market_signal", "business_signal", "opportunity_signal"}:
        return "understood"
    return "explained"


def _stage_evidence_for_action(action: Mapping[str, Any]) -> str:
    feedback_types = _feedback_types(action)
    if feedback_types:
        return f"feedback: {', '.join(feedback_types)}"
    if _has_completion_evidence(action):
        return "completion evidence recorded"
    return "no confirmed feedback or outcome evidence"


def _stage_definitions() -> dict[str, str]:
    return {
        "read": "source was read or queued with source refs; this is not mastery",
        "understood": "operator feedback or notes show the idea was understood",
        "explained": "operator produced a reusable explanation or note",
        "reproduced": "operator tried or reproduced the behavior",
        "implemented": "operator implemented the idea in code or workflow",
        "tested": "implementation or claim has test evidence",
        "project-applied": "idea was applied to an active project with source/outcome refs",
        "measured": "outcome has measured result or metric",
        "stale": "objective needs refresh before use",
        "prerequisite_gap": "missing source, feedback, implementation, or test evidence",
    }


def _thread_atoms(context: Mapping[str, Any]) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    rows = []
    seen: set[str] = set()
    for thread in context.get("threads") or []:
        if not isinstance(thread, Mapping):
            continue
        for atom in thread.get("atoms") or []:
            if not isinstance(atom, Mapping):
                continue
            key = str(atom.get("id") or f"{thread.get('slug')}:{len(rows)}")
            if key in seen:
                continue
            seen.add(key)
            rows.append((thread, atom))
    return rows


def _context_policy(atom: Mapping[str, Any]) -> str:
    atom_type = (_clean_text(atom.get("atom_type")) or "").lower()
    if any(marker in atom_type for marker in ("market", "business", "opportunity", "demand")):
        return "context_only"
    return "source_backed"


def _feedback_types(action: Mapping[str, Any]) -> list[str]:
    return _string_values(action.get("feedback_types") or action.get("confirmed_feedback_types"))


def _has_completion_evidence(action: Mapping[str, Any]) -> bool:
    return bool(
        _feedback_types(action)
        or _string_values(action.get("outcome_evidence"))
        or _clean_text(action.get("completed_at"))
        or _clean_text(action.get("test_result"))
    )


def _broad_only_terms(value: object) -> bool:
    terms = [str(term).strip().lower() for term in _as_list(value) if str(term or "").strip()]
    return bool(terms) and all(term in _BROAD_PROJECT_TERMS for term in terms)


def _mapping_items(value: object) -> list[Mapping[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, Mapping)]


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _string_values(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        values = value
    elif value is None:
        return []
    else:
        values = [value]
    result = []
    seen = set()
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _int_values(value: object) -> list[int]:
    if isinstance(value, (list, tuple, set)):
        values = value
    elif value is None:
        return []
    else:
        values = [value]
    result = []
    seen = set()
    for item in values:
        number = _safe_int(item)
        if not number or number in seen:
            continue
        seen.add(number)
        result.append(number)
    return result


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _clean_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _dedupe_by_id(items: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for item in items:
        item_id = str(item.get("id") or "")
        if item_id in seen:
            continue
        seen.add(item_id)
        result.append(item)
    return result
