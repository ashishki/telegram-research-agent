# CODEX_PROMPT — Session Handoff
_v3.2 · 2026-04-20 · telegram-research-agent_

---

## Current State

- Phases 1–5 complete.
- Phase 5 (Autonomous Signal Discovery) shipped 2026-04-20:
  - Preference judge prompt relaxed — `include=True` by default for any actionable signal
  - `_build_auto_watch_lines` gate softened — uses `category + confidence ≥ 0.65` instead of requiring `include=True`
  - `run_recommendations` silent crash fixed — snapshot refresh failure now logged with traceback; LLM call proceeds with fallback context
  - "What Changed" baseline fixed — `db_path` threaded from `settings` through to `_load_previous_quality_metrics`
- All roadmap phases (1–5) are complete. No active phase.
- `pytest` available via: `python3 -m pytest`
- Orchestrator-to-Codex execution path: write prompt to file, then `codex exec -s workspace-write < /tmp/prompt.md`

---

## What Exists

- Telegram ingestion, normalization, scoring, and topic assignment
- project relevance, personalization, and weekly report generation
- explicit feedback and tagging
- derived `channel_memory` and `project_context_snapshots`
- `signal_evidence_items` and `decision_journal` tables (unified memory)
- implementation-idea triage and rejection memory
- scope-first retrieval helpers
- autonomous signal discovery via preference judge (category + confidence gate)

---

## Known Open Issues

- `strong_count = 0` for W15–W17 — scoring calibration, separate from current phase.

---

## Active Architecture State

The weekly pipeline now has:
- project context snapshots (GitHub-derived)
- channel memory
- decision journal
- evidence items
- preference judge with generous inclusion policy

---

## Exact Next Execution Step

Implement **Phase 6 — Fix SQLite Transaction Conflicts** from `docs/tasks.md`.

Execute in this order:

1. **A6-1** — remove explicit `BEGIN` from `generate_recommendations.py` (lines 531, 539)
2. **A6-2** — remove explicit `BEGIN` from `generate_study_plan.py` (line 379)
3. **A6-3** — add `timeout=5` to `sqlite3.connect()` in `llm/client.py:_record_usage`

These are surgical one-line removals. Do not refactor connection management beyond what is specified.

Reference documents:

- `docs/tasks.md` (Phase 6 section for exact specs)
- `docs/IMPLEMENTATION_CONTRACT.md`
- `docs/architecture.md`
