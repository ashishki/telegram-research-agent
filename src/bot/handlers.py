import json
import hashlib
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib import error
from uuid import uuid4

from assistant.pi_chat import answer_pi_chat
from assistant.pi_facade import PersonalIntelligenceFacade
from assistant.pi_intent import classify_operator_message
from assistant.operator_context import build_operator_context, validate_operator_context
from assistant.project_context import load_project_descriptors
from assistant.prm_chat_display import render_prm_chat_answer
from assistant.prm_refresh_receipt import build_refresh_receipt, render_refresh_receipt
from db.reaction_fast_lane import build_reaction_fast_lane_receipt, build_reaction_preference_proposal, render_operator_reaction_receipt
from assistant.memory_research import (
    MemoryResearchBudget,
    answer_memory_research,
    render_memory_research_answer,
    render_memory_research_brief,
)
from assistant.pi_tools import call_pi_tool
from assistant.rag_answer_gate import assess_rag_answer_gate
from assistant.prm_post_answer_actions import build_post_answer_actions
from bot.telegram_delivery import _send_text_internal, send_document, send_report_preview, send_text
from config.settings import PROJECT_ROOT, Settings
from db.migrate import record_feedback, record_post_tag
from llm.client import LLMClient, suppress_usage_recording
from output.generate_digest import _compute_week_label, run_digest
from output.generate_insight import generate_insight
from output.generate_study_plan import generate_study_plan, mark_study_complete
from output.ai_report_feedback_intake import (
    apply_confirmed_feedback_intake,
    create_feedback_intake,
    discard_feedback_intake,
)
from output.mvp_weekly_pipeline import run_mvp_weekly_pipeline, source_mix_summary
from output.operator_reminders import (
    cancel_reminder,
    create_reminder,
    format_reminder_due_at,
    list_pending_reminders,
    parse_reminder_request,
)


LOGGER = logging.getLogger(__name__)
BOT_RUNTIME_LEGACY = "legacy"
BOT_RUNTIME_PRM_ASSISTANT = "prm_assistant"
BOT_RUNTIME_MODES = frozenset({BOT_RUNTIME_LEGACY, BOT_RUNTIME_PRM_ASSISTANT})
PRM_SAFE_COMMANDS = frozenset(
    {
        "/start",
        "/help",
        "/weekly",
        "/actions",
        "/explain",
        "/projects",
        "/mvp",
        "/strategy",
        "/codex",
        "/chat",
        "/hermes",
        "/ask",
        "/auto",
        "/auto_voice",
        "/research",
        "/brief",
        "/costs",
        "/status",
        "/refresh",
        "/reactions",
    }
)
QUESTION_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
TELEGRAM_POST_URL_RE = re.compile(r"^https?://t\.me/([A-Za-z0-9_]+)/(\d+)(?:\?.*)?$", re.IGNORECASE)
MARKDOWN_V2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"
WEEK_LABEL_RE = re.compile(r"^\d{4}-W\d{2}$")
COMMAND_DOCS: dict[str, tuple[str, str]] = {
    "/weekly [week]": ("handle_weekly", "Show Hermes weekly workbook summary"),
    "/actions [week]": ("handle_actions", "Show one to three workbook actions"),
    "/explain <query>": ("handle_explain", "Explain a curated workbook signal"),
    "/projects [week] [name]": ("handle_projects", "Show workbook project actions"),
    "/mvp [week]": ("handle_mvp", "Show MVP Radar status and missing evidence"),
    "/strategy [week]": ("handle_strategy", "Show Strategy Reviewer advisory notes"),
    "/codex [focus]": ("handle_codex", "Prepare a Codex prompt draft; never executes Codex"),
    "/chat <message>": ("handle_chat", "Ask Hermes; LLM may call bounded read-only PI tools"),
    "/hermes <message>": ("handle_chat", "Ask Hermes; alias for /chat"),
    "/auto <message>": ("handle_auto", "Choose PRM-safe tool automatically for an ordinary message"),
    "/research <question>": ("handle_research", "Run local-only compact PRM research over archive/context pack"),
    "/brief <question>": ("handle_research_brief", "Run local-only editor brief with source-backed points"),
    "/remind <when> <task>": ("handle_remind", "Create a daily-check-in reminder"),
    "/reminders": ("handle_reminders", "List pending reminders"),
    "/remind_cancel <id>": ("handle_remind_cancel", "Cancel a pending reminder"),
    "/digest": ("handle_digest", "Show the current weekly brief"),
    "/topics": ("handle_topics", "List the strongest tracked topics"),
    "/insight": ("handle_insight", "Show retrospective project insights"),
    "/project <name>": ("handle_project", "Find an active project by partial name"),
    "/ask <question>": ("handle_ask", "Ask Hermes through bounded curated PI tools"),
    "/study [refresh]": ("handle_study", "Show the weekly study plan or rebuild it"),
    "/study_done [notes]": ("handle_study_done", "Mark this week's study plan as completed"),
    "/costs": ("handle_costs", "Show LLM usage and cost statistics"),
    "/run_digest [force]": ("handle_run_digest", "Generate a fresh weekly brief; use force to resend delivery for the same week"),
    "/run_mvp_weekly": ("handle_run_mvp_weekly", "Generate the weekly MVP artifact"),
    "/status": ("handle_status", "Show database and pipeline status"),
    "/mark_useful <post_id|link>": ("handle_mark_useful", "Record acted_on feedback"),
    "/mark_skipped <post_id|link>": ("handle_mark_skipped", "Record skipped feedback"),
    "/feedback [week] <text>": ("handle_feedback", "Draft AI workbook feedback for confirmation"),
    "/feedback_voice [week] <transcript>": ("handle_feedback_voice", "Draft transcribed voice feedback for confirmation"),
    "/feedback_confirm <draft_id>": ("handle_feedback_confirm", "Confirm drafted AI workbook feedback"),
    "/feedback_discard <draft_id>": ("handle_feedback_discard", "Discard drafted AI workbook feedback"),
    "/tag <post_id|link> <tag>": ("handle_tag", "Save a tag: strong, interesting, try, funny, low, later"),
    "/mark_strong <post_id|link>": ("handle_mark_strong", "Mark a post as strong"),
    "/mark_interesting <post_id|link>": ("handle_mark_interesting", "Mark a post as interesting"),
    "/mark_try <post_id|link>": ("handle_mark_try", "Mark a post as worth trying in a project"),
    "/mark_funny <post_id|link>": ("handle_mark_funny", "Mark a post as cultural or funny"),
    "/mark_low <post_id|link>": ("handle_mark_low", "Mark a post as low signal"),
    "/mark_later <post_id|link>": ("handle_mark_later", "Mark a post to revisit later"),
}

TAG_ALIASES = {
    "strong": "strong",
    "interesting": "interesting",
    "try": "try_in_project",
    "try_in_project": "try_in_project",
    "funny": "funny",
    "low": "low_signal",
    "low_signal": "low_signal",
    "later": "read_later",
    "read_later": "read_later",
}
_RESEARCH_DIALOG_STATE: dict[str, dict[str, object]] = {}
_RESEARCH_DIALOG_MODE_STATE: dict[str, str] = {}
_MAX_RESEARCH_DIALOGS = 100
_RESEARCH_DIALOG_TTL = timedelta(minutes=30)


def _get_bot_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _escape_markdown_v2(text: str) -> str:
    escaped = []
    for char in text:
        if char in MARKDOWN_V2_SPECIAL_CHARS:
            escaped.append(f"\\{char}")
        else:
            escaped.append(char)
    return "".join(escaped)


def send_message(
    token: str,
    chat_id: str,
    text: str,
    parse_mode: str | None = "MarkdownV2",
    escape_markdown: bool = True,
    reply_markup: dict | None = None,
) -> None:
    should_escape = escape_markdown and str(parse_mode or "").casefold() == "markdownv2"
    message_text = _escape_markdown_v2(text) if should_escape else text
    try:
        kwargs: dict[str, object] = {
            "chat_id": chat_id,
            "text": message_text,
            "token": token,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        _send_text_internal(**kwargs)
    except Exception:
        LOGGER.warning("Failed to send Telegram message to chat_id=%s", chat_id, exc_info=True)


def send_file(token: str, chat_id: str, filepath: str, caption: str = "") -> None:
    try:
        send_document(chat_id=chat_id, file_path=filepath, caption=caption, token=token)
    except Exception:
        LOGGER.warning("Failed to send Telegram document chat_id=%s file=%s", chat_id, filepath, exc_info=True)


def _with_db(settings: Settings) -> sqlite3.Connection:
    connection = sqlite3.connect(settings.db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA journal_mode = WAL;")
    return connection


def _friendly_handler_error(chat_id: str) -> None:
    send_message(_get_bot_token(), chat_id, "The command could not be processed right now. Try again later.", parse_mode=None)


def _telegram_provider_egress_allowed() -> bool:
    value = os.environ.get("PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS", "").strip().casefold()
    return value in {"1", "true", "yes", "approved"}


def _send_telegram_provider_egress_required(chat_id: str) -> None:
    lines = [
        "Telegram /chat is LLM-backed and provider egress is not approved for this runtime.",
        "Send ordinary text for auto local routing, or use /research <question> for local-only RAG.",
        "If you intentionally want an LLM-backed Telegram test, set PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1 before startup.",
        "No provider call was made.",
    ]
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def _telegram_auto_llm_router_allowed() -> bool:
    value = os.environ.get("PRM_TELEGRAM_AUTO_LLM_ROUTER", "").strip().casefold()
    return value in {"1", "true", "yes", "approved"} and _telegram_provider_egress_allowed()


def _telegram_rag_llm_synthesis_allowed() -> bool:
    value = os.environ.get("PRM_TELEGRAM_RAG_LLM_SYNTHESIS", "").strip().casefold()
    return value in {"1", "true", "yes", "approved"} and _telegram_provider_egress_allowed()


def _telegram_hybrid_retrieval_allowed() -> bool:
    value = os.environ.get("PRM_ARCHIVE_HYBRID_RETRIEVAL", "").strip().casefold()
    return value in {"1", "true", "yes", "approved"}


def _telegram_vector_index_path() -> str:
    return os.environ.get("PRM_ARCHIVE_VECTOR_INDEX_PATH", "").strip()


def _route_auto_message(chat_id: str, text: str, *, input_kind: str = "text") -> dict[str, object]:
    clean = _clean_operator_text(text)
    key = _dialog_key(chat_id)
    entry = _active_dialog_entry(key)
    summaries = entry.get("summaries") if isinstance(entry, Mapping) else []
    previous_question = str(summaries[-1] if isinstance(summaries, list) and summaries else "")
    previous_mode = _RESEARCH_DIALOG_MODE_STATE.get(key, "")
    fallback = _deterministic_auto_route(clean, previous_question=previous_question, previous_mode=previous_mode)
    if fallback.get("mode") == "clarify":
        return {**fallback, "router": "deterministic_ambiguous", "model_call_attempted": False}
    hard_boundary = _hard_local_research_route(clean, previous_question=previous_question, previous_mode=previous_mode)
    if hard_boundary is not None:
        return {**hard_boundary, "router": "deterministic_hard_gate", "model_call_attempted": False}
    if not _telegram_auto_llm_router_allowed():
        return {**fallback, "router": "deterministic", "model_call_attempted": False}

    prompt = (
        "Choose the safest tool for a private Telegram research assistant. Return JSON only.\n"
        "Allowed modes:\n"
        "- research: local archive/context answer with citations; best for questions about what the archive says, project gates, current-fact boundaries, and evidence lookup.\n"
        "- brief: local source-backed editor brief; best for requests to prepare theses, angles, source packets, drafts-for-post inputs, or social post research.\n"
        "- chat: LLM-backed conversational synthesis; use only for freeform generation, rewriting, or final prose that cannot be handled as local cited research.\n\n"
        "Rules:\n"
        "- Prefer brief over chat when the user asks for post тезисы, опорные тезисы, source packet, редакторский бриф, or materials for social posts.\n"
        "- Prefer research over chat when the user asks what their archive/posts said, what sources exist, or asks a current fact that must be refused/freshness-gated.\n"
        "- For short follow-ups, keep the previous mode unless the message clearly asks for another output.\n"
        "- Do not choose chat merely because the wording is informal.\n\n"
        "- For research or brief, include retrieval_query: 2-8 concise search terms that express the user's topic as it may occur in sources. Translate/transliterate when useful. Do not turn it into an answer or add facts.\n"
        'Return exactly: {"mode":"research|brief|chat","confidence":0.0,"reason":"short","retrieval_query":"optional concise terms"}\n\n'
        f"Input kind: {input_kind}\n"
        f"Previous mode: {previous_mode or 'none'}\n"
        f"Previous question: {previous_question or 'none'}\n"
        f"Message: {clean}"
    )
    try:
        result = LLMClient.complete_json(prompt=prompt, system="", category="pi_chat", max_tokens=200)
    except Exception as exc:
        return {**fallback, "router": "deterministic_after_llm_error", "model_call_attempted": True, "error": type(exc).__name__}
    if not isinstance(result, Mapping):
        return {**fallback, "router": "deterministic_after_invalid_llm", "model_call_attempted": True}
    mode = str(result.get("mode") or "").strip().casefold()
    confidence = _safe_confidence(result.get("confidence"))
    if mode not in {"research", "brief", "chat"} or confidence < 0.45:
        return {**fallback, "router": "deterministic_after_low_confidence_llm", "model_call_attempted": True}
    if mode == "chat" and not _llm_chat_route_allowed(clean):
        return {
            **fallback,
            "router": "deterministic_after_llm_chat_guard",
            "model_call_attempted": True,
            "llm_rejected_mode": "chat",
            "llm_reason": str(result.get("reason") or "").strip(),
        }
    return {
        "mode": mode,
        "confidence": confidence,
        "reason": str(result.get("reason") or "LLM auto-router").strip(),
        "retrieval_query": _bounded_retrieval_query(result.get("retrieval_query")),
        "router": "llm",
        "model_call_attempted": True,
        "previous_mode": previous_mode,
        "previous_question": previous_question,
    }


def _bounded_retrieval_query(value: object) -> str:
    clean = _clean_operator_text(value)
    if not clean:
        return ""
    return " ".join(clean.split()[:8])[:240]


def _named_project_from_message(value: object) -> str:
    """Resolve only an explicitly named configured project; never infer one."""

    normalized_message = re.sub(r"[^a-z0-9]+", "", _clean_operator_text(value).casefold())
    if not normalized_message:
        return ""
    try:
        descriptors = load_project_descriptors(PROJECT_ROOT / "src" / "config" / "projects.yaml")
    except ValueError:
        return ""
    for descriptor in descriptors:
        name = _clean_operator_text(descriptor.get("name"))
        repo = _clean_operator_text(descriptor.get("repo"))
        aliases = (name, repo, repo.rsplit("/", 1)[-1])
        for alias in aliases:
            normalized_alias = re.sub(r"[^a-z0-9]+", "", alias.casefold())
            if len(normalized_alias) >= 5 and normalized_alias in normalized_message:
                return name
    return ""


def _hard_local_research_route(text: str, *, previous_question: str = "", previous_mode: str = "") -> dict[str, object] | None:
    gate = assess_rag_answer_gate(text, source_count=1)
    reason = str(gate.get("reason") or "")
    if reason not in {"current_external_fact_required", "unsupported_project_state_claim"}:
        return None
    return {
        "mode": "research",
        "confidence": 0.95,
        "reason": f"Hard local research gate: {reason}.",
        "previous_mode": previous_mode,
        "previous_question": previous_question,
    }


def _deterministic_auto_route(text: str, *, previous_question: str = "", previous_mode: str = "") -> dict[str, object]:
    clean = _clean_operator_text(text)
    lowered = clean.casefold()
    if _needs_auto_clarification(lowered, previous_question=previous_question, previous_mode=previous_mode):
        return {
            "mode": "clarify",
            "confidence": 0.0,
            "reason": "The request does not identify a research or brief goal.",
            "previous_mode": previous_mode,
            "previous_question": previous_question,
        }
    if _is_research_followup(clean) and previous_mode in {"brief", "research"}:
        return {
            "mode": previous_mode,
            "confidence": 0.66,
            "reason": "Short follow-up keeps previous mode.",
            "previous_mode": previous_mode,
            "previous_question": previous_question,
        }
    if _looks_like_editor_brief_request(lowered):
        return {
            "mode": "brief",
            "confidence": 0.72,
            "reason": "Editor/source-brief wording matched.",
            "previous_mode": previous_mode,
            "previous_question": previous_question,
        }
    return {
        "mode": "research",
        "confidence": 0.55,
        "reason": "Default safe local archive research route.",
        "previous_mode": previous_mode,
        "previous_question": previous_question,
    }


def _needs_auto_clarification(text: str, *, previous_question: str, previous_mode: str) -> bool:
    if previous_question or previous_mode:
        return False
    return text.strip(" .!?") in {
        "помоги",
        "нужна помощь",
        "помощь",
        "help",
    }


def _looks_like_editor_brief_request(lowered: str) -> bool:
    return any(
        marker in lowered
        for marker in (
            "тезис",
            "опорн",
            "для пост",
            "пост для",
            "пост в соц",
            "материал для",
            "соцсет",
            "редактор",
            "бриф",
            "source packet",
            "editor brief",
            "social post",
            "draft inputs",
            "углы",
            "angles",
        )
    )


def _llm_chat_route_allowed(text: str) -> bool:
    lowered = _clean_operator_text(text).casefold()
    if _contains_research_anchor(lowered) or _looks_like_editor_brief_request(lowered):
        return False
    return any(
        marker in lowered
        for marker in (
            "перепиши",
            "переформулируй",
            "сократи",
            "сделай короче",
            "сделай проще",
            "улучши текст",
            "rewrite",
            "rephrase",
            "shorten",
            "make this clearer",
            "make it simpler",
        )
    )


def _safe_confidence(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))


def _dialog_key(chat_id: str) -> str:
    return hashlib.sha256(f"prm.research-dialog.v1:{chat_id}".encode("utf-8")).hexdigest()[:24]


def _resolve_research_dialog_question(chat_id: str, question: str, *, now: datetime | None = None) -> dict[str, str | bool]:
    clean_question = _clean_operator_text(question)
    key = _dialog_key(chat_id)
    entry = _active_dialog_entry(key, now=now)
    summaries = entry.get("summaries") if isinstance(entry, Mapping) else []
    previous = str(summaries[-1] if isinstance(summaries, list) and summaries else "")
    if previous and _is_research_followup(clean_question):
        effective = _clean_operator_text(f"{previous}. Уточнение: {clean_question}")
        return {
            "used": True,
            "question": clean_question,
            "previous_question": previous,
            "effective_question": effective,
        }
    return {
        "used": False,
        "question": clean_question,
        "previous_question": previous,
        "effective_question": clean_question,
    }


def _active_dialog_entry(key: str, *, now: datetime | None = None) -> dict[str, object]:
    entry = _RESEARCH_DIALOG_STATE.get(key, {})
    timestamp = now or datetime.now(timezone.utc)
    updated_at = entry.get("updated_at") if isinstance(entry, Mapping) else None
    if not isinstance(updated_at, datetime) or timestamp - updated_at > _RESEARCH_DIALOG_TTL:
        _RESEARCH_DIALOG_STATE.pop(key, None)
        _RESEARCH_DIALOG_MODE_STATE.pop(key, None)
        return {}
    return dict(entry)


def _dialog_session_id(chat_id: str, question: str) -> str:
    """Continue only a short follow-up; every new topic starts a fresh session."""

    entry = _active_dialog_entry(_dialog_key(chat_id))
    session_id = str(entry.get("session_id") or "")
    if session_id and _is_research_followup(_clean_operator_text(question)):
        return session_id
    return str(uuid4())


def _remember_research_dialog(
    chat_id: str, effective_question: str, *, mode: str = "research", session_id: str = ""
) -> None:
    key = _dialog_key(chat_id)
    if len(_RESEARCH_DIALOG_STATE) >= _MAX_RESEARCH_DIALOGS and key not in _RESEARCH_DIALOG_STATE:
        oldest_key = next(iter(_RESEARCH_DIALOG_STATE))
        _RESEARCH_DIALOG_STATE.pop(oldest_key, None)
        _RESEARCH_DIALOG_MODE_STATE.pop(oldest_key, None)
    existing = _active_dialog_entry(key)
    summaries = existing.get("summaries") if isinstance(existing.get("summaries"), list) else []
    summary = _clean_operator_text(effective_question)[:500]
    if not summaries or summaries[-1] != summary:
        summaries = [*summaries, summary][-6:]
    _RESEARCH_DIALOG_STATE[key] = {
        "summaries": summaries,
        "updated_at": datetime.now(timezone.utc),
        "session_id": str(session_id or existing.get("session_id") or uuid4()),
    }
    _RESEARCH_DIALOG_MODE_STATE[key] = mode if mode in {"research", "brief", "chat"} else "research"


def _is_research_followup(question: str) -> bool:
    clean = _clean_operator_text(question)
    lowered = clean.casefold()
    if not clean:
        return False
    if len(clean) > 90:
        return False
    if _contains_research_anchor(lowered):
        return False
    followup_markers = (
        "а почему",
        "почему",
        "а где",
        "а кто",
        "а что",
        "что еще",
        "что ещё",
        "и где",
        "и кто",
        "сравни",
        "разверни",
        "подробнее",
        "поясни",
        "дальше",
        "why",
        "and why",
        "what else",
        "compare",
        "expand",
    )
    if any(lowered.startswith(marker) for marker in followup_markers):
        return True
    token_count = len(re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", lowered))
    return token_count <= 4 and lowered.endswith("?")


def _contains_research_anchor(lowered: str) -> bool:
    anchors = (
        "ai",
        "ии",
        "rag",
        "раг",
        "telegram",
        "телеграм",
        "компан",
        "трансформац",
        "внедрен",
        "архив",
        "пост",
        "цена",
        "nvidia",
        "eval",
        "vector",
        "вектор",
    )
    return any(anchor in lowered for anchor in anchors)


def _clean_operator_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _format_post_snippet(text: str | None, limit: int = 150) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _format_optional_list(title: str, values: list, limit: int = 3) -> list[str]:
    items = [str(value).strip() for value in values if str(value or "").strip()]
    if not items:
        return []
    lines = [title]
    for item in items[:limit]:
        lines.append(f"- {item}")
    return lines


def _format_source_refs(source_refs: list, atom_ids: list | None = None, limit: int = 3) -> str:
    refs = [str(ref).strip() for ref in source_refs if str(ref or "").strip()]
    atoms = [f"atom:{atom_id}" for atom_id in atom_ids or [] if str(atom_id or "").strip()]
    combined = [*refs, *atoms]
    if not combined:
        return "Sources: insufficient curated evidence"
    return "Sources: " + ", ".join(combined[:limit])


def _pi_tool(settings: Settings, name: str, args: dict | None = None) -> dict:
    return call_pi_tool(name, args or {}, facade=PersonalIntelligenceFacade(settings=settings))


def _normalize_tag(raw_tag: str) -> str | None:
    return TAG_ALIASES.get(raw_tag.strip().lower())


def _resolve_post_reference(connection: sqlite3.Connection, raw_ref: str) -> sqlite3.Row | None:
    ref = raw_ref.strip()
    if ref.isdigit() and int(ref) > 0:
        return connection.execute(
            "SELECT id, channel_username, content FROM posts WHERE id = ? LIMIT 1",
            (int(ref),),
        ).fetchone()

    match = TELEGRAM_POST_URL_RE.match(ref)
    if not match:
        return None

    channel_username = f"@{match.group(1)}"
    message_id = int(match.group(2))
    return connection.execute(
        """
        SELECT p.id, p.channel_username, p.content
        FROM posts p
        INNER JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE lower(r.channel_username) = lower(?) AND r.message_id = ?
        LIMIT 1
        """,
        (channel_username, message_id),
    ).fetchone()


def _parse_week_label_args(args: str) -> tuple[str, str]:
    stripped = args.strip()
    if not stripped:
        return _compute_week_label(), ""
    first, _, rest = stripped.partition(" ")
    if WEEK_LABEL_RE.match(first):
        return first, rest.strip()
    return _compute_week_label(), stripped


def _parse_optional_week_label_args(args: str) -> tuple[str | None, str]:
    stripped = args.strip()
    if not stripped:
        return None, ""
    first, _, rest = stripped.partition(" ")
    if WEEK_LABEL_RE.match(first):
        return first, rest.strip()
    return None, stripped


def _format_local_due_at(iso_value: str) -> str:
    return format_reminder_due_at(iso_value)


def _extract_question_terms(question: str) -> list[str]:
    terms = []
    for raw_term in QUESTION_WORD_RE.findall(question.lower()):
        if len(raw_term) < 3:
            continue
        if raw_term not in terms:
            terms.append(raw_term)
    return terms[:8]


def _build_fts_query(question: str) -> str:
    terms = _extract_question_terms(question)
    if not terms:
        return ""
    return " OR ".join(f'"{term.replace(chr(34), " ").strip()}"' for term in terms if term.strip())


def _load_topics_summary(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        """
        SELECT label, description, post_count
        FROM topics
        ORDER BY post_count DESC, label ASC
        LIMIT 20
        """
    ).fetchall()
    if not rows:
        return "No topics yet."
    return "\n".join(
        f"- {row['label']} ({row['post_count']}): {row['description'] or 'no description'}" for row in rows
    )


def handle_start(chat_id: str, args: str, settings: Settings) -> None:
    del args, settings
    lines = [
        "Hermes",
        "",
        "Просто напиши вопрос или отправь голосовое.",
        "Я сам определю: чат, фидбек или напоминание.",
        "",
        "Рабочий цикл:",
        "1. Открой weekly HTML Workbook.",
        "2. Спроси обычным текстом, что важно и что делать дальше.",
        "3. После чтения дай feedback текстом или голосом.",
        "4. Подтверди память, если draft правильный.",
        "",
        "Ручные команды остаются запасным вариантом: /weekly, /actions, /mvp, /strategy, /remind.",
        "",
        "Границы: read-only PI tools, curated intelligence, без raw Telegram RAG, без Codex/config/code mutations.",
    ]
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_prm_start(chat_id: str, args: str, settings: Settings) -> None:
    del args, settings
    lines = [
        "Личный помощник по исследованию",
        "",
        "Просто напиши вопрос или отправь голосовое.",
        "Найду материалы в твоём архиве, соберу бриф или задам один короткий уточняющий вопрос.",
        "",
        "Например:",
        "• Что обсуждали про agent evals за последние 90 дней?",
        "• Что из этого относится к моему проекту?",
        "• Собери бриф для поста про AI adoption.",
        "",
        "Команды /research и /brief — запасной вариант.",
        "Я показываю источники и отмечаю, где данных недостаточно. Актуальные внешние факты требуют отдельной проверки.",
        "Сохранение заметки всегда требует явного подтверждения.",
    ]
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_refresh(chat_id: str, args: str, settings: Settings) -> None:
    """Show a read-only refresh orchestration receipt; never starts a routine."""

    del args, settings
    owner_chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
    if not owner_chat_id or str(chat_id) != owner_chat_id:
        send_message(_get_bot_token(), chat_id, "Обновление доступно только владельцу. Ничего не запускалось.", parse_mode=None)
        return
    receipt = build_refresh_receipt()
    send_message(_get_bot_token(), chat_id, render_refresh_receipt(receipt), parse_mode=None)


def _load_reaction_receipt_readonly(db_path: str) -> dict[str, object] | None:
    path = Path(db_path)
    if not path.exists():
        return None
    try:
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            return build_reaction_fast_lane_receipt(connection)
    except (OSError, sqlite3.Error):
        return None


def handle_reactions(chat_id: str, args: str, settings: Settings) -> None:
    """Render the existing reaction receipt read-only; never starts sync or writes a preference."""

    del args
    owner_chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
    if not owner_chat_id or str(chat_id) != owner_chat_id:
        send_message(_get_bot_token(), chat_id, "Реакции доступны только владельцу. Ничего не запускалось.", parse_mode=None)
        return
    receipt = _load_reaction_receipt_readonly(settings.db_path)
    if receipt is None:
        send_message(_get_bot_token(), chat_id, "Статус реакций пока недоступен. Синхронизация не запускалась.", parse_mode=None)
        return
    lines = [render_operator_reaction_receipt(receipt)]
    proposal = build_reaction_preference_proposal(receipt)
    if proposal["status"] == "needs_confirmation":
        lines.extend(["", "Есть предложение настройки интересов; оно не сохранено и ждёт отдельного подтверждения."])
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def normalize_bot_runtime_mode(runtime_mode: str | None) -> str:
    mode = str(runtime_mode or BOT_RUNTIME_LEGACY).strip()
    if mode in BOT_RUNTIME_MODES:
        return mode
    return BOT_RUNTIME_LEGACY


def _send_prm_safe_blocked(chat_id: str, command: str) -> None:
    shown_command = command or "unknown"
    lines = [
        "PRM safe mode blocked this legacy command.",
        f"Command: {shown_command}",
        "",
        "Send ordinary text for auto local routing, or use /research for grounded questions, /brief for source-backed theses, or /weekly /actions /mvp /strategy for read-only orientation.",
        "No generation, ingestion, Radar, direct feedback/tag/reminder write, or report delivery was run.",
    ]
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_weekly(chat_id: str, args: str, settings: Settings) -> None:
    week_label, _rest = _parse_optional_week_label_args(args)
    tool = _pi_tool(settings, "get_weekly_summary", {"week_label": week_label})
    summary = tool["result"]
    if tool["status"] != "ok":
        send_message(
            _get_bot_token(),
            chat_id,
            f"Hermes weekly: workbook is not ready for {week_label or 'latest week'}.\n{summary.get('message')}",
            parse_mode=None,
        )
        return

    lines = [f"Hermes weekly {summary.get('week_label') or week_label or 'latest'}"]
    decision_brief = summary.get("decision_brief")
    if isinstance(decision_brief, list) and decision_brief:
        lines.append("")
        lines.append("Decision brief")
        for card in decision_brief[:3]:
            if not isinstance(card, dict):
                continue
            title = card.get("title") or card.get("verdict") or "Decision"
            body = card.get("summary") or card.get("next_action") or ""
            lines.append(f"- {title}: {_format_post_snippet(body, limit=180)}")
    strong_signals = [item for item in summary.get("strong_signals") or [] if isinstance(item, dict)]
    if strong_signals:
        lines.append("")
        lines.append("Strong signals")
        for signal in strong_signals[:3]:
            claim = signal.get("claim") or signal.get("title") or "Signal"
            lines.append(f"- {_format_post_snippet(claim, limit=180)}")
    actions = [item for item in summary.get("actions") or [] if isinstance(item, dict)]
    if actions:
        lines.append("")
        lines.append("Actions")
        for action in actions[:3]:
            title = action.get("title") or "Action"
            next_step = action.get("next_step") or action.get("success_criterion") or ""
            lines.append(f"- {title}: {_format_post_snippet(next_step, limit=160)}")
    paths = summary.get("artifact_paths") or {}
    if paths.get("html") or paths.get("json"):
        lines.append("")
        lines.append("Workbook")
        if paths.get("html"):
            lines.append(str(paths["html"]))
        if paths.get("json"):
            lines.append(str(paths["json"]))
    if tool["evidence_status"] == "insufficient":
        lines.append("")
        lines.append("Evidence: insufficient curated evidence.")
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_actions(chat_id: str, args: str, settings: Settings) -> None:
    week_label, _rest = _parse_optional_week_label_args(args)
    tool = _pi_tool(settings, "get_action_statuses", {"week_label": week_label})
    result = tool["result"]
    if tool["status"] == "missing":
        send_message(
            _get_bot_token(),
            chat_id,
            f"No workbook actions are available for {week_label or 'latest week'}.",
            parse_mode=None,
        )
        return

    items = [item for item in result.get("items") or [] if isinstance(item, dict)]
    lines = [f"Hermes actions {result.get('week_label') or week_label or 'latest'}"]
    for action in items[:3]:
        title = action.get("title") or action.get("action_id") or "Action"
        status = action.get("status") or "unknown"
        lines.append(f"- [{status}] {title}")
        if action.get("follow_up_hint"):
            lines.append(f"  follow-up: {_format_post_snippet(action['follow_up_hint'], limit=160)}")
        if action.get("outcome_policy"):
            lines.append(f"  policy: {_format_post_snippet(action['outcome_policy'], limit=160)}")
    if not items:
        lines.append("No action cards are available in the curated workbook.")
    if result.get("counts"):
        counts = ", ".join(f"{key}={value}" for key, value in sorted(result["counts"].items()) if value)
        if counts:
            lines.append(f"Status counts: {counts}")
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_explain(chat_id: str, args: str, settings: Settings) -> None:
    week_label, query = _parse_optional_week_label_args(args)
    if not query:
        send_message(_get_bot_token(), chat_id, "Usage: /explain [week] <query>", parse_mode=None)
        return
    filters = {"week_label": week_label} if week_label else {}
    tool = _pi_tool(
        settings,
        "search_intelligence_items",
        {"query": query, "filters": filters, "limit": 3},
    )
    items = [item for item in tool["result"].get("items") or [] if isinstance(item, dict)]
    if not items:
        send_message(
            _get_bot_token(),
            chat_id,
            f"No curated explanation found for: {query}\nEvidence: insufficient curated evidence.",
            parse_mode=None,
        )
        return
    lines = [f"Hermes explain: {query}"]
    for item in items:
        title = item.get("title") or item.get("id") or "Curated item"
        summary = item.get("summary") or item.get("text") or ""
        lines.append("")
        lines.append(f"{item.get('item_type')}: {title}")
        if summary:
            lines.append(_format_post_snippet(summary, limit=260))
        lines.append(_format_source_refs(item.get("source_refs") or [], item.get("atom_ids") or []))
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_projects(chat_id: str, args: str, settings: Settings) -> None:
    week_label, project_query = _parse_optional_week_label_args(args)
    tool = _pi_tool(settings, "get_project_actions", {"week_label": week_label})
    items = [item for item in tool["result"].get("items") or [] if isinstance(item, dict)]
    if project_query:
        needle = project_query.lower()
        items = [item for item in items if needle in str(item.get("project") or "").lower()]
    if not items:
        send_message(
            _get_bot_token(),
            chat_id,
            f"No curated project actions are available for {project_query or week_label or 'latest week'}.",
            parse_mode=None,
        )
        return
    lines = [f"Hermes projects {tool['result'].get('week_label') or week_label or 'latest'}"]
    for item in items[:5]:
        project = item.get("project") or "project"
        action = item.get("action") or item.get("why") or ""
        lines.append("")
        lines.append(f"{project}: {_format_post_snippet(action, limit=180)}")
        if item.get("effort"):
            lines.append(f"Effort: {item['effort']}")
        if item.get("risk"):
            lines.append(f"Risk: {_format_post_snippet(item['risk'], limit=140)}")
        lines.append(_format_source_refs(item.get("source_refs") or []))
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_mvp(chat_id: str, args: str, settings: Settings) -> None:
    week_label, _rest = _parse_optional_week_label_args(args)
    tool = _pi_tool(settings, "get_mvp_radar_status", {"week_label": week_label})
    result = tool["result"]
    if tool["status"] != "ok":
        send_message(
            _get_bot_token(),
            chat_id,
            f"MVP Radar status is missing for {week_label or 'latest week'}.\n{result.get('message')}",
            parse_mode=None,
        )
        return
    lines = [
        f"Hermes MVP {result.get('week_label') or week_label or 'latest'}",
        f"Candidate: {result.get('candidate') or 'none'}",
        f"Dossier status: {result.get('dossier_status') or 'unknown'}",
        f"Recommendation: {result.get('recommendation') or 'unknown'}",
    ]
    if result.get("source_mix"):
        lines.append(f"Source mix: {result['source_mix']}")
    lines.extend(_format_optional_list("Missing evidence", result.get("missing_evidence") or [], limit=5))
    lines.extend(_format_optional_list("Next validation", result.get("next_validation") or [], limit=5))
    if tool["evidence_status"] == "insufficient":
        lines.append("Evidence: insufficient curated evidence.")
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_strategy(chat_id: str, args: str, settings: Settings) -> None:
    week_label, _query = _parse_optional_week_label_args(args)
    tool = _pi_tool(
        settings,
        "get_strategy_reviewer_notes",
        {"week_label": week_label},
    )
    result = tool["result"]
    if tool["status"] != "ok":
        send_message(
            _get_bot_token(),
            chat_id,
            f"No Strategy Reviewer notes are available for {week_label or 'latest week'}.\n{result.get('message')}",
            parse_mode=None,
        )
        return
    lines = [
        f"Hermes strategy {result.get('week_label') or week_label or 'latest'}",
        "Advisory only; no changes were applied.",
    ]
    suggestions = result.get("suggestions") or {}
    for title, key in (
        ("Keep", "keep"),
        ("Change", "change"),
        ("Demote", "demote"),
        ("Test next week", "test_next_week"),
    ):
        lines.extend(_format_optional_list(title, suggestions.get(key) or [], limit=4))
    lines.extend(_format_optional_list("Memory-only updates", result.get("memory_only_updates") or [], limit=4))
    approvals = [item for item in result.get("approval_required") or [] if isinstance(item, dict)]
    if approvals:
        lines.append("Approval required")
        for item in approvals[:4]:
            reason = item.get("reason") or item.get("change_type") or "manual approval required"
            lines.append(f"- {_format_post_snippet(reason, limit=180)}")
    tasks = [item for item in result.get("codex_tasks") or [] if isinstance(item, dict)]
    if tasks:
        lines.append("Codex tasks")
        for task in tasks[:3]:
            lines.append(f"- {task.get('title') or 'Codex task'}")
            if task.get("rationale"):
                lines.append(f"  why: {_format_post_snippet(task['rationale'], limit=160)}")
            if task.get("files"):
                lines.append(f"  files: {', '.join(task['files'][:4])}")
            if task.get("acceptance_criteria"):
                lines.append(f"  acceptance: {_format_post_snippet(task['acceptance_criteria'][0], limit=160)}")
            if task.get("verification_commands"):
                lines.append(f"  verify: {task['verification_commands'][0]}")
    lines.extend(_format_optional_list("Risks", result.get("risks") or [], limit=4))
    mutation_policy = result.get("mutation_policy") or {}
    if mutation_policy:
        lines.append(
            "Mutation policy: "
            + ", ".join(f"{key}={value}" for key, value in sorted(mutation_policy.items()))
        )
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_codex(chat_id: str, args: str, settings: Settings) -> None:
    del settings
    focus = args.strip() or "Implement the next bounded HPI task from docs/tasks.md."
    lines = [
        "Codex prompt draft (manual approval required)",
        "",
        "Task:",
        focus,
        "",
        "Constraints:",
        "- Use curated PI/Hermes data only; no raw Telegram firehose RAG.",
        "- Do not edit code/config/profile/projects unless the approved task requires code/docs edits.",
        "- Do not run weekly pipelines unless explicitly needed for verification.",
        "- Preserve evidence gates and insufficient-evidence states.",
        "",
        "Verification:",
        "- Run focused unit tests for touched modules.",
        "- Run relevant regressions before commit.",
        "",
        "No Codex command has been executed.",
    ]
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_digest(chat_id: str, args: str, settings: Settings) -> None:
    del args
    week_label = _compute_week_label()

    with _with_db(settings) as connection:
        row = connection.execute(
            """
            SELECT content_md
            FROM digests
            WHERE week_label = ?
            """,
            (week_label,),
        ).fetchone()

        if row is None:
            row = connection.execute(
                """
                SELECT content_md
                FROM digests
                ORDER BY week_label DESC
                LIMIT 1
                """
            ).fetchone()

    if row is None or not row["content_md"]:
        send_message(
            _get_bot_token(),
            chat_id,
            "This week's brief is not ready yet. Run /run_digest.",
            parse_mode=None,
        )
        return

    try:
        send_text(chat_id=chat_id, text=row["content_md"], token=_get_bot_token(), parse_mode=None)
    except Exception:
        LOGGER.warning("Failed to send digest text chat_id=%s week=%s", chat_id, week_label, exc_info=True)
        _friendly_handler_error(chat_id)


def handle_topics(chat_id: str, args: str, settings: Settings) -> None:
    del args
    with _with_db(settings) as connection:
        rows = connection.execute(
            """
            SELECT id, label, description, post_count, last_seen
            FROM topics
            ORDER BY post_count DESC, label ASC
            """
        ).fetchall()

    if not rows:
        send_message(_get_bot_token(), chat_id, "No topics yet.", parse_mode=None)
        return

    lines = []
    for index, row in enumerate(rows, start=1):
        description = row["description"] or "no description"
        lines.append(f"{index}. {row['label']} ({row['post_count']} posts) — {description}")
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_insight(chat_id: str, args: str, settings: Settings) -> None:
    del args
    result = generate_insight(settings.db_path, lookback_days=90).strip()
    if not result:
        send_message(_get_bot_token(), chat_id, "No active projects found. Sync or define projects first.", parse_mode=None)
        return
    send_message(_get_bot_token(), chat_id, result, parse_mode=None)


def handle_project(chat_id: str, args: str, settings: Settings) -> None:
    project_query = args.strip()
    if not project_query:
        send_message(_get_bot_token(), chat_id, "Usage: /project <partial-name>", parse_mode=None)
        return

    with _with_db(settings) as connection:
        projects = connection.execute(
            """
            SELECT DISTINCT
                p.id,
                p.name,
                p.description,
                p.keywords,
                p.last_commit_at
            FROM projects p
            LEFT JOIN post_project_links ppl ON p.id = ppl.project_id
            LEFT JOIN posts po ON ppl.post_id = po.id
            LEFT JOIN post_topics pt ON po.id = pt.post_id
            LEFT JOIN topics t ON pt.topic_id = t.id
            WHERE lower(p.name) LIKE lower('%' || ? || '%') AND p.active = 1
            ORDER BY p.name ASC
            LIMIT 5
            """,
            (project_query,),
        ).fetchall()

        if not projects:
            send_message(
                _get_bot_token(),
                chat_id,
                "Project not found. Use /project <partial-name> to search active projects.",
                parse_mode=None,
            )
            return

        sections = []
        for project in projects:
            topic_rows = connection.execute(
                """
                SELECT DISTINCT t.label
                FROM post_project_links ppl
                INNER JOIN posts po ON ppl.post_id = po.id
                LEFT JOIN post_topics pt ON po.id = pt.post_id
                LEFT JOIN topics t ON pt.topic_id = t.id
                WHERE ppl.project_id = ? AND t.label IS NOT NULL
                ORDER BY t.label ASC
                """,
                (project["id"],),
            ).fetchall()
            post_rows = connection.execute(
                """
                SELECT po.posted_at, po.channel_username, po.content
                FROM post_project_links ppl
                INNER JOIN posts po ON ppl.post_id = po.id
                WHERE ppl.project_id = ?
                ORDER BY ppl.relevance_score DESC, po.posted_at DESC
                LIMIT 3
                """,
                (project["id"],),
            ).fetchall()

            topics = ", ".join(row["label"] for row in topic_rows) or "no linked topics"
            last_commit = project["last_commit_at"] or "unknown"
            lines = [
                project["name"],
                f"Last commit: {last_commit}",
                f"Topics: {topics}",
            ]
            if project["description"]:
                lines.append(f"Description: {project['description']}")
            if project["keywords"]:
                lines.append(f"Keywords: {project['keywords']}")
            if post_rows:
                lines.append("Linked posts:")
                for row in post_rows:
                    lines.append(
                        f"- {row['posted_at']} @{row['channel_username']}: {_format_post_snippet(row['content'])}"
                    )
            else:
                lines.append("Linked posts: none")
            sections.append("\n".join(lines))

    send_message(_get_bot_token(), chat_id, "\n\n".join(sections), parse_mode=None)


def handle_ask(chat_id: str, args: str, settings: Settings) -> None:
    handle_chat(chat_id, args, settings)


def handle_auto(chat_id: str, args: str, settings: Settings) -> None:
    _handle_auto(chat_id, args, settings, input_kind="text")


def handle_auto_voice(chat_id: str, args: str, settings: Settings) -> None:
    """Internal PRM-safe voice route; the transcript remains ephemeral."""

    _handle_auto(chat_id, args, settings, input_kind="voice_transcript")


def _handle_auto(chat_id: str, args: str, settings: Settings, *, input_kind: str) -> None:
    question = args.strip()
    if not question:
        send_message(_get_bot_token(), chat_id, "Напиши обычный вопрос или задачу.", parse_mode=None)
        return
    route = _route_auto_message(chat_id, question, input_kind=input_kind)
    project_name = _named_project_from_message(question)
    mode = str(route.get("mode") or "research")
    operator_context = build_operator_context(
        chat_id=chat_id,
        query=question,
        requested_mode=mode,
        input_kind=input_kind,  # type: ignore[arg-type]
        project_name=project_name,
        session_id=_dialog_session_id(chat_id, question),
    )
    validate_operator_context(operator_context)
    mode = {
        "writer_editor_brief": "brief",
        "generic_chat": "chat",
        "insufficient_evidence": "clarify",
    }.get(operator_context.primary_workflow, "research")
    LOGGER.info(
        "PRM auto route selected interaction_id=%s chat_id_hash=%s workflow=%s router=%s confidence=%.2f model_call_attempted=%s",
        operator_context.interaction_id,
        operator_context.chat_id_hash,
        operator_context.primary_workflow,
        route.get("router") or "unknown",
        _safe_confidence(route.get("confidence")),
        bool(route.get("model_call_attempted")),
    )
    if mode == "clarify":
        send_message(
            _get_bot_token(),
            chat_id,
            "Уточни: найти материалы в архиве или собрать бриф для текста?",
            parse_mode=None,
        )
        return
    acknowledgement = _auto_intent_acknowledgement(route)
    if mode == "brief":
        handle_research_brief(
            chat_id,
            question,
            settings,
            intent_acknowledgement=acknowledgement,
            archive_query=_bounded_retrieval_query(route.get("retrieval_query")),
            project_name=project_name,
            operator_context=operator_context.to_dict(),
        )
        return
    if mode == "chat":
        handle_chat(chat_id, question, settings)
        if _telegram_provider_egress_allowed():
            _remember_research_dialog(chat_id, question, mode="chat")
        return
    handle_research(
        chat_id,
        question,
        settings,
        intent_acknowledgement=acknowledgement,
        archive_query=_bounded_retrieval_query(route.get("retrieval_query")),
        project_name=project_name,
        operator_context=operator_context.to_dict(),
    )


def _auto_intent_acknowledgement(route: Mapping[str, object]) -> str:
    mode = str(route.get("mode") or "")
    reason = str(route.get("reason") or "")
    if mode == "research" and reason == "Default safe local archive research route.":
        return "Проверю по локальному архиву."
    if mode == "brief" and _safe_confidence(route.get("confidence")) < 0.7:
        return "Соберу редакторский бриф по локальным источникам."
    return ""


def handle_research(
    chat_id: str,
    args: str,
    settings: Settings,
    *,
    intent_acknowledgement: str = "",
    archive_query: str = "",
    project_name: str = "",
    operator_context: Mapping[str, object] | None = None,
) -> None:
    question = args.strip()
    if not question:
        send_message(_get_bot_token(), chat_id, "Напиши вопрос после /research или просто отправь обычное сообщение.", parse_mode=None)
        return
    dialog = _resolve_research_dialog_question(chat_id, question)
    budget = MemoryResearchBudget(
        max_tool_calls=4,
        max_archive_sources=5,
        max_linked_sources=3,
        max_retries=0,
        timeout_seconds=30,
        max_prompt_chars=8000,
        max_model_calls=0,
        max_cost_usd=0.0,
        allow_open_browsing=False,
        allow_provider_egress=False,
        allow_vector_retrieval=_telegram_hybrid_retrieval_allowed(),
        vector_index_path=_telegram_vector_index_path(),
    )
    try:
        result = answer_memory_research(
            str(dialog["effective_question"]),
            archive_query=archive_query,
            project_name=project_name or _named_project_from_message(dialog["effective_question"]),
            settings=settings,
            limit=4,
            budget=budget,
            operator_context=operator_context,
        )
    except Exception as exc:
        send_message(_get_bot_token(), chat_id, f"Не смог выполнить local research: {exc}", parse_mode=None)
        return
    result = _with_dialog_context(result, dialog)
    if operator_context is not None:
        result["operator_context"] = dict(operator_context)
    _remember_research_dialog(
        chat_id,
        str(dialog["effective_question"]),
        mode="research",
        session_id=str(_safe_mapping(operator_context).get("session_id") or ""),
    )
    local_text = render_memory_research_answer(result)
    response_text = _with_auto_intent_acknowledgement(
        _render_telegram_research_response(result, local_text=local_text, mode="research"),
        intent_acknowledgement,
    )
    _send_research_text(chat_id, response_text, token=_get_bot_token(), reply_markup=_prm_post_answer_markup(result, settings=settings, chat_id=chat_id))


def handle_research_brief(
    chat_id: str,
    args: str,
    settings: Settings,
    *,
    intent_acknowledgement: str = "",
    archive_query: str = "",
    project_name: str = "",
    operator_context: Mapping[str, object] | None = None,
) -> None:
    question = args.strip()
    if not question:
        send_message(_get_bot_token(), chat_id, "Напиши вопрос после /brief.", parse_mode=None)
        return
    dialog = _resolve_research_dialog_question(chat_id, question)
    budget = MemoryResearchBudget(
        max_tool_calls=4,
        max_archive_sources=5,
        max_linked_sources=3,
        max_retries=0,
        timeout_seconds=30,
        max_prompt_chars=8000,
        max_model_calls=0,
        max_cost_usd=0.0,
        allow_open_browsing=False,
        allow_provider_egress=False,
        allow_vector_retrieval=_telegram_hybrid_retrieval_allowed(),
        vector_index_path=_telegram_vector_index_path(),
    )
    try:
        result = answer_memory_research(
            str(dialog["effective_question"]),
            archive_query=archive_query,
            project_name=project_name or _named_project_from_message(dialog["effective_question"]),
            settings=settings,
            limit=5,
            budget=budget,
            operator_context=operator_context,
        )
    except Exception as exc:
        send_message(_get_bot_token(), chat_id, f"Не смог собрать local brief: {exc}", parse_mode=None)
        return
    result = _with_dialog_context(result, dialog)
    if operator_context is not None:
        result["operator_context"] = dict(operator_context)
    _remember_research_dialog(
        chat_id,
        str(dialog["effective_question"]),
        mode="brief",
        session_id=str(_safe_mapping(operator_context).get("session_id") or ""),
    )
    local_text = render_memory_research_brief(result)
    response_text = _with_auto_intent_acknowledgement(
        _render_telegram_research_response(result, local_text=local_text, mode="brief"),
        intent_acknowledgement,
    )
    _send_research_text(chat_id, response_text, token=_get_bot_token(), reply_markup=_prm_post_answer_markup(result, settings=settings, chat_id=chat_id))


def _with_auto_intent_acknowledgement(response_text: str, acknowledgement: str) -> str:
    clean_acknowledgement = str(acknowledgement or "").strip()
    if not clean_acknowledgement:
        return response_text
    return f"{clean_acknowledgement}\n\n{response_text.lstrip()}"


def _with_dialog_context(result: Mapping[str, object], dialog: Mapping[str, object]) -> dict:
    payload = dict(result)
    if bool(dialog.get("used")):
        payload["question"] = str(dialog.get("question") or payload.get("question") or "")
        payload["dialog_context"] = {
            "used": True,
            "previous_question": str(dialog.get("previous_question") or ""),
            "effective_question": str(dialog.get("effective_question") or ""),
        }
    return payload


def _render_telegram_research_response(payload: Mapping[str, Any], *, local_text: str, mode: str) -> str:
    """Optionally synthesize a Telegram RAG answer after local retrieval has run."""

    clean_local_text = _telegram_report_without_technical_metrics(local_text)
    professional_answer = _safe_mapping(payload.get("professional_answer"))
    if professional_answer.get("schema_version") == "professional_answer.v1":
        return _render_telegram_professional_answer(professional_answer)
    answer_gate = _safe_mapping(payload.get("answer_gate"))
    current_fact_boundary = bool(answer_gate.get("external_verification_required")) and not bool(
        answer_gate.get("current_claim_allowed", True)
    )
    if current_fact_boundary:
        return _render_telegram_answer_first_research(payload)
    if _telegram_rag_llm_synthesis_allowed() and _telegram_rag_source_count(payload) > 0:
        try:
            return _synthesize_telegram_rag_answer(payload, mode=mode)
        except Exception:
            LOGGER.warning("Telegram RAG LLM synthesis failed mode=%s", mode, exc_info=True)
    if mode == "research" and _looks_russian(str(payload.get("question") or "")):
        return _render_telegram_answer_first_research(payload)
    return clean_local_text


def _render_telegram_professional_answer(answer: Mapping[str, Any]) -> str:
    """Render the shared MAT reader DTO without exposing runtime-only fields."""

    verification_required = str(answer.get("answer_status") or "") == "verification_required" or bool(
        _safe_mapping(answer.get("external_verification")).get("required")
    )
    findings: list[str] = []
    sources: list[str] = []
    for item in _safe_mapping_list(answer.get("key_findings"))[:4]:
        claim = _public_telegram_text(item.get("claim"))
        citation = _public_telegram_text(item.get("citation"))
        if claim:
            findings.append(f"- {claim}")
        if citation:
            sources.append(f"- {citation}")
    if not sources:
        for item in _safe_mapping_list(answer.get("citations"))[:4]:
            citation = _public_telegram_text(item.get("source_url"))
            if citation:
                sources.append(f"- {citation}")

    project_context = _safe_mapping(answer.get("project_context"))
    uncertainty = [
        _public_telegram_text(_localize_telegram_unknown(str(item)))
        for item in answer.get("uncertainty") or []
        if str(item).strip()
    ]
    short_answer = _public_telegram_text(answer.get("short_answer")) or "Недостаточно данных для уверенного вывода."
    if verification_required:
        short_answer = "Требуется отдельная внешняя проверка актуального факта."
        uncertainty.insert(0, "Архив может дать только контекст, а не подтверждение текущего факта.")
    if not uncertainty:
        uncertainty.append("Недостаточно данных для более сильного вывода без дополнительной проверки.")

    action = _public_telegram_text(answer.get("recommended_action"))
    if verification_required:
        action = "Сначала нужна отдельная внешняя проверка; в этом ответе она не запускалась."
    if not action:
        action = "Не превращать этот сигнал в действие без более точных доказательств."
    workflow_section = _safe_mapping(answer.get("workflow_section"))
    workflow_line = _telegram_workflow_line(workflow_section)

    lines = [
        "Короткий вывод", short_answer, "", "Что найдено",
        *(findings or ["- Локальных источников для сильного вывода не найдено."]), "",
        "Почему это важно тебе", _telegram_project_relation(project_context), "",
        *( ["Рабочий фокус", workflow_line, ""] if workflow_line else []),
        "Что сделать", action, "", "Чего пока не делать",
        "Не считать локальные сигналы подтверждением без достаточных источников.", "",
        "Где доказательства слабые", *[f"- {item}" for item in uncertainty[:2]], "",
        "Источники", *(sources or ["- локальных источников нет"]),
    ]
    return _telegram_report_without_technical_metrics("\n".join(lines))


def _telegram_workflow_line(section: Mapping[str, Any]) -> str:
    for field in (
        "project_implication",
        "practical_conclusion",
        "validation_step",
        "plain_explanation",
        "recurring_requirement",
        "next_portfolio_action",
        "market_boundary",
        "gap_summary",
    ):
        value = _public_telegram_text(section.get(field))
        if value:
            return value
    return ""


def _render_telegram_answer_first_research(payload: Mapping[str, Any]) -> str:
    """Render the fixed public Telegram research contract from bounded local evidence."""

    answer_gate = _safe_mapping(payload.get("answer_gate"))
    archive = _safe_mapping(payload.get("archive_evidence"))
    linked = _safe_mapping(payload.get("linked_source_evidence"))
    project_fit = _safe_mapping(payload.get("project_fit"))
    next_steps = _safe_mapping(payload.get("next_steps"))
    unknowns = [
        _public_telegram_text(_localize_telegram_unknown(str(item)))
        for item in payload.get("unknowns") or []
        if str(item).strip()
    ]
    source_lines = [_public_telegram_text(line) for line in _telegram_public_source_lines(archive, linked)]
    source_lines = [line for line in source_lines if line]
    current_fact = bool(answer_gate.get("external_verification_required")) and not bool(
        answer_gate.get("current_claim_allowed", True)
    )
    source_count = len(_safe_mapping_list(archive.get("items"))) + len(_safe_mapping_list(linked.get("items")))

    lines: list[str] = []
    if current_fact:
        lines.extend(
            [
                "Внешняя проверка нужна: актуальность текущего факта не подтверждена локальным архивом.",
                "",
            ]
        )
    lines.extend(["Короткий вывод", _telegram_public_answer_summary(payload)])
    lines.extend(
        [
            "",
            "Что найдено",
            (
                f"В локальном архиве найдено источников: {source_count}."
                if source_count
                else "В локальном архиве релевантных источников не найдено."
            ),
        ]
    )
    lines.extend(["", "Почему это важно тебе", _telegram_project_relation(project_fit)])

    action = _telegram_public_next_action(next_steps)
    if current_fact:
        action = "Сначала нужна отдельная внешняя проверка; в этом ответе она не запускалась."
    lines.extend(["", "Что сделать", action])

    weak_lines = [item for item in unknowns if item][:2]
    if current_fact:
        weak_lines.insert(0, "Текущий факт не подтверждён; архив ниже является только контекстом.")
    if not source_count:
        weak_lines.insert(0, "Недостаточно данных: без локальных источников нельзя делать вывод.")
    if not weak_lines:
        weak_lines.append("Недостаточно данных для более сильного вывода без дополнительной проверки.")
    elif not any("недостаточно данных" in item.casefold() for item in weak_lines):
        weak_lines.insert(0, "Недостаточно данных для более сильного вывода без дополнительной проверки.")
    lines.extend(["", "Где доказательства слабые", *[f"- {item}" for item in weak_lines]])
    lines.extend(["", "Источники", *(source_lines or ["- локальных источников нет"])])
    return _telegram_report_without_technical_metrics("\n".join(lines))


def _public_telegram_text(value: object) -> str:
    """Remove implementation-only fragments from text entering the Telegram view."""

    lines: list[str] = []
    raw_id_pattern = re.compile(r"\b(?:post|message|row|db)_?id\s*[=:]", re.IGNORECASE)
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        lowered = line.casefold()
        if not line or "/srv/" in lowered or "/home/" in lowered or raw_id_pattern.search(line):
            continue
        if _is_telegram_technical_line(line):
            continue
        lines.append(line)
    return " ".join(lines).strip()


def _localize_telegram_unknown(value: str) -> str:
    translations = {
        "current external truth": "актуальность текущего утверждения",
        "external verification before current claims": "внешняя проверка перед текущими утверждениями",
        "local Telegram archive support": "поддержка в локальном Telegram-архиве",
        "sufficient cited proof for the requested claim": "достаточное цитируемое доказательство для утверждения",
    }
    return translations.get(value, value)


def _telegram_public_answer_summary(payload: Mapping[str, Any]) -> str:
    answer_gate = _safe_mapping(payload.get("answer_gate"))
    if not bool(answer_gate.get("allow_answer", True)):
        return "Недостаточно данных: локальный архив не подтверждает это утверждение."
    archive = _safe_mapping(payload.get("archive_evidence"))
    items = _safe_mapping_list(archive.get("items"))
    if items:
        snippet = _format_post_snippet(str(items[0].get("snippet") or items[0].get("content") or ""), limit=300)
        if snippet:
            return f"В архиве найдено {len(items)} релевантных источника. Основной сигнал: {snippet}"
    return "Недостаточно данных: локальных доказательств для уверенного вывода нет."


def _telegram_public_source_lines(archive: Mapping[str, Any], linked: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in _safe_mapping_list(archive.get("items"))[:4]:
        date = str(item.get("posted_at") or "")[:10] or "дата неизвестна"
        channel = str(item.get("channel_username") or "источник")
        snippet = _format_post_snippet(str(item.get("snippet") or item.get("content") or ""), limit=120)
        source_url = str(item.get("source_url") or item.get("telegram_url") or "").strip()
        lines.append(f"- {date} {channel}: {snippet}")
        if source_url:
            lines.append(f"  {source_url}")
    if not lines:
        for item in _safe_mapping_list(linked.get("items"))[:4]:
            title = str(item.get("normalized_title") or item.get("source_type") or "связанный источник")
            source_url = str(item.get("source_url") or item.get("normalized_url") or "").strip()
            lines.append(f"- {title}: {source_url}".rstrip(":"))
    return lines


def _telegram_public_next_action(next_steps: Mapping[str, Any]) -> str:
    for key in ("apply", "watch", "study", "ignore"):
        values = [str(item).strip() for item in next_steps.get(key) or [] if str(item).strip()]
        if values:
            translations = {
                "Keep as source-backed editorial angle.": "Сохранить как редакторский угол, опирающийся на источники.",
                "Do not apply this to active project work from the current evidence.": "Не применять к активному проекту на основании текущих доказательств.",
                "Treat this as a cross-project engineering signal, not a project-specific action.": (
                    "Использовать как общий инженерный сигнал для текущих проектов, "
                    "но не как действие для конкретного проекта без явной привязки."
                ),
                "Run an explicitly approved external verification step before making current claims.": "Перед текущими утверждениями отдельно разрешить внешнюю проверку.",
            }
            return _public_telegram_text(translations.get(values[0], values[0])) or "Не превращать этот сигнал в действие без более точных доказательств."
    return "Не превращать этот сигнал в действие без более точных доказательств."


def _telegram_project_relation(project_fit: Mapping[str, Any]) -> str:
    project_name = str(project_fit.get("project_name") or "").strip()
    if not project_name:
        return "Проект не указан: можно спросить, как тема относится к конкретному репозиторию."
    matched_terms = [str(item).strip() for item in project_fit.get("matched_terms") or [] if str(item).strip()]
    label = str(project_fit.get("relevance_label") or "no_match")
    if label == "direct_implication":
        terms = ", ".join(matched_terms[:4]) or "задачи проекта"
        return f"Есть прямая связь с {project_name}: источники пересекаются с контекстом проекта по {terms}."
    if label in {"weak_watch", "learning_relevance"}:
        terms = ", ".join(matched_terms[:4]) or "инженерным контекстом"
        return f"Для {project_name} это релевантный сигнал для изучения: пересечение по {terms}; проектное действие пока не доказано."
    return f"Для {project_name} прямое совпадение в найденных источниках не доказано; это пока общий инженерный контекст, а не рекомендация по проекту."


def _telegram_rag_source_count(payload: Mapping[str, Any]) -> int:
    archive = _safe_mapping(payload.get("archive_evidence"))
    linked = _safe_mapping(payload.get("linked_source_evidence"))
    return len(_safe_mapping_list(archive.get("items"))) + len(_safe_mapping_list(linked.get("items")))


def _synthesize_telegram_rag_answer(payload: Mapping[str, Any], *, mode: str) -> str:
    context = _telegram_rag_synthesis_context(payload, mode=mode)
    question = str(context.get("question") or "")
    ru = _looks_russian(question)
    title = "PRM Editor Brief" if mode == "brief" else "PRM Research"
    if ru and mode == "brief":
        title = "PRM редакторский бриф"
    prompt = (
        "You are the Telegram UX layer for a private Personal Research Memory assistant.\n"
        "The local RAG step has already run. Turn the bounded context into a polished, ready-to-read Telegram report.\n\n"
        "Hard rules:\n"
        "- Use only the bounded_context JSON below for source-grounded claims.\n"
        "- Do not use general model background as evidence.\n"
        "- Do not invent source links, channels, dates, companies, ROI, hiring, layoffs, or current facts.\n"
        "- If time_window.requested is true, treat that date window as a hard source eligibility boundary.\n"
        "- For freshness-scoped questions, do not present older sources as recent evidence. If no archive sources remain in the window, say that clearly instead of answering from older context.\n"
        "- If the context says external verification is required, state that clearly.\n"
        "- Keep the answer compact enough for Telegram: roughly 1200-2200 characters.\n"
        "- Same language as the user.\n"
        "- Include source references as short bullets using the provided source_url when present.\n"
        "- Do not include raw JSON or internal field names.\n"
        "- Use a clean visual layout: short headings, blank lines, and bullets. No tables and no code blocks.\n"
        "- Do not show technical metrics: no model_calls, cost, estimated_cost_usd, tool_calls, retrieval_mode, privacy footer, debug hints, budgets, or vector/backend internals.\n"
        "- The user wants a packaged report, not an audit receipt.\n\n"
        f"Preferred title: {title}\n"
        "Recommended structure for research:\n"
        "1. Title line with the topic.\n"
        "2. One-paragraph executive summary.\n"
        "3. Two to four thematic blocks with short readable headings. Group related sources by topic when multiple topics are present.\n"
        "4. What this means / how to use it.\n"
        "5. Sources.\n"
        "6. Boundaries: local archive only, no live web verification, no writes.\n\n"
        "Recommended structure for editor brief:\n"
        "1. Title line with the editorial topic.\n"
        "2. Position.\n"
        "3. Source-backed theses grouped by topic.\n"
        "4. Angles for a post.\n"
        "5. Sources.\n"
        "6. Boundaries: local archive only, no live web verification, no writes.\n\n"
        f"bounded_context:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )
    with suppress_usage_recording():
        receipt = LLMClient.complete_with_receipt(
            prompt=prompt,
            system="You produce concise, source-grounded Telegram answers from bounded private RAG context.",
            max_tokens=900,
            category="pi_chat",
        )
    answer = str(receipt.text or "").strip()
    if not answer:
        raise RuntimeError("empty_llm_synthesis")
    return _ensure_telegram_report_boundary(_telegram_report_without_technical_metrics(answer), ru=ru)


def _telegram_rag_synthesis_context(payload: Mapping[str, Any], *, mode: str) -> dict[str, Any]:
    archive = _safe_mapping(payload.get("archive_evidence"))
    linked = _safe_mapping(payload.get("linked_source_evidence"))
    time_window = _safe_mapping(payload.get("time_window"))
    answer_gate = _safe_mapping(payload.get("answer_gate"))
    next_steps = _safe_mapping(payload.get("next_steps"))
    project_fit = _safe_mapping(payload.get("project_fit"))
    privacy = _safe_mapping(payload.get("privacy"))
    archive_items = [
        {
            "date": str(item.get("posted_at") or "")[:10],
            "channel": item.get("channel_username"),
            "snippet": _format_post_snippet(str(item.get("snippet") or item.get("content") or ""), limit=260),
            "source_url": item.get("source_url") or item.get("telegram_url") or item.get("message_url"),
            "retrieval_mode": item.get("retrieval_mode"),
        }
        for item in _safe_mapping_list(archive.get("items"))[:5]
    ]
    linked_items = [
        {
            "title": item.get("normalized_title") or item.get("source_type"),
            "url": item.get("source_url") or item.get("normalized_url"),
            "excerpt": _format_post_snippet(str(item.get("text_excerpt") or ""), limit=220),
            "status": item.get("extraction_status"),
        }
        for item in _safe_mapping_list(linked.get("items"))[:3]
    ]
    return {
        "schema_version": "telegram_rag_llm_synthesis_context.v1",
        "mode": mode,
        "question": str(payload.get("question") or ""),
        "time_window": {
            "requested": bool(time_window.get("requested")),
            "strict": bool(time_window.get("strict")),
            "label": time_window.get("label"),
            "date_from": time_window.get("date_from"),
            "date_to": time_window.get("date_to"),
            "source": time_window.get("source"),
        },
        "local_direct_answer": str(payload.get("direct_answer") or ""),
        "answer_status": payload.get("status"),
        "answer_gate": {
            "allow_answer": answer_gate.get("allow_answer"),
            "external_verification_required": answer_gate.get("external_verification_required"),
            "current_claim_allowed": answer_gate.get("current_claim_allowed"),
            "reason": answer_gate.get("reason"),
        },
        "archive": {
            "status": archive.get("status"),
            "retrieval_mode": archive.get("retrieval_mode"),
            "sources": archive_items,
        },
        "linked_sources": linked_items,
        "project_fit": {
            "project_name": project_fit.get("project_name"),
            "relevance_label": project_fit.get("relevance_label"),
            "guidance": project_fit.get("guidance"),
        },
        "next_steps": {
            key: [str(item) for item in next_steps.get(key) or [] if str(item).strip()][:3]
            for key in ("apply", "watch", "ignore", "study")
        },
        "unknowns": [str(item) for item in payload.get("unknowns") or [] if str(item).strip()][:6],
        "privacy": {
            "local_retrieval_model_calls": privacy.get("model_calls"),
            "local_retrieval_provider_egress": privacy.get("provider_egress"),
            "raw_corpus_egress": False,
            "durable_writes": False,
        },
    }


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _looks_russian(text: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", str(text or "")))


def _telegram_report_without_technical_metrics(text: str) -> str:
    lines: list[str] = []
    previous_blank = False
    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip()
        if _is_telegram_technical_line(line):
            continue
        blank = not line.strip()
        if blank and previous_blank:
            continue
        lines.append(line)
        previous_blank = blank
    return "\n".join(lines).strip()


def _is_telegram_technical_line(line: str) -> bool:
    lowered = line.strip().casefold()
    if not lowered:
        return False
    prefixes = (
        "privacy:",
        "mode:",
        "режим:",
        "limits:",
        "лимиты:",
        "planner limits:",
        "details:",
        "подробности:",
        "llm synthesis:",
    )
    if lowered.startswith(prefixes):
        return True
    technical_markers = (
        "model_calls",
        "estimated_cost",
        "tool_calls=",
        "sources<=",
        "debug=",
        "bounded_telegram_snippet_provider_egress",
        "raw_telegram_corpus_egress",
        "linked_source_live_fetch",
        "vector_backend_used",
        "external_skill_used",
        "durable_writes",
        "retrieval_mode",
        "max_tool_calls",
        "max_archive_sources",
    )
    return any(marker in lowered for marker in technical_markers)


def _ensure_telegram_report_boundary(text: str, *, ru: bool) -> str:
    clean = _telegram_report_without_technical_metrics(text)
    lowered = clean.casefold()
    if "границ" in lowered or "ограничен" in lowered or "boundar" in lowered or "limits" in lowered:
        return clean
    boundary = (
        "Границы: отчёт собран по локальному архиву; live web не запускался; память и база не менялись."
        if ru
        else "Boundaries: local archive report; no live web verification; no memory/database writes."
    )
    return (clean.rstrip() + "\n\n" + boundary).rstrip()


def handle_operator_message(chat_id: str, args: str, settings: Settings) -> None:
    _handle_operator_message(chat_id, args, settings, input_kind="text")


def handle_voice_message(chat_id: str, args: str, settings: Settings) -> None:
    _handle_operator_message(chat_id, args, settings, input_kind="voice_transcript")


def _handle_operator_message(chat_id: str, args: str, settings: Settings, *, input_kind: str) -> None:
    text = args.strip()
    if not text:
        send_message(_get_bot_token(), chat_id, "Напиши вопрос, фидбек или напоминание.", parse_mode=None)
        return
    intent = classify_operator_message(text, input_kind=input_kind)
    if intent["intent"] == "reminder":
        handle_remind(chat_id, text, settings)
        return
    if intent["intent"] == "feedback":
        _handle_feedback_intake(chat_id, text, settings, input_kind=input_kind)
        return
    handle_chat(chat_id, text, settings)


def _prm_post_answer_markup(result: Mapping[str, Any], *, settings: Settings, chat_id: str) -> dict | None:
    answer_gate = _safe_mapping(result.get("answer_gate"))
    if not bool(answer_gate.get("allow_answer", True)):
        return None
    archive = _safe_mapping(result.get("archive_evidence"))
    linked = _safe_mapping(result.get("linked_source_evidence"))
    source_refs = [
        *[str(item.get("source_url") or "") for item in _safe_mapping_list(archive.get("items"))],
        *[str(item.get("source_url") or item.get("normalized_url") or "") for item in _safe_mapping_list(linked.get("items"))],
    ]
    project_fit = _safe_mapping(result.get("project_fit"))
    return build_post_answer_actions(
        {
            "question": result.get("question"),
            "direct_answer": result.get("direct_answer"),
            "source_refs": source_refs,
            "project_name": project_fit.get("project_name"),
        }, db_path=settings.db_path, chat_id=chat_id
    )["reply_markup"]


def _send_research_text(
    chat_id: str,
    text: str,
    *,
    token: str,
    limit: int = 3900,
    reply_markup: dict | None = None,
) -> None:
    chunks = _telegram_text_chunks(text, limit=limit)
    for index, chunk in enumerate(chunks):
        send_message(token, chat_id, chunk, parse_mode=None, reply_markup=reply_markup if index == len(chunks) - 1 else None)


def _telegram_text_chunks(text: str, *, limit: int = 3900) -> list[str]:
    clean = str(text or "").strip()
    if not clean:
        return [""]
    if len(clean) <= limit:
        return [clean]

    chunks: list[str] = []
    current = ""
    for paragraph in clean.split("\n\n"):
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(paragraph) > limit:
            chunks.append(paragraph[:limit].rstrip())
            paragraph = paragraph[limit:].lstrip()
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


def handle_chat(chat_id: str, args: str, settings: Settings) -> None:
    question = args.strip()
    if not question:
        send_message(_get_bot_token(), chat_id, "Напиши вопрос после /chat или просто отправь обычное сообщение.", parse_mode=None)
        return
    if not _telegram_provider_egress_allowed():
        _send_telegram_provider_egress_required(chat_id)
        return
    result = answer_pi_chat(question, settings=settings)
    send_message(_get_bot_token(), chat_id, render_prm_chat_answer(result, mode="llm-approved"), parse_mode=None)


def handle_remind(chat_id: str, args: str, settings: Settings) -> None:
    text = args.strip()
    if not text:
        send_message(
            _get_bot_token(),
            chat_id,
            "Usage: /remind завтра 18:00 дать feedback по Workbook",
            parse_mode=None,
        )
        return
    try:
        parsed = parse_reminder_request(text)
        with _with_db(settings) as connection:
            reminder = create_reminder(
                connection,
                due_at=parsed.due_at,
                text=parsed.text,
                reminder_type=parsed.reminder_type,
                source_text=text,
                recorded_by="telegram_bot",
            )
        send_message(
            _get_bot_token(),
            chat_id,
            (
                f"Напоминание добавлено #{reminder['id']}\n"
                f"Когда: {_format_local_due_at(parsed.due_at)}\n"
                f"Что: {reminder['text']}\n\n"
                "Я покажу его в дневном чек-ине с кнопками сделал / не сделал."
            ),
            parse_mode=None,
        )
    except Exception as exc:
        send_message(_get_bot_token(), chat_id, f"Не смог создать напоминание: {exc}", parse_mode=None)


def handle_reminders(chat_id: str, args: str, settings: Settings) -> None:
    del args
    with _with_db(settings) as connection:
        rows = list_pending_reminders(connection, limit=10)
    if not rows:
        send_message(_get_bot_token(), chat_id, "Активных напоминаний нет.", parse_mode=None)
        return
    lines = ["Активные напоминания"]
    for row in rows:
        lines.append(
            f"#{row['id']} · {_format_local_due_at(row['due_at'])} · {row['reminder_type']}: {row['text']}"
        )
    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_remind_cancel(chat_id: str, args: str, settings: Settings) -> None:
    first = args.strip().split(maxsplit=1)[0] if args.strip() else ""
    if not first.isdigit():
        send_message(_get_bot_token(), chat_id, "Usage: /remind_cancel <id>", parse_mode=None)
        return
    with _with_db(settings) as connection:
        reminder = cancel_reminder(connection, reminder_id=int(first))
    if reminder is None:
        send_message(_get_bot_token(), chat_id, f"Напоминание не найдено: {first}", parse_mode=None)
        return
    send_message(_get_bot_token(), chat_id, f"Напоминание отменено: #{first}", parse_mode=None)


def handle_costs(chat_id: str, args: str, settings: Settings) -> None:
    del args
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat().replace("+00:00", "Z")

    with _with_db(settings) as connection:
        total_row = connection.execute(
            """
            SELECT
                COUNT(*) AS calls,
                SUM(input_tokens) AS total_input,
                SUM(output_tokens) AS total_output,
                SUM(cost_usd) AS total_cost,
                AVG(duration_ms) AS avg_ms
            FROM llm_usage
            """
        ).fetchone()
        category_rows = connection.execute(
            """
            SELECT
                category,
                COUNT(*) AS calls,
                SUM(cost_usd) AS cost,
                AVG(duration_ms) AS avg_ms
            FROM llm_usage
            WHERE called_at >= ?
            GROUP BY category
            ORDER BY cost DESC
            """,
            (cutoff_30d,),
        ).fetchall()
        month_rows = connection.execute(
            """
            SELECT
                substr(called_at, 1, 7) AS month,
                SUM(cost_usd) AS cost,
                COUNT(*) AS calls
            FROM llm_usage
            GROUP BY month
            ORDER BY month DESC
            LIMIT 8
            """
        ).fetchall()

    total_calls = int(total_row["calls"] or 0)
    total_cost = float(total_row["total_cost"] or 0.0)
    avg_ms = float(total_row["avg_ms"] or 0.0)

    lines = [
        "LLM Usage Statistics",
        "",
        "All time:",
        f"  Calls: {total_calls} | Cost: ${total_cost:.4f} | Avg: {avg_ms / 1000:.1f}s",
        "",
        "By category (last 30 days):",
    ]

    if category_rows:
        for row in category_rows:
            lines.append(
                f"  {row['category']:<16} {int(row['calls'] or 0)} calls  "
                f"${float(row['cost'] or 0.0):.4f}  avg {float(row['avg_ms'] or 0.0) / 1000:.1f}s"
            )
    else:
        lines.append("  No usage in the last 30 days.")

    lines.extend(["", "By month:"])
    if month_rows:
        for row in month_rows:
            lines.append(
                f"  {row['month']}  {int(row['calls'] or 0)} calls  ${float(row['cost'] or 0.0):.4f}"
            )
    else:
        lines.append("  No usage recorded yet.")

    send_message(_get_bot_token(), chat_id, "\n".join(lines), parse_mode=None)


def handle_study(chat_id: str, args: str, settings: Settings) -> None:
    force = any(token.lower() in {"refresh", "rebuild", "force"} for token in args.split())
    content_md = generate_study_plan(settings, force=force)
    send_message(_get_bot_token(), chat_id, content_md, parse_mode="Markdown", escape_markdown=False)


def handle_study_done(chat_id: str, args: str, settings: Settings) -> None:
    notes = args.strip() or None
    try:
        week_label = mark_study_complete(settings, notes=notes)
        message = f"Study plan marked as completed for {week_label}."
        if notes:
            message += f"\nNotes: {notes}"
        send_message(_get_bot_token(), chat_id, message, parse_mode=None)
    except Exception as exc:
        send_message(_get_bot_token(), chat_id, f"Failed to update study progress: {exc}", parse_mode=None)


def handle_run_digest(chat_id: str, args: str, settings: Settings) -> None:
    force_delivery = args.strip().lower() in {"force", "--force", "redeliver"}
    if force_delivery:
        summary = run_digest(settings, force_delivery=True)
    else:
        summary = run_digest(settings)
    summary_lines = [summary.output_path]
    if summary.json_path:
        summary_lines.append(summary.json_path)
    send_report_preview(
        chat_id=chat_id,
        title="Дайджест сгенерирован",
        summary_lines=summary_lines,
        week_label=summary.week_label,
        token=_get_bot_token(),
    )


def handle_run_mvp_weekly(chat_id: str, args: str, settings: Settings) -> None:
    del args
    summary = run_mvp_weekly_pipeline(settings, deliver=True)
    lines = [
        summary.report_path or "No report path returned",
        f"status={summary.radar_status}",
        f"dossier_status={summary.dossier_status or 'unknown'}",
        f"seeds={summary.seed_count}",
    ]
    if summary.telegraph_url:
        lines.append(summary.telegraph_url)
    lines.append(source_mix_summary(summary))
    if summary.selected_title:
        lines.append(f"title={summary.selected_title}")
    send_report_preview(
        chat_id=chat_id,
        title="MVP of the Week generated",
        summary_lines=lines,
        week_label=summary.week_label,
        token=_get_bot_token(),
    )


def handle_status(chat_id: str, args: str, settings: Settings) -> None:
    del args
    with _with_db(settings) as connection:
        raw_posts_count = connection.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0]
        posts_count = connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        topics_count = connection.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
        projects_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        last_ingestion = connection.execute("SELECT MAX(ingested_at) FROM raw_posts").fetchone()[0] or "never"
        last_digest = connection.execute("SELECT MAX(week_label) FROM digests").fetchone()[0] or "none"

    channels_path = PROJECT_ROOT / "src" / "config" / "channels.yaml"
    active_channels = 0
    if channels_path.exists():
        for line in channels_path.read_text(encoding="utf-8").splitlines():
            if line.strip() == "active: true":
                active_channels += 1

    message = (
        f"Status\n"
        f"raw_posts: {raw_posts_count}\n"
        f"posts: {posts_count}\n"
        f"topics: {topics_count}\n"
        f"projects: {projects_count}\n"
        f"last_ingestion: {last_ingestion}\n"
        f"last_digest: {last_digest}\n"
        f"active_channels: {active_channels}"
    )
    send_message(_get_bot_token(), chat_id, message, parse_mode=None)


def _handle_mark_feedback(chat_id: str, args: str, settings: Settings, feedback_value: str) -> None:
    post_ref = args.strip().split()[0] if args.strip() else ""
    if not post_ref:
        send_message(
            _get_bot_token(),
            chat_id,
            f"Usage: /mark_{'useful' if feedback_value == 'acted_on' else 'skipped'} <post_id|link>",
            parse_mode=None,
        )
        return
    try:
        with _with_db(settings) as connection:
            row = _resolve_post_reference(connection, post_ref)
            if row is None:
                send_message(
                    _get_bot_token(),
                    chat_id,
                    f"Post not found: {post_ref}",
                    parse_mode=None,
                )
                return
            post_id = int(row["id"])
            record_feedback(connection, post_id, feedback_value)
        send_message(
            _get_bot_token(),
            chat_id,
            f"Feedback recorded: {feedback_value} for post {post_id}",
            parse_mode=None,
        )
    except Exception as exc:
        send_message(_get_bot_token(), chat_id, f"Failed to record feedback: {exc}", parse_mode=None)


def _handle_post_tag(chat_id: str, args: str, settings: Settings, tag_value: str | None = None) -> None:
    parts = args.strip().split(maxsplit=2)
    if tag_value is None:
        if len(parts) < 2:
            send_message(
                _get_bot_token(),
                chat_id,
                "Usage: /tag <post_id|link> <strong|interesting|try|funny|low|later>",
                parse_mode=None,
            )
            return
        post_ref, raw_tag = parts[0], parts[1]
        note = parts[2] if len(parts) > 2 else None
        normalized_tag = _normalize_tag(raw_tag)
    else:
        if not parts:
            send_message(
                _get_bot_token(),
                chat_id,
                f"Usage: /mark_{tag_value} <post_id|link>",
                parse_mode=None,
            )
            return
        post_ref = parts[0]
        note = parts[1] if len(parts) > 1 else None
        normalized_tag = _normalize_tag(tag_value)

    if not post_ref or normalized_tag is None:
        send_message(
            _get_bot_token(),
            chat_id,
            "Usage: /tag <post_id|link> <strong|interesting|try|funny|low|later>",
            parse_mode=None,
        )
        return
    try:
        with _with_db(settings) as connection:
            row = _resolve_post_reference(connection, post_ref)
            if row is None:
                send_message(_get_bot_token(), chat_id, f"Post not found: {post_ref}", parse_mode=None)
                return
            post_id = int(row["id"])
            record_post_tag(connection, post_id, normalized_tag, note)
            snippet = _format_post_snippet(row["content"], limit=100)
        send_message(
            _get_bot_token(),
            chat_id,
            f"Tag saved: {normalized_tag} for post {post_id}\n@{row['channel_username']}: {snippet}",
            parse_mode=None,
        )
    except Exception as exc:
        send_message(_get_bot_token(), chat_id, f"Failed to save tag: {exc}", parse_mode=None)


def handle_mark_useful(chat_id: str, args: str, settings: Settings) -> None:
    _handle_mark_feedback(chat_id, args, settings, "acted_on")


def handle_mark_skipped(chat_id: str, args: str, settings: Settings) -> None:
    _handle_mark_feedback(chat_id, args, settings, "skipped")


def handle_tag(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings)


def handle_mark_strong(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings, "strong")


def handle_mark_interesting(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings, "interesting")


def handle_mark_try(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings, "try")


def handle_mark_funny(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings, "funny")


def handle_mark_low(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings, "low")


def handle_mark_later(chat_id: str, args: str, settings: Settings) -> None:
    _handle_post_tag(chat_id, args, settings, "later")


def _handle_feedback_intake(chat_id: str, args: str, settings: Settings, *, input_kind: str) -> None:
    week_label, text = _parse_week_label_args(args)
    if not text:
        command = "/feedback_voice" if input_kind == "voice_transcript" else "/feedback"
        send_message(_get_bot_token(), chat_id, f"Usage: {command} [week] <feedback text>", parse_mode=None)
        return
    try:
        with _with_db(settings) as connection:
            intake = create_feedback_intake(
                connection,
                week_label=week_label,
                text=text,
                input_kind=input_kind,
                recorded_by="telegram_bot",
            )
        send_message(_get_bot_token(), chat_id, intake["confirmation_summary"], parse_mode=None)
    except Exception as exc:
        send_message(_get_bot_token(), chat_id, f"Failed to draft feedback: {exc}", parse_mode=None)


def handle_feedback(chat_id: str, args: str, settings: Settings) -> None:
    _handle_feedback_intake(chat_id, args, settings, input_kind="text")


def handle_feedback_voice(chat_id: str, args: str, settings: Settings) -> None:
    _handle_feedback_intake(chat_id, args, settings, input_kind="voice_transcript")


def _parse_feedback_intake_id(args: str) -> int | None:
    first = args.strip().split(maxsplit=1)[0] if args.strip() else ""
    if not first.isdigit() or int(first) <= 0:
        return None
    return int(first)


def handle_feedback_confirm(chat_id: str, args: str, settings: Settings) -> None:
    intake_id = _parse_feedback_intake_id(args)
    if intake_id is None:
        send_message(_get_bot_token(), chat_id, "Usage: /feedback_confirm <draft_id>", parse_mode=None)
        return
    try:
        with _with_db(settings) as connection:
            result = apply_confirmed_feedback_intake(
                connection,
                intake_id=intake_id,
                recorded_by="telegram_bot_confirmed",
            )
        send_message(
            _get_bot_token(),
            chat_id,
            (
                f"Confirmed feedback draft #{intake_id}\n"
                f"memory_writes={len(result['created_events'])}\n"
                f"manual_suggestions={len(result['suggestions'])}"
            ),
            parse_mode=None,
        )
    except Exception as exc:
        send_message(_get_bot_token(), chat_id, f"Failed to confirm feedback: {exc}", parse_mode=None)


def handle_feedback_discard(chat_id: str, args: str, settings: Settings) -> None:
    intake_id = _parse_feedback_intake_id(args)
    if intake_id is None:
        send_message(_get_bot_token(), chat_id, "Usage: /feedback_discard <draft_id>", parse_mode=None)
        return
    try:
        with _with_db(settings) as connection:
            intake = discard_feedback_intake(connection, intake_id=intake_id)
        send_message(
            _get_bot_token(),
            chat_id,
            f"Discarded feedback draft #{intake['id']}",
            parse_mode=None,
        )
    except Exception as exc:
        send_message(_get_bot_token(), chat_id, f"Failed to discard feedback: {exc}", parse_mode=None)


HANDLERS: dict[str, Callable[[str, str, Settings], None]] = {
    "/start": handle_start,
    "/help": handle_start,
    "/message": handle_operator_message,
    "/voice": handle_voice_message,
    "/weekly": handle_weekly,
    "/actions": handle_actions,
    "/explain": handle_explain,
    "/projects": handle_projects,
    "/mvp": handle_mvp,
    "/strategy": handle_strategy,
    "/codex": handle_codex,
    "/auto": handle_auto,
    "/auto_voice": handle_auto_voice,
    "/chat": handle_chat,
    "/hermes": handle_chat,
    "/research": handle_research,
    "/brief": handle_research_brief,
    "/remind": handle_remind,
    "/reminders": handle_reminders,
    "/remind_cancel": handle_remind_cancel,
    "/digest": handle_digest,
    "/topics": handle_topics,
    "/insight": handle_insight,
    "/project": handle_project,
    "/ask": handle_ask,
    "/study": handle_study,
    "/study_done": handle_study_done,
    "/costs": handle_costs,
    "/run_digest": handle_run_digest,
    "/run_mvp_weekly": handle_run_mvp_weekly,
    "/status": handle_status,
    "/refresh": handle_refresh,
    "/reactions": handle_reactions,
    "/mark_useful": handle_mark_useful,
    "/mark_skipped": handle_mark_skipped,
    "/feedback": handle_feedback,
    "/feedback_voice": handle_feedback_voice,
    "/feedback_confirm": handle_feedback_confirm,
    "/feedback_discard": handle_feedback_discard,
    "/tag": handle_tag,
    "/mark_strong": handle_mark_strong,
    "/mark_interesting": handle_mark_interesting,
    "/mark_try": handle_mark_try,
    "/mark_funny": handle_mark_funny,
    "/mark_low": handle_mark_low,
    "/mark_later": handle_mark_later,
}


def dispatch_command(
    chat_id: str,
    text: str,
    settings: Settings,
    *,
    runtime_mode: str = BOT_RUNTIME_LEGACY,
) -> None:
    command, _, args = text.strip().partition(" ")
    command = command.split("@", maxsplit=1)[0]
    mode = normalize_bot_runtime_mode(runtime_mode)
    if mode == BOT_RUNTIME_PRM_ASSISTANT:
        if command in {"/start", "/help"}:
            handle_prm_start(chat_id, args, settings)
            return
        if command not in PRM_SAFE_COMMANDS:
            _send_prm_safe_blocked(chat_id, command)
            return

    handler = HANDLERS.get(command)
    if handler is None:
        send_message(
            _get_bot_token(),
            chat_id,
            "Unknown command. Use /start to see the available commands.",
            parse_mode=None,
        )
        return

    try:
        handler(chat_id, args, settings)
    except sqlite3.OperationalError:
        LOGGER.warning("Bot handler database error command=%s", command, exc_info=True)
        _friendly_handler_error(chat_id)
    except error.HTTPError:
        LOGGER.warning("Bot handler HTTP error command=%s", command, exc_info=True)
        _friendly_handler_error(chat_id)
    except Exception:
        LOGGER.exception("Bot handler failed command=%s", command)
        _friendly_handler_error(chat_id)
