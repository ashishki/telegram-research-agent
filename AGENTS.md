# Codex Handoff

Status: active
Last updated: 2026-07-26

## Product Direction

The repository is being retrofitted from a weekly-report-centered Telegram
intelligence system into Personal Telegram Research Memory + Grounded Assistant.
The assistant and full-archive search are planned, not implemented.

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

PRM-1 - Corpus Inventory, Data Readiness, And Gold Query Process.
