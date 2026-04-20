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

## Known Open Issues (not yet roadmapped)

- `strong_count = 0` for W15–W17 — scoring engine calibration needed; no post ever reaches "strong" bucket. Tracked as A6, separate from Phase 5.

---

## Active Architecture State

The weekly pipeline now has:
- project context snapshots (GitHub-derived)
- channel memory
- decision journal
- evidence items
- preference judge with generous inclusion policy

The brief should now produce auto-selected signals from `watch`/`cultural` posts without any manual tagging this week.

---

## Next Execution Step

No active phase. Await new roadmap item or A6 (scoring recalibration).

If starting A6, scope it as a standalone phase with:
- root cause analysis of why `signal_score` never reaches 0.75 threshold
- calibration changes to `src/config/scoring.yaml` or `src/processing/score_posts.py`
- success criterion: at least 1 post reaches "strong" bucket in a normal week

Reference documents:

- `docs/tasks.md`
- `docs/IMPLEMENTATION_CONTRACT.md`
- `docs/architecture.md`
