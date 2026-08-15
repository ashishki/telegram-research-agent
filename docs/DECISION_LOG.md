# Decision Log

## D-PRM-QA-2026-08-15 — Select FTS/query-rewrite retrieval and demote always-on hash-vector fusion

Decision: default PRM runtime retrieval uses SQLite FTS with deterministic OR
fallback, bounded generic query rewrites, and local hash-vector search only when
FTS misses. Always-on hash-vector fusion, OpenAI API dense hybrid retrieval, and
the candidate-pool reranker remain eval adapters. API dense retrieval is not
adopted as the default.

Rationale: PRM-QA all-case and holdout ablations showed no recall/nDCG gain from
always-on hash-vector fusion, while MRR and p95 latency regressed materially.
After the operator approved API embeddings on 2026-08-15, OpenAI
`text-embedding-3-large` was measured over a gitignored SQLite sidecar. It
preserved Recall@10 but regressed holdout MRR/nDCG versus R1 and increased p95
latency/provider cost, so it remains non-default.

Evidence:

- `evals/prm_qa/prm_qa_eval_report.v1.json`
- `evals/prm_qa/prm_qa_holdout_report.v1.json`
- `evals/prm_qa/prm_qa_api_dense_report.v1.json`
- `evals/prm_qa/prm_qa_api_dense_holdout_report.v1.json`
- `docs/adr/ADR-005-prm-qa-selected-retrieval-policy.md`

Boundary: this decision approves only the bounded API embedding evaluation and
local gitignored API sidecar. It does not approve hosted vector services, live
web research, production migrations, PRM-19 dogfood, or release claims.

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
