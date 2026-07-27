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

## PRM-6 Selective Enrichment Enforcement

Implemented contract: `selective_enrichment_batch.v1`.

PRM-6 adds deterministic queue and budget enforcement only. It does not approve
or run live LLM extraction, full archive backfill, embeddings, or report
generation.

Priority order:

1. reactions;
2. repeated search returns;
3. cited assistant answers;
4. watch topics;
5. active projects;
6. repeated signals;
7. manual saves.

Default hard caps:

| Control | Value |
| --- | ---: |
| Max cost per selective enrichment batch | $5.00 |
| Max model calls per batch | 100 |
| Max retries per post | 1 |
| Default estimated cost per attempt | $0.05 |

The batch runner checks the next attempt before calling the injected extractor.
If the next attempt would exceed cost or model-call caps, the batch stops with
`stopped_budget` and records `cost_cap_exceeded` or
`model_call_cap_exceeded`. Extraction failure records `extractor_failed` while
preserving archive search availability. Receipts exclude raw post text, source
URLs, and provider payloads.

Verification:

```text
python3 -m pytest tests/test_selective_enrichment.py tests/test_reaction_fast_lane.py tests/test_archive_search.py tests/test_archive_documents.py -q
21 passed in 0.24s
python3 -m pytest tests/test_selective_enrichment.py tests/test_knowledge_extraction.py tests/test_reaction_fast_lane.py tests/test_archive_search.py tests/test_archive_documents.py -q
28 passed in 4.75s
python3 -m pytest tests/ -q
1 failed, 989 passed, 281 subtests passed in 280.26s
FAILED tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
```

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

## PRM-10 Answer Telemetry Enforcement

Implemented contract: `pi_answer_telemetry.v1`.

Each assistant answer separates:

- planning latency, model calls, estimated cost, and cost source;
- retrieval latency, tool calls, and estimated cost;
- generation latency, model calls, estimated cost, and cost source.

Telemetry excludes raw post text, raw tool payloads, and provider payloads. In
the PRM-10 fixture path, estimated costs remain `0.0` with
`cost_source=fake_or_unmetered_no_receipt` because no live provider call is
made. The live `LLMClient` path uses completion receipts for generation cost.
Bounded Telegram snippet provider context is recorded separately from broad raw
corpus egress. PI chat suppresses `llm_usage` database writes during read-only
planning/generation; response telemetry remains the cost receipt for these
turns.

Verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_pi_tools.py tests/test_pi_chat.py -q
39 passed, 6 subtests passed in 14.25s
```
