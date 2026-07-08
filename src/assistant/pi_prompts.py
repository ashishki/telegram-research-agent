from __future__ import annotations


PI_TOOL_LOOP_MAX_CALLS = 4

PI_ASSISTANT_SYSTEM_PROMPT = """
You are PI Assistant for a private single-user intelligence OS.

Answer only from curated intelligence tools. Prefer workbook sections, claim
cards, knowledge atoms, idea threads, project actions, MVP Radar dossiers,
feedback summaries, and Strategy Reviewer notes. Curated search may use
deterministic ranking plus transient SQLite FTS over those objects only. Do not
use raw Telegram firehose retrieval or vector memory. Do not mutate code,
config, profiles, projects, feedback, or database state. If curated evidence is
missing, say that evidence is insufficient instead of filling gaps from model
knowledge.
""".strip()

PI_TOOL_DESCRIPTIONS = {
    "get_current_week_label": "Return the current intelligence week label from artifacts or date fallback.",
    "get_weekly_summary": "Return the weekly workbook summary and artifact paths.",
    "get_workbook_sections": "Return workbook section DTOs for a week.",
    "get_action_statuses": "Return workbook action statuses from confirmed feedback; missing feedback stays unknown.",
    "search_intelligence_items": "Search curated retrieval items with deterministic+FTS ranking, not raw Telegram posts.",
    "search_idea_threads": "Search curated idea threads by keyword.",
    "get_idea_thread": "Return detail for one curated idea thread.",
    "get_project_actions": "Return workbook project implementation actions.",
    "get_mvp_radar_status": "Return MVP Radar candidate status without running Radar.",
    "get_feedback_summary": "Return AI workbook feedback summary.",
    "list_marked_posts": "Return operator-marked posts; no reaction is unknown, not negative.",
    "get_strategy_reviewer_notes": "Return structured Strategy Reviewer advisory notes and Codex task suggestions.",
}
