# Cost Budget

Status: active PRM budget requiring human approval before live provider use

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
| PRM-18A LLM chat UX contract | $0 | 0 | any provider call |
| PRM-18B LLM-backed memory chat CLI implementation | $0 for implementation/tests | 0 for implementation/tests | real provider call with private snippets |
| PRM-18C Telegram PRM assistant UX parity | $0 for implementation/tests | 0 for implementation/tests | starting service or real provider call |
| PRM-22 linked-source resolver implementation | $0 for implementation/tests | 0 for implementation/tests | live HTTP fetch, external skill, provider summarization, or durable production cache write |
| PRM-23 memory research planner implementation | $0 for implementation/tests | 0 for implementation/tests | live linked-source fetch, provider synthesis, service start, dogfood start, production write, or vector/backend adoption |
| PRM-24 generated seed gold labels and FTS baseline | $0 | 0 | raw Telegram text copied into eval rows, provider judge, embeddings, vector backend, live research, or production write |
| PRM-26 no-vector ADR acceptance | $0 | 0 | any embedding run, vector backend adoption, production index write, migration, provider egress, or accepted backend budget |
| PRM-28 no-vector answer gate | $0 for implementation/tests | 0 for implementation/tests | provider synthesis, live fetch, embeddings/vector backend, service start, production write, or dogfood start |
| PRM-27 local vector sidecar | $0 provider cost; local CPU/disk only | 0 | external embeddings, hosted vector service, provider synthesis, service start, production DB write, or migration |

Monthly planning ceiling before dogfood: $25 unless the human approves more.

## PRM-18A..PRM-18C LLM Chat UX Budget

The next ChatGPT-like UX block must be implemented with fake LLM clients and
fixture databases by default. Real provider calls with private Telegram
snippets are allowed only after explicit human approval for bounded snippet
provider egress.

Budget controls before approval:

| Control | Value |
| --- | ---: |
| Implementation/test model calls | 0 |
| Implementation/test provider cost | $0 |
| External skill calls | 0 |
| Runtime/service starts | 0 |
| Approval trigger | any real provider call, external skill call, or service start |

The user-visible chat response must include an explicit privacy/cost line with
model call count, estimated cost, and whether bounded Telegram snippets were
sent to the provider.

PRM-18A contracts this line for every local or LLM-backed chat answer:

```text
Privacy: mode=<local-only|llm-approved>; model_calls=<n>; estimated_cost_usd=<usd>; bounded_telegram_snippet_provider_egress=<true|false>; raw_telegram_corpus_egress=false; durable_writes=false
```

Required budget behavior:

- current `memory ask` answers show `model_calls=0`, `estimated_cost_usd=0`,
  and no provider egress;
- PRM-18B/PRM-18C implementation and tests use fake clients and fixture
  databases, so implementation cost remains `$0`;
- a real provider call with private snippets requires explicit human approval
  for that run and the `--allow-provider-egress`-style switch;
- approved runtime calls must derive `estimated_cost_usd` from provider usage
  receipts or a documented local estimator when the provider does not return
  cost directly;
- hidden retry fan-out is not allowed before dogfood approval.

## PRM-17 Runtime Workflow Budget

Implemented telemetry schema: `workflow_telemetry_receipt.v1`.

Runtime workflow activation is still not approved. PRM-17 only defines the
contract and sanitizer used by future scheduled ingestion, indexing, enrichment,
projection, backup, dry-run reindex, and rollback routines.

Default workflow ceiling before dogfood approval:

| Control | Value |
| --- | ---: |
| Max weekly workflow cost | $10.00 |
| Max weekly workflow model calls | 500 |
| Max retries per job | 1 |
| Approval trigger | weekly cost or model calls exceed the ceiling |

Required aggregate telemetry:

- index freshness seconds;
- queue age seconds;
- retrieval latency milliseconds;
- generation latency milliseconds;
- model cost USD;
- model calls;
- tool calls;
- no-answer count and rate;
- error class.

The telemetry receipt excludes raw post text, provider payloads, prompts,
completions, and raw Telegram corpus egress. If a caller passes raw fields to the
fixture builder, only the redacted field names appear in the receipt.

Verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_workflow_telemetry.py -q
4 passed in 0.08s
```

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

## PRM-21..PRM-23 Research Session Assistant Budget

The project-aware research-session assistant is specified as a future capability
in `docs/personal_research_memory_product_contract.md` and scheduled in
`docs/tasks.md`. PRM-22 now implements only the fixture-first linked-source
resolver/cache layer. PRM-23 now implements the bounded fixture-first
`memory research` planner/CLI with deterministic synthesis; runtime dogfood and
live/provider-backed research remain unapproved.

Default budget before approval:

| Control | Value |
| --- | ---: |
| Contract/docs cost | $0 |
| Implementation/test provider calls | 0 |
| Implementation/test external web calls | 0 |
| Implementation/test service starts | 0 |
| Fixture/fake-client tests | allowed |
| Live linked-source fetch | approval required |
| Real provider synthesis over private snippets | approval required |
| Vector/backend adoption | approval required through PRM-8 ADR |

PRM-22 implementation receipts must report `model_calls=0`,
`estimated_cost_usd=0`, `external_skill_used=false`, and
`provider_summarization_used=false` for fixture/fake-client runs. A fetcher that
requires live HTTP, an external skill, or provider summarization must be refused
unless approval switches also include a nonzero budget or fetch/call cap and an
approval reference.

PRM-23 implementation receipts must report `model_calls=0`,
`estimated_cost_usd=0`, `bounded_telegram_snippet_provider_egress=false`,
`raw_telegram_corpus_egress=false`, `external_skill_used=false`, and
`durable_writes=false`. The planner refuses open-ended browsing, provider
egress, nonzero model/cost budgets, oversized tool/source/retry/prompt/timeout
limits, and keeps all memory/project/action proposals as confirmation-gated
drafts.

If the operator later approves a bounded research-session dogfood, approval
must name:

- total budget in USD;
- max provider calls;
- max linked-source fetches;
- whether bounded Telegram snippets may leave the machine;
- whether linked-source excerpts may be cached durably;
- whether Telegram `prm-assistant` service start is allowed.

## PRM-26 Hybrid/Vector Gate Budget

ADR-003 accepts the no-vector path for now and records no approved
vector/backend budget. Current limits are:

| Control | Value |
| --- | ---: |
| Embedding rows | 0 |
| Embedding tokens/chars | 0 |
| Provider egress calls | 0 |
| Vector backend writes | 0 |
| Production migrations | 0 |
| Max provider cost | $0 |

Any future backend experiment must name the provider/model or local model,
backend, max rows, max tokens/chars, persistence boundary, rollback plan, and
cost ceiling in an accepted ADR before execution.

PRM-28 no-vector answer-gate implementation stays inside the same local budget:
0 provider calls, 0 model calls, 0 embedding rows, 0 vector writes, and no
service start.

## PRM-27 Local Vector Sidecar Budget

ADR-004 approves only deterministic local vectorization and a local SQLite
sidecar:

| Control | Value |
| --- | ---: |
| Embedding provider calls | 0 |
| External embedding payload chars | 0 |
| Hosted vector service calls | 0 |
| Canonical DB writes | 0 |
| Production migrations | 0 |
| Provider cost | $0 |

The expected cost is local CPU time and disk for `data/vector/archive_vector.sqlite`.
Any provider embedding model, hosted vector database, LLM reranker, production
migration, or service-start budget requires a separate explicit approval.
