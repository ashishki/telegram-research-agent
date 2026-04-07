# Workflow Quick Reference

---

## Entry Point

Use [workflow_orchestrator.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/prompts/workflow_orchestrator.md) as the master loop prompt.

The orchestrator reads the roadmap from [docs/tasks.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/tasks.md) and advances phase by phase.

---

## Phase Order

| Order | Phase |
|---|---|
| 1 | Memory Contract And Inventory |
| 2 | MVP Memory Unification |
| 3 | Wire Memory Into Weekly Outputs |
| 4 | Observability And Evaluation |

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
- canonical vs derived state ownership is unclear
- retrieval behavior has no inspectable debug surface
- prompt work appears before storage contracts are defined
- memory work turns into a generic platform effort

---

## Review Focus by Phase

| Phase | Mandatory review focus |
|---|---|
| Memory Contract And Inventory | schema clarity, migration clarity, retrieval contract clarity |
| MVP Memory Unification | provenance completeness, decision continuity, scope-first retrieval |
| Wire Memory Into Weekly Outputs | output integration, suppression continuity, prompt-context discipline |
| Observability And Evaluation | eval usefulness, debug surfaces, operator inspectability |

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
- memory schema and retrieval contract work
- migration mapping
- debug/eval contract definition

Codex should not yet implement:
- global memory frameworks
- decorative abstractions
- graph systems
- broad semantic search over everything
