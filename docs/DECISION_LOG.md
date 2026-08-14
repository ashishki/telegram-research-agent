# Decision Log

## D-PRM-MAT-2026-08-13 — Plan an integrated maturity queue without claiming completion

Decision: preserve PRM-UX historical implementation evidence and create proposed PRM-MAT successor tasks for the missing shared request lifecycle, durability, receipts, freshness, verification, evaluation and operations. Rationale: repository inspection found several deterministic components that are not one reader-facing or durable live path. Consequence: no configuration, database, service, provider, fetch, dogfood, release or compatibility-cleanup authority is granted.

Status: active
Last updated: 2026-07-26

| ID | Date | Decision | Status | Evidence |
| --- | --- | --- | --- | --- |
| D-001 | 2026-07-26 | Pivot from weekly-report-centered product to Personal Telegram Research Memory + Grounded Assistant. | proposed | docs/adr/ADR-001-product-pivot-to-personal-research-memory.md |
| D-002 | 2026-07-26 | Use AI Workflow Playbook commit 5583eca96c4d2d480b5574ed78bea63e0b07ebf0 as retrofit baseline. | proposed | docs/playbook_retrofit_audit.md |
| D-003 | 2026-07-26 | Adopt Standard mode with RAG, Tool-Use, Agentic, Autonomous Workflow, and Cost Architecture active; Planning and Compliance profiles off. | proposed | docs/PROJECT_BRIEF.md; docs/ARCHITECTURE.md |
| D-004 | 2026-07-26 | Select runtime tier T1 and classify official NousResearch Hermes Agent as pattern_only, not a dependency. | proposed | docs/ARCHITECTURE.md |
| D-005 | 2026-07-26 | Treat Knowledge Atoms and topics as selective enrichment, never a gate for archive search visibility. | proposed | docs/personal_research_memory_product_contract.md |
| D-006 | 2026-07-26 | Use persistent full-archive SQLite FTS as the first retrieval baseline before any vector backend decision. | proposed | docs/retrieval_eval.md; docs/RAG_DATA_READINESS.md |
| D-007 | 2026-07-26 | External skills are project-disabled until Playbook trust records are created and approved. | proposed | docs/playbook_retrofit_audit.md |

## Rules

- Proposed decisions are not accepted until the human operator approves them.
- Superseded decisions remain visible and cite the ADR or contract that changed
  them.
- Implementation tasks may rely on proposed decisions only when the task itself
  is documentation or evaluation preparation. Product implementation requires
  the relevant human gates in docs/tasks.md.
