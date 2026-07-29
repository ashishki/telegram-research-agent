# Codex Session Handoff

Status: active
Last updated: 2026-07-29

## Repository State

- Target repository commit inspected before retrofit: ad8689fa25b89f77122c4cec7c7a6b9da3f500cf
- Target branch: master
- AI Workflow Playbook commit used: 5583eca96c4d2d480b5574ed78bea63e0b07ebf0
- Adoption mode: Standard
- Current phase: PRM-13 through PRM-17 implementation block
- Implemented slices in HEAD: PRM-1 through PRM-7 plus PRM-9 through PRM-15
- Blocked/not implemented slices: PRM-8 and PRM-16 through PRM-20
- Next safe work: PRM-16 only if the human operator wants to proceed within the
  open PRM-13 through PRM-17 block. The next batched deep-review gate is before
  PRM-18 unless a stop-ship boundary requires immediate review earlier.

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
requires explicit receipts. The full product is not released.

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
- Deep review is batched by implementation block. Do not spawn a separate
  deep-review subagent after every task unless the task touches a stop-ship
  boundary such as privacy egress, unsafe writes, vector backend adoption,
  production data migration, external skill approval, dogfood start, or file
  deletion/archive.

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
- PRM-16 through PRM-20, Brief V3, dogfood, and release readiness are planned,
  not implemented.
- External skills are project-disabled until trust records are approved.
- Legacy report-centered docs remain as historical/compatibility surfaces and
  need a safe archive/migration pass in PBR-7 or PRM-20.
- The configured full pytest baseline currently has one known failure:
  tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist.
  The fixture seeds 2026-07-08 live evidence and now falls outside the 14-day
  validation window on 2026-07-26.

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
