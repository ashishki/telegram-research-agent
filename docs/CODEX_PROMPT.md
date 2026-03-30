# CODEX_PROMPT — Session Handoff
_v2.0 · 2026-03-30 · telegram-research-agent_

---

## Current State

- `Execution model`: Strategic Roadmap v2
- `Current phase`: Phase 1 — Baseline Stabilization
- `Phase status`: ready for bounded implementation packet
- `Baseline`: repository state is stable enough to begin Phase 1, but CI/CD issue must be treated as a baseline blocker
- `Last known test baseline`: 37 passing tests (legacy context, 2026-03-30)
- `Ruff`: not enforced

## Next Task

Build a bounded `Phase 1 — Baseline Stabilization` implementation packet.

The first packet should cover only:
- baseline/runtime drift capture
- documentation/runtime reconciliation where needed
- baseline metrics capture
- CI/CD blocker handling as a Phase 1 baseline issue

It must not include:
- Phase 2 scoring redesign
- Phase 3 routing implementation
- signal-first output redesign in production
- personalization logic

## Fix Queue

- none formalized under Roadmap v2 yet

## Open Context

- Legacy phases and audit artifacts remain in the repo as historical context
- Any references to `Phase 19`, `Phase 20`, `T29-T34`, or similar should be treated as legacy history, not as the current execution queue
- Current orchestration must derive scope from `docs/tasks.md` Roadmap v2, not from legacy phase numbering

## Legacy History Note

Legacy delivery work completed before Roadmap v2 includes:
- ingestion and normalization pipeline
- topic detection and digest generation
- project insights and recommendations
- scoring and initial routing-related work
- reporting/rendering experiments including HTML/PDF

These are implementation history, not the current phase plan.

## Instructions for Codex / Orchestrator

- Read `docs/tasks.md` first
- Treat `Strategic Roadmap v2` as authoritative for new execution
- Use legacy artifacts only as implementation context
- Do not start Phase 2+ work until Phase 1 entry and exit conditions are satisfied
- Return bounded packets and explicit stop conditions rather than broad “continue implementation” guidance
