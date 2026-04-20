# CODEX_PROMPT — Session Handoff
_v3.1 · 2026-04-20 · telegram-research-agent_

---

## Current State

- Phases 1–4 (memory unification roadmap) complete.
- Active problem: weekly brief produces near-empty output when no manual tags exist for the current week.
- Root cause confirmed via data analysis (W17 post-mortem):
  - `strong_count = 0` for three consecutive weeks — scoring never promotes any post to "strong" bucket.
  - Preference judge runs (6 batches, 24 candidates in W17) but its output is blocked by `include=True` gate in `_build_auto_watch_lines`.
  - Judge prompt says "Be selective. Prefer fewer items." — makes it too conservative.
  - `run_recommendations` (implementation brief) silently crashed in W17 — no `insight` LLM call in `llm_usage`, no W17 entry in `recommendations` table. Caught by bare `except Exception` with no traceback.
  - "No comparison baseline" — `AGENT_DB_PATH` env var absent; `_load_previous_quality_metrics()` can't read DB.
- `pytest` available via: `python -m pytest`
- Orchestrator-to-Codex execution path: `codex exec -s workspace-write`

---

## What Exists

- Telegram ingestion, normalization, scoring, and topic assignment
- project relevance, personalization, and weekly report generation
- explicit feedback and tagging
- derived `channel_memory` and `project_context_snapshots`
- `signal_evidence_items` and `decision_journal` tables (unified memory)
- implementation-idea triage and rejection memory
- scope-first retrieval helpers

---

## Active Architecture Concern

Phases 1–4 added the memory plumbing. The system now has project context, channel memory, evidence items, and decision history — but the weekly report pipeline does not fully use this to produce autonomous output.

The preference judge should be the primary signal-discovery mechanism. Instead, manual tagging is still de facto required for a non-empty brief.

---

## Exact Next Execution Step

Implement **Phase 5 — Autonomous Signal Discovery** from `docs/tasks.md`.

Execute in this order:

1. **A5-3** — fix silent `run_recommendations` crash (add try/except around `_load_project_context_snapshots`; improve exception logging in `generate_digest.py`)
2. **A5-1** — relax judge prompt: replace "Be selective. Prefer fewer items." with an explicit inclusion policy
3. **A5-2** — soften `_build_auto_watch_lines` gate: use `category + confidence ≥ 0.65` instead of requiring `include=True`
4. **A5-4** — fix "No comparison baseline": thread `db_path` from `settings` through to `_load_previous_quality_metrics`

Do not start scoring recalibration (strong_count=0 issue) in this phase — that is a separate task.

Reference documents:

- `docs/tasks.md` (Phase 5 section for exact specs)
- `docs/IMPLEMENTATION_CONTRACT.md`
- `docs/architecture.md`
