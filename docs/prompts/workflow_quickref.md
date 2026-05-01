# Workflow Quick Reference

---

## Entry Point

Use [workflow_orchestrator.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/prompts/workflow_orchestrator.md) as the master loop prompt.

The orchestrator reads the maintenance backlog from [docs/tasks.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/tasks.md) and advances one bounded packet at a time.

---

## Current Backlog Lanes

| Lane | Focus |
|---|---|
| Feedback | reaction sync, inline buttons, decision history |
| Quality | digest health, signal quality, evaluation fixtures |
| Cost | baseline tracking, LLM routing, tenant/project cost visibility |
| Docs | README, active docs, archive hygiene |

---

## What the Orchestrator Must Enforce

- dependencies before implementation
- one bounded packet at a time
- explicit non-goals
- required documentation updates
- quality gates before completion

---

## Hard Stops

Stop the loop when:
- the current work item has no measurable success criteria
- dependencies are unmet
- docs and implementation disagree
- canonical vs derived state ownership is unclear
- retrieval behavior has no inspectable debug surface
- prompt work appears before storage or feedback contracts are defined
- memory or feedback work turns into a generic platform effort

---

## Review Focus by Change Type

| Change type | Mandatory review focus |
|---|---|
| Schema / storage | migration clarity, provenance, rollback safety |
| Retrieval / memory | scope-first retrieval, inspectability, prompt-context discipline |
| Bot / delivery | owner gating, idempotency, safe callback handling |
| Reports / prompts | output contract, fixtures, no invented evidence |
| Ops / cost | observability, budget visibility, failure mode clarity |

---

## Task Decomposition Rule

Every task unit must be reviewable in isolation. If it spans unrelated backlog
lanes, it is too large.

---

## Current Implementation Guidance

Codex should start with:
- the highest-priority open item in `docs/tasks.md`
- the smallest implementation packet that satisfies its success criteria
- docs updates that directly match the code change

Codex should not yet implement:
- global memory frameworks
- decorative abstractions
- graph systems
- broad semantic search over everything
- unrelated product surface redesigns
