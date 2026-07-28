# Codex Handoff

Status: active
Last updated: 2026-07-28

## Product Direction

The repository is being retrofitted from a weekly-report-centered Telegram
intelligence system into Personal Telegram Research Memory + Grounded Assistant.
HEAD contains corrective PRM implementation slices through PRM-7 and PRM-9
through PRM-13, including bounded SQLite FTS archive search, a grounded
assistant vertical slice, deterministic external-verification requirement
routing, confirmation-gated saved memory proposals, and a deterministic
Knowledge Library topic-page renderer. HEAD also contains PRM-14 deterministic
project context and decision-support routing. PRM-8 and PRM-15 through PRM-20 are not
implemented.

## Operating Rules

- Work directly in this repository; do not spawn nested Codex CLI processes for
  bootstrap or implementation.
- Do not run live Telegram ingestion, reaction sync, Radar, Frontier, report
  generation, full archive LLM backfill, embeddings, or external web research
  jobs unless a task explicitly authorizes it.
- Do not modify production database contents.
- Do not commit private Telegram data or generated private reports.
- Do not enable external skills without approved trust records.
- Human operator is final completion authority.

## Canonical Docs

- docs/CODEX_PROMPT.md
- docs/tasks.md
- docs/PROJECT_BRIEF.md
- docs/ARCHITECTURE.md
- docs/IMPLEMENTATION_CONTRACT.md
- docs/personal_research_memory_product_contract.md
- docs/final_acceptance_plan.md
- docs/PRIVACY_THREAT_MODEL.md
- docs/COST_BUDGET.md

## Current Next Task

Continue at PRM-15 only if the human operator wants to proceed within the open
PRM-13 through PRM-17 implementation block. The next batched deep-review gate is
before PRM-18, unless a stop-ship boundary requires immediate review earlier.
