# Telegram Research Agent — Development Cycle

**Version:** 2.0.0
**Date:** 2026-03-30
**Status:** Strategic redesign aligned

---

## Overview

Development now follows a phase-gated workflow aligned to the redesigned product:

```text
Strategist -> Orchestrator -> Codex -> Review -> Fixes
```

The purpose of the workflow is not just to ship code.
It is to enforce sequencing, prevent premature complexity, and keep docs, implementation, and evaluation in sync.

---

## Roles

### 1. Strategist

Owns:
- phase design
- architecture deltas
- success criteria
- non-goals
- documentation updates

Produces per phase:
- scope definition
- dependencies
- quality gates
- stop conditions
- required document changes

Must not:
- mix multiple future phases into one implementation packet

---

### 2. Orchestrator

Owns:
- current-phase selection from `docs/tasks.md`
- dependency checks
- packaging work for Codex
- packaging review context for reviewer
- stop/go decision after review

Produces:
- one implementation packet at a time
- one review packet at a time
- updated phase state after review outcome

Must stop when:
- prerequisites are not met
- baseline metrics are missing
- review fails on phase contract items
- docs and implementation drift

---

### 3. Codex

Owns:
- code and config changes for the active phase only
- tests and implementation-level verification
- task-level documentation touch-ups explicitly requested by strategist/orchestrator

Must receive:
- bounded scope
- explicit acceptance criteria
- clear file ownership

Must not:
- jump ahead to future phases
- merge routing, output, and personalization into one change set

---

### 4. Reviewer

Owns:
- contract verification
- architectural drift detection
- output/routing/personalization guardrail checks
- regression detection against prior phase criteria

Review focus:
- correctness
- clarity of boundaries
- measurable success

Not responsible for:
- writing fixes
- speculative redesign during review

---

### 5. Fixes

Owns:
- address only review findings
- re-verify changed surfaces
- keep scope narrow

Must not:
- broaden implementation beyond review deltas unless explicitly re-scoped

---

## Phase Execution Rules

### Before a phase starts

- confirm all dependencies in `docs/tasks.md`
- confirm phase entry metrics exist
- confirm architecture and prompt contracts are current
- confirm scope excludes future-phase work

### During implementation

- work by epic, then sub-epic, then task unit
- keep task units reviewable in isolation
- attach metrics/eval changes to behavior changes

### Before review

- verify implementation matches the current phase only
- verify required docs are updated
- verify quality-gate evidence exists

### Before moving to next phase

- review must pass
- phase success criteria must be met
- stop conditions must be clear for the next phase

---

## Review Checklist Requirements

Every phase review must cover:
- architecture adherence
- scope adherence
- quality-gate evidence
- observability coverage
- cost awareness where models are involved
- prompt/output contract alignment

Additional mandatory checks by phase type:
- scoring work: bucket quality and reproducibility
- routing work: tier distribution, escalation rate, budget control
- output work: section completeness, readability, ignored/noise handling
- personalization work: explainability, bounded influence, no evidence override

---

## Stop Conditions

Do not advance when any of the following holds:
- no baseline metrics
- no measurable quality gate for the phase
- docs describe behavior that code does not implement
- expensive model usage is introduced without routing measurement
- personalization is added before relevance precision is acceptable
- product surface work starts before signal-first output is stable

---

## Task Sizing Rules

- `Epic`: a phase-level capability such as routing or personalization
- `Sub-epic`: one coherent slice inside the epic
- `Task unit`: a bounded change that can be reviewed quickly

Good task unit:
- one clear purpose
- narrow file set
- explicit acceptance criteria

Bad task unit:
- spans multiple phases
- bundles architecture, implementation, and polish together
- cannot be tested or reviewed independently

---

## Living Document Rules

The following must stay aligned:
- `README.md`
- `docs/spec.md`
- `docs/architecture.md`
- `docs/tasks.md`
- `docs/prompts/`
- review and evaluation docs

Rules:
- update existing docs instead of creating forks
- remove obsolete framing instead of leaving dual truths
- treat prompt templates as behavior contracts

---

## Definition of Ready

A phase is ready for implementation when:
- dependencies are complete
- non-goals are explicit
- quality gates are defined
- required docs are identified
- the task packet is small enough for isolated review

---

## Definition of Done

A phase is done when:
- implementation passes review
- quality gates are satisfied
- required docs are aligned
- no blocked assumptions remain hidden
- the next phase can start without reinterpretation
