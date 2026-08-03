# Codex Session Handoff

Status: active
Last updated: 2026-08-03

## Repository State

- Target repository commit inspected before retrofit: ad8689fa25b89f77122c4cec7c7a6b9da3f500cf
- Target branch: master
- AI Workflow Playbook commit used: 5583eca96c4d2d480b5574ed78bea63e0b07ebf0
- Adoption mode: Standard
- Current phase: PRM-18 release/dogfood gate is implemented and blocks dogfood
  start while final acceptance evidence and human approval are missing; legacy
  live runtime is frozen; safe `prm-assistant` runtime is implemented but not
  installed, enabled, started, or dogfood evidence; PRM-18A through PRM-18C are
  implemented and their batched deep review is recorded.
- Implemented slices in HEAD: PRM-1 through PRM-7 plus PRM-9 through PRM-18C
- Proposed next slices: none inside the allowed PRM-18B..PRM-18C block
- Blocked/not implemented slices: PRM-8, PRM-19, and PRM-20
- Next safe work: stop before PRM-19. PRM-19 only after explicit human
  dogfood-start approval exists and PRM-18 blockers are accepted or cleared;
  PRM-20 only after real dogfood evidence and explicit compatibility
  archive/delete/move approval.

## Product Direction

The product pivot is proposed, not accepted:

Personal Telegram Research Memory + Grounded Assistant replaces the weekly
report as the product center. Full archive search is the primary planned value.
Knowledge Atoms, topics, reports, and Atlas-like surfaces become selective or
secondary projections.

Do not claim dogfood, release readiness, vector adoption, gold-query approval,
external-source execution, or approved external-verification evidence. HEAD
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
runtime activation. PRM-18 adds a deterministic release/dogfood gate receipt;
the current receipt is blocked and does not start dogfood or claim release
readiness. On 2026-07-29 the old live Telegram bot and Report V2 weekly timer
were stopped and disabled. A dedicated `prm-assistant` mode now exists for the
future operator entrypoint: ordinary text and voice transcript dispatch to
`/chat`, legacy callbacks are disabled, and generation/write commands are
blocked. It does not run automatic startup migrations. The full product is not
released. For immediate local use, `memory ask` provides a no-LLM local
evidence brief over bounded archive/curated/project context. LLM-backed
`memory ask --llm-approved` and `memory chat --allow-provider-egress` now exist
behind the explicit provider-egress switch; Telegram chat uses the same display
contract, while runtime start remains blocked.

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
Radar, report generation, full archive indexing, embeddings, or web research
jobs from this handoff.

## Known Blockers

- Product pivot ADR remains proposed and needs human approval.
- Candidate retrieval queries are not gold evidence until the operator approves
  labels and expected citations.
- PRM-8 vector/hybrid retrieval remains blocked.
- PRM-18 release/dogfood gate is implemented and currently blocked.
- PRM-18A through PRM-18C are implemented and the batched deep review is
  recorded at `docs/audit/PRM_DEEP_REVIEW_PRM18A_18C_2026-08-03.md`.
- PRM-19 dogfood cannot start until explicit human dogfood approval is recorded,
  and PRM-18 blockers are accepted or cleared.
- PRM-20 cleanup/archive cannot start until PRM-19 dogfood evidence exists and
  compatibility archive/delete/move approval is explicit.
- Legacy runtime is frozen: do not restart `telegram-bot.service` or
  `telegram-ai-split-report.timer` as PRM dogfood.
- Safe runtime is not dogfood yet: do not start `src/main.py prm-assistant` or
  `systemd/telegram-prm-assistant.service` without explicit dogfood-start
  approval and accepted or cleared PRM-18 blockers.
- External skills are project-disabled until trust records are approved.
- Legacy report-centered docs remain as historical/compatibility surfaces and
  need a safe archive/migration pass in PBR-7 or PRM-20.
- The configured full pytest baseline currently has one known failure:
  tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist.
  The fixture seeds 2026-07-08 live evidence and now falls outside the 14-day
  validation window. The PRM-18 verifier on 2026-07-29 recorded:
  `1 failed, 1049 passed, 287 subtests passed in 412.02s (0:06:52)`.

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
