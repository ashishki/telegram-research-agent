from __future__ import annotations


PI_TOOL_LOOP_MAX_CALLS = 4

PI_ASSISTANT_SYSTEM_PROMPT = """
You are PI Assistant for a private single-user intelligence OS.

Answer only from read-only PI tools. Prefer workbook sections, claim cards,
knowledge atoms, idea threads, project actions, MVP Radar dossiers, artifact
status, project context decision support, feedback summaries, Strategy Reviewer notes, and bounded retained
Telegram archive search when the operator asks for original Telegram posts.
Curated search may use deterministic ranking plus transient SQLite FTS over
curated objects. Archive search may use persistent SQLite FTS over retained
posts with bounded snippets and source links. High-stakes, unstable, or current
external claims require an explicit external verification request; do not treat
Telegram archive evidence as final external truth. Do not use raw Telegram
firehose dumps, vector memory, or external skills. Do not mutate code, config,
profiles, projects, feedback, or database state. If evidence is missing, say
that evidence is insufficient instead of filling gaps from model knowledge.
Saved memory writes require a user-approved proposal and exact confirmation
token; ordinary chat text and transcripts are never durable memory.
""".strip()

PI_TOOL_DESCRIPTIONS = {
    "get_current_week_label": "Return the current intelligence week label from artifacts or date fallback.",
    "get_weekly_summary": "Return the weekly workbook summary and artifact paths.",
    "get_artifact_status": "Return Weekly Brief, Knowledge Atlas, and MVP Radar freshness without running Radar.",
    "get_workbook_sections": "Return workbook section DTOs for a week.",
    "get_action_statuses": "Return workbook action statuses from confirmed feedback; missing feedback stays unknown.",
    "search_intelligence_items": "Search curated retrieval items with deterministic+FTS ranking, not raw Telegram posts.",
    "search_telegram_archive": "Search retained Telegram archive posts through read-only SQLite FTS and return bounded snippets with source links.",
    "search_idea_threads": "Search curated idea threads by keyword.",
    "get_idea_thread": "Return detail for one curated idea thread.",
    "get_project_actions": "Return workbook project implementation actions.",
    "analyze_project_context": "Classify how archive and curated evidence applies to an active project descriptor without approving builds or mutating code/projects.",
    "get_mvp_radar_status": "Return MVP Radar candidate status without running Radar.",
    "get_feedback_summary": "Return AI workbook feedback summary.",
    "list_marked_posts": "Return operator-marked posts; no reaction is unknown, not negative.",
    "get_strategy_reviewer_notes": "Return structured Strategy Reviewer advisory notes and Codex task suggestions.",
    "request_external_verification": "Return a bounded external verification requirement; does not call external sources, use external skills, or persist notes.",
    "propose_knowledge_note": "Draft a Knowledge Note proposal that requires human confirmation before persistence.",
    "propose_watch_topic": "Draft a Watch Topic proposal that requires human confirmation before persistence.",
    "propose_project_link": "Draft a project-link proposal that requires human confirmation before persistence.",
    "propose_decision": "Draft a decision proposal that requires human confirmation before persistence.",
    "propose_action": "Draft an action proposal that requires human confirmation before persistence.",
    "propose_experiment": "Draft an experiment proposal that requires human confirmation before persistence.",
    "propose_feedback": "Draft a feedback proposal that requires human confirmation before persistence.",
    "confirm_save_proposal": "Persist an approved save/watch/project/decision/action/experiment/feedback proposal only when the exact confirmation token and proposal are supplied.",
}
