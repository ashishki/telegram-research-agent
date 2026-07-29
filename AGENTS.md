# Codex Handoff

Status: active
Last updated: 2026-07-29

## Product Direction

The repository is being retrofitted from a weekly-report-centered Telegram
intelligence system into Personal Telegram Research Memory + Grounded Assistant.
HEAD contains corrective PRM implementation slices through PRM-7 and PRM-9
through PRM-13, including bounded SQLite FTS archive search, a grounded
assistant vertical slice, deterministic external-verification requirement
routing, confirmation-gated saved memory proposals, and a deterministic
Knowledge Library topic-page renderer. HEAD also contains PRM-14 deterministic
project context and decision-support routing, PRM-15 corrected learning-state
projection/migration semantics, and PRM-16 deterministic Weekly Brief V3
projection with legacy Brief/Atlas demotion semantics. HEAD also contains
PRM-17 deterministic runtime workflow contracts and privacy-safe aggregate
telemetry receipts. The PRM-13 through PRM-17 batched deep review is recorded.
PRM-18 deterministic release/dogfood gate is implemented and currently blocks
dogfood because final acceptance evidence, gold retrieval labels, and explicit
human dogfood approval are missing. PRM-8 remains blocked. PRM-19 and PRM-20
are not started; PRM-19 requires real four-week operator dogfood approval and
evidence, and PRM-20 requires PRM-19 evidence plus explicit compatibility
archive/delete/move approval.

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

PRM-18 is implemented as a blocking release gate. Do not start PRM-19 dogfood
until the human operator explicitly approves dogfood start and accepts or clears
the PRM-18 blockers. Do not start PRM-20 cleanup/archive work until PRM-19
dogfood evidence exists and the human operator approves any compatibility
archive/delete/move.
