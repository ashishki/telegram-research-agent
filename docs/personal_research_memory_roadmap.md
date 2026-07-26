# Personal Research Memory Roadmap

Status: active roadmap summary

Detailed task graph: `docs/tasks.md`

## Milestones

### M0 - Playbook Retrofit

Tasks: PBR-0 through PBR-8.

Outcome: current-state audit, product pivot ADR, Standard Playbook contracts,
eval/cost/privacy/ops docs, compact task graph, validators.

### M1 - Searchable Archive Baseline

Tasks: PRM-0 through PRM-4.

Outcome: corpus inventory, document identity contract, persistent full-archive
FTS baseline, and first assistant archive-search vertical slice.

First user-value milestone: PRM-3.

First directly testable interaction: PRM-4.

### M2 - Personalization And Selective Enrichment

Tasks: PRM-5 through PRM-6.

Outcome: reactions become searchable immediately; enrichment is queued and
receipt-backed; priority posts produce cases, claims, tools, practices,
warnings, entities, and topic candidates.

### M3 - Retrieval Evaluation And Hybrid Decision

Tasks: PRM-7 through conditional PRM-8.

Outcome: FTS baseline measured against human-approved gold queries; vector or
hybrid backend chosen only if evidence justifies it.

### M4 - Grounded Assistant Product

Tasks: PRM-9 through PRM-12.

Outcome: one entrypoint, bounded tool catalog, grounded answer synthesis,
external verification path, and confirmation-gated save/watch/project flows.

### M5 - Library, Projects, Learning, And Brief

Tasks: PRM-13 through PRM-17.

Outcome: query-driven Knowledge Library, project decision support, corrected
learning states, Weekly Brief V3, autonomous workflow receipts, observability,
cost telemetry, and rollback.

### M6 - Acceptance And Dogfood

Tasks: PRM-18 through PRM-20.

Outcome: end-to-end eval/security review, four-week operator dogfood, and
usage-based cleanup/archive decisions.

## Anti-Complexity Rules

- No vector store before PRM-7.
- No broad refactor before PRM-4.
- No full archive LLM backfill.
- No new generic agent framework.
- No global graph product.
- No public SaaS/multi-user architecture.
- No fake eval evidence.
