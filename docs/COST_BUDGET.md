# Cost Budget

Status: draft budget requiring human approval before implementation

## Principles

- FTS retrieval costs zero model calls.
- Search and filters run before generation.
- Selective enrichment is priority-based and bounded.
- No full archive LLM backfill.
- Stronger models require task-specific justification.

## Initial Task Budgets

| Workload | Max cost | Max model calls | Approval trigger |
| --- | ---: | ---: | --- |
| PRM-1 data inventory | $0 | 0 | any model call |
| PRM-3 FTS baseline | $0 | 0 | any model call |
| PRM-4 assistant search slice | $3/run | 20 | stronger model, retries > 2 |
| PRM-6 selective enrichment batch | $5/batch | 100 | larger batch or full-archive expansion |
| PRM-7 retrieval eval | $2/run | 20 | LLM judge or embeddings |
| PRM-10 answer generation eval | $5/run | 50 | judge becomes blocking |

Monthly planning ceiling before dogfood: $25 unless the human approves more.

## Required Telemetry

- model;
- workload class;
- task ID;
- input/output token estimate where available;
- tool calls;
- retries;
- cache hit;
- cost estimate;
- human approval reference for overrun.
