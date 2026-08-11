# Codex Session Handoff

Status: active
Last updated: 2026-08-11

## Repository State

- Target repository commit inspected before retrofit: ad8689fa25b89f77122c4cec7c7a6b9da3f500cf
- Target branch: master
- AI Workflow Playbook commit used: 5583eca96c4d2d480b5574ed78bea63e0b07ebf0
- Adoption mode: Standard
- Current phase: PRM-18 release/dogfood gate is implemented. The current
  post-PRM28 receipt records deterministic local no-vector RAG readiness and
  blocks dogfood start because explicit human dogfood-start approval is
  missing; legacy
  live runtime is frozen; safe `prm-assistant` runtime is installed, enabled,
  and running for manual operator testing only as of 2026-08-11 18:27 CEST, not
  dogfood evidence; PRM-18A through PRM-18C are
  implemented and their batched deep review is recorded. PRM-21 documentation
  records the future project-aware research-session assistant target, PRM-22
  implements its fixture-first linked-source resolver/cache layer, and PRM-23
  implements a bounded fixture-first `memory research` planner/CLI.
- Implemented slices in HEAD: PRM-1 through PRM-7 plus PRM-9 through PRM-18C,
  PRM-21 docs-only research-session contract, PRM-22 fixture-first
  linked-source resolver/cache, and PRM-23 fixture-first memory research
  planner/CLI, PRM-24 generated seed eval coverage, PRM-26 accepted no-vector
  gate, PRM-28 no-vector answer gate, and PRM-27 local vector sidecar
- Current safe slice: PRM-27 local vector sidecar is implemented under
  `operator-approval-2026-08-11-full-stack-local-vector-telegram-llm`. PRM-24 now has a
  50-row operator-approved generated seed gold set and SQLite FTS baseline
  report under `operator-approval-2026-08-11-all-50-generated-gold`; this is
  generated seed evidence, not independent human review. PRM-26 accepted the no-vector path under
  `operator-approval-2026-08-11-no-vector-prm28-path`, and PRM-28 implements
  the no-vector answer gate. PRM-27 later adds a gitignored local SQLite vector
  sidecar and hybrid retrieval flags without external embeddings, production
  migrations, canonical DB writes, or dogfood start. A later 2026-08-11
  operator instruction enabled the local vector/RAG/LLM/Telegram stack for
  manual testing: the sidecar was built, PRM hybrid retrieval and Telegram
  LLM/router flags were set in the host `.env`, and
  `telegram-prm-assistant.service` was installed, enabled, and started. The
  current post-PRM28 PRM-18 receipt is
  `evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json`. A local UX
  trial is recorded at `docs/audit/PRM_LOCAL_UX_TRIAL_2026-08-11.md`: RAG is
  technically usable. A follow-up safe UX polish adds compact default
  `memory research` rendering, `--debug` audit rendering, Russian heading
  localization, freshness-first current-fact boundaries, local path redaction,
  narrow repo-context cues, and no drafts for current-fact freshness-boundary
  answers.
- Blocked/not implemented slices: PRM-8, PRM-19, and PRM-20 remain blocked
  until their gates are satisfied.
- Next safe work: local operator smoke/preflight for vector-backed Telegram
  testing is eligible; stop before PRM-19 dogfood.
  PRM-19 only after explicit human dogfood-start approval exists. The current
  post-PRM28 PRM-18 receipt has deterministic local stop-ship blockers clear
  but still blocks dogfood on missing dogfood-start approval.
  PRM-20 only after real dogfood evidence and explicit compatibility
  archive/delete/move approval.

## Product Direction

The product pivot is proposed, not accepted:

Personal Telegram Research Memory + Grounded Assistant replaces the weekly
report as the product center. Full archive search is the primary planned value.
Knowledge Atoms, topics, reports, and Atlas-like surfaces become selective or
secondary projections.

Do not claim dogfood, release readiness, external vector-service adoption, independent
human-reviewed gold labels, external-source execution, or approved
external-verification evidence. HEAD
contains a bounded SQLite FTS archive search, assistant vertical slice, grounded
answer contract, local external-verification requirement path,
confirmation-gated saved memory proposal flow, and deterministic Knowledge
Library topic-page renderer. PRM-14 adds deterministic project context decision
support for active project descriptors, archive citations, curated knowledge,
and weak/learning/no-match classification. PRM-15 corrects learning-state
semantics so legacy source presence maps only to indexed/surfaced and progress
requires explicit receipts. PRM-16 adds a bounded Weekly Brief V3 projection and
static renderer that localizes Radar failure to the Radar card while demoting
V1 Brief and Atlas to compatibility/internal surfaces. PRM-17 adds deterministic
workflow contracts and privacy-safe aggregate telemetry receipts for future
runtime activation. PRM-18 adds deterministic release/dogfood gate receipts;
the current post-PRM28 receipt is blocked only on dogfood-start approval and
does not start dogfood or claim release readiness. On 2026-07-29 the old live Telegram bot and Report V2 weekly timer
were stopped and disabled. A dedicated `prm-assistant` mode now exists and is
running for manual operator testing only: ordinary text and voice transcripts dispatch to
`/auto`, which chooses local research or local editor brief by default and can
choose LLM chat only when both `PRM_TELEGRAM_AUTO_LLM_ROUTER=1` and
`PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1` are explicitly enabled. Manual
`/research`, `/brief`, and separately gated `/chat` remain fallback commands.
Legacy callbacks are disabled, and
generation/write commands are blocked. It does not run automatic startup
migrations. The full product is not released. For immediate local use,
`memory ask` provides a no-LLM local evidence brief over bounded
archive/curated/project context.
LLM-backed `memory ask --llm-approved` and
`memory chat --allow-provider-egress` now exist behind the explicit
provider-egress switch; Telegram `/chat` remains a separate LLM-backed command,
requires `PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1`, and the currently running
Telegram runtime remains manual-test state, not dogfood.
The polished archive-plus-linked-source project-aware research assistant target
is specified in `docs/personal_research_memory_product_contract.md` and
scheduled in `docs/tasks.md`; PRM-22 and PRM-23 are implemented fixture-first
only. They must not be claimed as dogfood evidence, live external-source
execution, provider-egress approval, service start approval, durable
production-cache approval, production DB write approval, or vector/backend
approval.
Full product RAG is now formalized as PRM-24 through PRM-28 before dogfood:
gold eval set, citation-safe context pack, hybrid/vector ADR and privacy budget,
approved retrieval implementation, and product chat acceptance gate. ADR-004
approves only the PRM-27 local vector sidecar. It does not approve external
embeddings, hosted vector services, migrations, production writes, or dogfood
by itself. The subsequent operator instruction approved provider-egress flags
and manual `prm-assistant` runtime activation for testing, but not PRM-19
dogfood or release readiness.

## Active Profiles

- RAG: ON
- Tool-Use: ON
- Agentic: ON, bounded to the existing/planned read-only assistant tool loop
- Autonomous Workflow: required for ingestion, indexing, enrichment, and weekly routines
- Cost Architecture: ON
- Planning: OFF
- Compliance: OFF, with privacy/security controls still required

Runtime tier: T1.

Hermes reuse decision: official NousResearch Hermes Agent is pattern_only. It is
not a dependency and should not be introduced for T1 work.

## Delivery Model

- Bootstrap: Codex Direct.
- Ongoing delivery candidate: split_orchestrated.
- Orchestrator: main Codex session under human direction.
- Implementer: one scoped task at a time.
- Reviewer: optional read-only subagent when policy requires.
- Verifier: deterministic tests, evals, CI, Playbook validators.
- Completion authority: human.
- Child agents must not commit, push, self-review, or approve completion.
- Deep review is batched by implementation block. For the PRM LLM chat block,
  the PRM-18A through PRM-18C review is recorded before PRM-19. Do not spawn a
  separate deep-review subagent after every task unless the task touches a
  stop-ship boundary such as live provider egress, unsafe writes, vector backend
  adoption, production data migration, external skill approval, service start,
  dogfood start, release claim, or file deletion/archive.

## Verification Commands

Run these before claiming a planning or implementation handoff is clean:

- python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
- python3 tools/verify_project.py --root .
- git diff --check
- git diff --stat

Test tier helper:

- python3 tools/test_tiers.py --list
- python3 tools/test_tiers.py focused-prm
- python3 tools/test_tiers.py fast-contract
- python3 tools/test_tiers.py ops-date-sensitive

Do not run live Telegram ingestion, reaction sync, LLM extraction, Frontier,
Radar, report generation, full archive LLM backfill, external embeddings,
hosted vector services, or web research jobs from this handoff. PRM-27 local
vector sidecar indexing is authorized only inside ADR-004.

## Known Blockers

- Product pivot ADR remains proposed and needs human approval.
- PRM-24 candidate retrieval queries became a 50-row operator-approved
  generated seed gold set on 2026-08-11. Do not overclaim this as independent
  human review, dogfood, or release evidence.
- PRM-8 vector/hybrid retrieval remains historical/conditional outside the
  approved PRM-27 local sidecar scope.
- PRM-26 accepted the no-vector path and PRM-28 implemented the no-vector
  answer gate; PRM-27 local vector sidecar is implemented under ADR-004.
- Post-PRM28 local UX polish improved `memory research` default rendering,
  localization, current-fact boundaries, path redaction, and narrow repo-context
  cues. A follow-up Telegram UX polish adds ordinary-message auto routing,
  local-only `/brief` editor briefs, volatile per-chat mode-aware follow-up
  context, deterministic AI-transformation query hints, and a corrected
  archive-scope/current-price answer gate. Remaining UX gaps are deeper
  multi-turn product memory and curated-memory relevance/deduplication.
- PRM-18 release/dogfood gate is implemented. The current post-PRM28 receipt
  clears deterministic local stop-ship blockers and remains blocked on missing
  dogfood-start approval.
- PRM-18A through PRM-18C are implemented and the batched deep review is
  recorded at `docs/audit/PRM_DEEP_REVIEW_PRM18A_18C_2026-08-03.md`.
- PRM-19 dogfood cannot start until explicit human dogfood approval is
  recorded.
- PRM-20 cleanup/archive cannot start until PRM-19 dogfood evidence exists and
  compatibility archive/delete/move approval is explicit.
- PRM-21 records the future research-session assistant contract. PRM-22 and
  PRM-23 are implemented fixture-first only. Neither task can be treated as
  dogfood evidence or as approval for live web research, durable production
  cache writes, production DB writes, or external vector/backend adoption
  without explicit approval.
- PRM-24 through PRM-28 are the required full product RAG path before dogfood
  unless the human operator explicitly waives the RAG gate. PRM-27 is limited
  to ADR-004 local sidecar scope; do not expand to external embeddings, hosted
  vector services, migrations, or canonical DB writes without explicit
  approval.
- Legacy runtime is frozen: do not restart `telegram-bot.service` or
  `telegram-ai-split-report.timer` as PRM dogfood.
- Safe runtime is not dogfood yet: `systemd/telegram-prm-assistant.service` is
  currently installed, enabled, and running only for manual operator testing.
  Do not record PRM-19 dogfood evidence from this runtime without explicit
  dogfood-start approval.
- External skills are project-disabled until trust records are approved.
- Legacy report-centered docs remain as historical/compatibility surfaces and
  need a safe archive/migration pass in PBR-7 or PRM-20.
- Current full verifier is green after PRM-23 local fixture work:
  `python3 tools/verify_project.py --root .` passed on 2026-08-03 with
  `1083 passed, 291 subtests passed in 465.66s (0:07:45)`. The former
  date-window fixture drift in product ops and source-trust tests is corrected
  with relative fixture timestamps.

## Canonical Docs

- docs/PROJECT_BRIEF.md
- docs/ARCHITECTURE.md
- docs/IMPLEMENTATION_CONTRACT.md
- docs/adr/ADR-001-product-pivot-to-personal-research-memory.md
- docs/personal_research_memory_product_contract.md
- docs/personal_research_memory_architecture.md
- docs/personal_research_memory_roadmap.md
- docs/final_acceptance_plan.md
- docs/tasks.md
- docs/playbook_retrofit_audit.md
- docs/product_pivot_current_state_audit.md
- docs/RAG_DATA_READINESS.md
- docs/retrieval_eval.md
- docs/generation_eval.md
- docs/tool_eval.md
- docs/agent_eval.md
- docs/AGENT_HARNESS_DESIGN.md
- docs/COST_BUDGET.md
- docs/PRIVACY_THREAT_MODEL.md
- docs/ROLLBACK_AND_REINDEX_PLAN.md
