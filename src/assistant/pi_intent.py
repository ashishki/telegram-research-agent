from __future__ import annotations

from typing import Literal

from llm.client import LLMClient


OperatorIntent = Literal["chat", "feedback", "reminder"]


FEEDBACK_TERMS = (
    "фидбек",
    "feedback",
    "полезно",
    "мимо",
    "слишком",
    "попробовал",
    "попробовала",
    "применил",
    "применила",
    "не интересно",
    "неинтересно",
    "wrong priority",
    "not interested",
    "too shallow",
    "useful",
    "tried",
    "applied",
)

REMINDER_TERMS = (
    "напомни",
    "напомин",
    "remind",
    "reminder",
)
QUESTION_TERMS = (
    "как",
    "что",
    "почему",
    "зачем",
    "можно",
    "how",
    "what",
    "why",
)


def classify_operator_message(
    text: str,
    *,
    input_kind: str = "text",
    llm_client: type[LLMClient] = LLMClient,
) -> dict:
    clean = " ".join(str(text or "").split())
    if not clean:
        return {"intent": "chat", "confidence": 0.0, "reason": "empty message"}

    prompt = (
        "Classify a private operator message for Hermes.\n"
        "Return JSON only: {\"intent\":\"chat|feedback|reminder\",\"confidence\":0.0,\"reason\":\"short\"}\n\n"
        "Definitions:\n"
        "- chat: a question, request for explanation, request to inspect workbook/MVP/actions/projects, or general assistant interaction.\n"
        "- feedback: the operator is reporting what was useful, wrong, too shallow, tried, applied, missed, not interesting, or what should change in future reports.\n"
        "- reminder: the operator asks Hermes to remind them later about an action, reading, watching, feedback, or follow-up.\n\n"
        "Do not classify a question about how feedback works as feedback. That is chat.\n"
        "If uncertain, choose chat.\n\n"
        f"Input kind: {input_kind}\n"
        f"Message: {clean}"
    )
    try:
        result = llm_client.complete_json(prompt=prompt, system="", category="pi_chat")
    except Exception:
        return _heuristic_intent(clean)
    if not isinstance(result, dict):
        return _heuristic_intent(clean)

    intent = str(result.get("intent") or "").strip().lower()
    if intent not in {"chat", "feedback", "reminder"}:
        return _heuristic_intent(clean)
    confidence = _safe_float(result.get("confidence"), default=0.0)
    if confidence < 0.45:
        return _heuristic_intent(clean)
    return {
        "intent": intent,
        "confidence": confidence,
        "reason": str(result.get("reason") or "").strip() or "LLM classified operator message.",
    }


def _heuristic_intent(text: str) -> dict:
    lowered = text.casefold()
    if any(term in lowered for term in REMINDER_TERMS):
        return {"intent": "reminder", "confidence": 0.65, "reason": "Reminder keyword matched."}
    if any(term in lowered for term in QUESTION_TERMS) and any(term in lowered for term in ("feedback", "фидбек")):
        return {"intent": "chat", "confidence": 0.58, "reason": "Question about feedback workflow."}
    if any(term in lowered for term in FEEDBACK_TERMS):
        return {"intent": "feedback", "confidence": 0.6, "reason": "Feedback keyword matched."}
    return {"intent": "chat", "confidence": 0.55, "reason": "Defaulted to chat."}


def _safe_float(value: object, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))
