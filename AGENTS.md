# Codex Handoff

Status: active
Last updated: 2026-08-11

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
PRM-18 deterministic release/dogfood gate is implemented. The current
post-PRM28 receipt records deterministic local no-vector RAG readiness but
still blocks dogfood because explicit human dogfood-start approval is missing.
PRM-18A Operator LLM
Chat UX Contract,
PRM-18B LLM-backed memory chat CLI, and PRM-18C Telegram `prm-assistant` UX
parity/runbook are implemented; the PRM-18A through PRM-18C batched deep review
is recorded. The polished project-aware research-session assistant target is
documented by PRM-21. PRM-22 implements a fixture-first linked-source
resolver/cache, and PRM-23 implements a bounded fixture-first `memory research`
planner/CLI with no live fetch, provider call, service start, dogfood evidence,
durable production write/cache, or vector/backend approval. PRM-24 now has a
50-row operator-approved generated seed gold set and a privacy-safe SQLite FTS
baseline report; the labels are not independent human review evidence. PRM-26
accepted the no-vector path for now under
`operator-approval-2026-08-11-no-vector-prm28-path`, and PRM-28 implements the
no-vector answer gate over SQLite FTS/context pack with provider egress,
embeddings, vector backend, service start, migrations, production writes, and
dogfood all false. The current post-PRM28 gate receipt is
`evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json`; it leaves
`dogfood_started=false` and `release_claimed=false`. PRM-24 through PRM-28
formalize the required full product RAG path before dogfood: gold eval set,
citation-safe context pack,
hybrid/vector ADR and privacy budget, approved retrieval implementation, and
product chat acceptance gate. PRM-8
remains blocked until that approval path is satisfied. PRM-19 and PRM-20 are
not started; PRM-19 requires explicit human dogfood-start approval before it
can start and real four-week operator dogfood evidence before it can complete.
PRM-20 requires PRM-19 evidence plus explicit compatibility archive/delete/move
approval. The old live
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

No further PRM implementation task is eligible under the current hard stops.
PRM-24's 50 generated seed gold labels were operator-approved on 2026-08-11
under `operator-approval-2026-08-11-all-50-generated-gold`; PRM-26 accepted the
no-vector path under `operator-approval-2026-08-11-no-vector-prm28-path`; PRM-28
implemented the no-vector answer gate. These do not approve embeddings, a
vector backend, provider egress, live research, service start, production
writes, or dogfood. The post-PRM28 PRM-18 receipt has deterministic local
stop-ship blockers clear, but it remains blocked on explicit dogfood-start
approval. Do not start PRM-19 dogfood until the human operator explicitly
approves dogfood start. Do not start PRM-20 cleanup/archive work until PRM-19 dogfood evidence
exists and the human operator approves any compatibility archive/delete/move.
Do not restart legacy bot/report timers as PRM dogfood. Do not start
`prm-assistant` as dogfood without the same explicit approval. The
PRM-18A..PRM-18C deep review boundary is recorded at
`docs/audit/PRM_DEEP_REVIEW_PRM18A_18C_2026-08-03.md`.
PRM-21 records the future polished-assistant contract. PRM-22 and PRM-23 are
implemented fixture-first only; do not treat them as dogfood evidence or as
approval for web research, provider egress, service start, durable production
cache writes, production DB writes, or vector/backend adoption. PRM-27 hybrid
retrieval implementation remains blocked unless a future successor vector ADR
is explicitly approved.
