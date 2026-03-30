# Workflow Quick Reference

---

## Entry Point

Use [workflow_orchestrator.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/prompts/workflow_orchestrator.md) as the master loop prompt.

The orchestrator reads the roadmap from [docs/tasks.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/tasks.md) and advances phase by phase.

---

## Phase Order

| Order | Phase |
|---|---|
| 1 | Baseline Stabilization |
| 2 | Scoring Foundation |
| 3 | Model Routing |
| 4 | Signal-First Output |
| 5 | Project Relevance Upgrade |
| 6 | Personalization / Taste Model |
| 7 | Learning Layer Refinement |
| 8 | Productization / Surface Layer |

---

## What the Orchestrator Must Enforce

- dependencies before implementation
- one bounded phase packet at a time
- explicit non-goals
- required documentation updates
- quality gates before phase completion

---

## Hard Stops

Stop the loop when:
- the current phase has no measurable success criteria
- dependencies are unmet
- docs and implementation disagree
- routing work has no cost metrics
- personalization appears before project relevance is validated
- product surface work starts before signal-first output is stable

---

## Review Focus by Phase

| Phase | Mandatory review focus |
|---|---|
| Baseline Stabilization | docs/runtime alignment, baseline metrics, frozen contracts |
| Scoring Foundation | bucket quality, stability, evidence fields |
| Model Routing | `CHEAP / MID / STRONG` policy, escalation rate, cost awareness |
| Signal-First Output | section completeness, readability, ignored/noise visibility |
| Project Relevance Upgrade | relevance precision, rationale quality, separation from general importance |
| Personalization | explainability, bounded influence, no evidence override |
| Learning Layer | durable knowledge-gap mapping, non-generic recommendations |
| Productization | operator clarity, surface stability, observability access |

---

## Task Decomposition Rule

Always split work as:
- epic
- sub-epic
- task unit

If a task unit spans multiple roadmap phases, it is too large.

---

## Current Implementation Guidance

Codex should start with:
- baseline stabilization
- measurement capture
- contract cleanup

Codex should not yet implement:
- deep personalization
- advanced feedback loops
- broad product-surface expansion
