# Telegram Research Agent — Development Cycle

**Version:** 3.0
**Date:** 2026-04-07
**Status:** Memory-unification workflow active

---

## Overview

Development follows a bounded AI-assisted loop:

```text
Strategist -> Orchestrator -> Codex -> Review -> Fixes
```

The active program is the memory-unification roadmap in `docs/tasks.md`, not the older roadmap generations.

The workflow exists to enforce:

- dependency order
- bounded implementation packets
- explicit architecture contracts
- reviewable phases
- documentation alignment before code drift accumulates

---

## Active Execution Model

Current phase order:

1. Phase 1 — Memory Contract And Inventory
2. Phase 2 — MVP Memory Unification
3. Phase 3 — Wire Memory Into Weekly Outputs
4. Phase 4 — Observability And Evaluation

Reference documents:

- `docs/tasks.md`
- `docs/memory_architecture.md`
- `docs/architecture.md`
- `docs/IMPLEMENTATION_CONTRACT.md`

---

## Roles

### Strategist

Owns:

- phase design
- architecture deltas
- sequencing
- non-goals
- documentation updates

Must produce:

- exact phase scope
- dependencies
- success criteria
- stop conditions
- required docs to update

### Orchestrator

Owns:

- current phase selection from `docs/tasks.md`
- dependency checks
- bounded implementation packet for Codex
- bounded review packet for the reviewer
- stop/go decision after review

Must not:

- hand Codex a multi-phase packet
- use legacy roadmap phases as the active execution source

Execution path:

- implementation packets are handed to Codex via `codex exec -s workspace-write`
- fix packets are also handed to Codex via `codex exec -s workspace-write`

### Codex

Owns:

- implementation for the active bounded packet only
- tests and local validation for that packet
- small doc touchups explicitly required by the packet

Must not:

- redesign roadmap during implementation
- broaden memory scope into a generic memory system

Invocation contract:

- Codex is invoked by the orchestrator with `codex exec -s workspace-write`
- `workspace-write` is the default implementation sandbox unless a task explicitly requires another mode

### Reviewer

Owns:

- architecture adherence
- scope adherence
- quality gate verification
- regression risk detection

Must focus on:

- correctness
- contract violations
- hidden scope expansion

### Fixes

Owns:

- only reviewer findings
- revalidation of changed surfaces

Must not:

- silently widen scope

---

## Phase Rules

### Before implementation

- read `docs/tasks.md`
- read `docs/memory_architecture.md`
- confirm dependencies are complete
- confirm the phase has explicit success criteria
- confirm canonical vs derived state boundaries are understood

### During implementation

- keep changes reviewable in isolation
- keep schema work separate from prompt rewrites where possible
- add retrieval/debug tests alongside retrieval behavior

### Before review

- verify docs and code still match
- verify non-goals were respected
- verify the packet did not leak into a later phase

### Before advancing

- review must pass
- phase success criteria must be evidenced
- next phase must be startable without reinterpretation

---

## Mandatory Review Checks

Every phase review must cover:

- architecture adherence
- scope adherence
- documentation alignment
- validation evidence
- observability impact

Phase-specific additions:

- Phase 1: schema clarity, migration clarity, retrieval contract clarity
- Phase 2: provenance completeness, decision continuity correctness, retrieval scoping correctness
- Phase 3: weekly output integration correctness, suppression continuity, prompt-context discipline
- Phase 4: eval usefulness, debug surfaces, operator inspectability

---

## Stop Conditions

Stop and do not advance when:

- dependencies are missing
- the packet spans multiple phases
- canonical vs derived ownership is unclear
- retrieval behavior cannot be inspected
- prompt work is being used to hide missing storage contracts
- a generic memory abstraction is being introduced without a concrete need

---

## Living Docs

These documents define the active AI-development workflow and must stay aligned:

- `README.md`
- `docs/tasks.md`
- `docs/memory_architecture.md`
- `docs/architecture.md`
- `docs/IMPLEMENTATION_CONTRACT.md`
- `docs/CODEX_PROMPT.md`
- `docs/prompts/workflow_orchestrator.md`
- `docs/prompts/workflow_codex_implementer.md`
- `docs/prompts/workflow_claude_reviewer.md`
- `docs/prompts/workflow_codex_fixer.md`
