# CODEX_PROMPT — Session Handoff
_v3.0 · 2026-04-07 · telegram-research-agent_

---

## Current State

- Planning reset complete
- Active architecture concern: fragmented memory/state surfaces
- Repository status verified from code, not legacy roadmap prose
- `pytest` is not available in the current shell environment (`pytest: command not found`)
- Orchestrator-to-Codex execution path: `codex exec -s workspace-write`

---

## What Exists

- Telegram ingestion, normalization, scoring, and topic assignment
- project relevance, personalization, and weekly report generation
- explicit feedback and tagging
- derived `channel_memory`
- derived `project_context_snapshots`
- implementation-idea triage and rejection memory

---

## Architectural Verdict

The repo already has persistence, but it lacks one coherent memory contract.

Next work is **memory unification**, specifically:

- a curated verbatim evidence layer for high-value signals
- a decision journal spanning acted-on / ignored / deferred / rejected outcomes
- scope-first retrieval helpers shared by weekly generators

Do not build a generic memory framework.

Reference documents:

- `docs/memory_architecture.md`
- `docs/tasks.md`
- `docs/architecture.md`

---

## Exact Next Execution Step

Implement **Phase 1 — Memory Contract And Inventory** from `docs/tasks.md`.

Immediate tasks:

1. M3 — finalize schema for `signal_evidence_items`, `decision_journal`, and the evolved project snapshot surface
2. M4 — write migration mapping from current tables into the new architecture
3. M5 — define retrieval debug/eval requirements

Do not start prompt rewrites or broad output changes before those contracts are explicit.
