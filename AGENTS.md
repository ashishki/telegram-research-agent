# Codex Handoff

Status: active
Last updated: 2026-08-03

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
human dogfood approval are missing. PRM-18A Operator LLM Chat UX Contract,
PRM-18B LLM-backed memory chat CLI, and PRM-18C Telegram `prm-assistant` UX
parity/runbook are implemented; the PRM-18A through PRM-18C batched deep review
is recorded. The polished project-aware research-session assistant target is
documented by PRM-21, but PRM-22 and PRM-23 implementation is not done and is
not dogfood evidence. PRM-8 remains blocked. PRM-19 and PRM-20 are not started; PRM-19
requires explicit human dogfood-start approval plus accepted or cleared PRM-18
blockers and real four-week operator dogfood evidence, and PRM-20 requires
PRM-19 evidence plus explicit compatibility archive/delete/move approval. The old live
Telegram bot and
Report V2 weekly timer were stopped and disabled on 2026-07-29; see
`docs/PRODUCT_OPERATING_MODEL.md` and
`docs/audit/PRM_RUNTIME_FREEZE_2026-07-29.md`. A dedicated safe
`prm-assistant` runtime entrypoint and repo unit template exist, but they are
not installed, enabled, started, or dogfood evidence; the safe entrypoint does
not run automatic startup migrations. A local user-facing `memory ask` command
exists for immediate local evidence questions without LLM calls, external
search, service starts, migrations, or writes.

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

Stop before PRM-19. Do not start PRM-19 dogfood until the human operator
explicitly approves dogfood start and the PRM-18 blockers are accepted or
cleared. Do not start PRM-20 cleanup/archive work until PRM-19 dogfood evidence
exists and the human operator approves any compatibility archive/delete/move.
Do not restart legacy bot/report timers as PRM dogfood. Do not start
`prm-assistant` as dogfood without the same explicit approval. The
PRM-18A..PRM-18C deep review boundary is recorded at
`docs/audit/PRM_DEEP_REVIEW_PRM18A_18C_2026-08-03.md`.
PRM-21 records the future polished-assistant contract. PRM-22..PRM-23 are
proposed implementation tasks; do not treat them as dogfood evidence or as
approval for web research, provider egress, service start, or vector/backend
adoption.
