# AI Cost Architecture

Status: draft

## Workload Classes

| Class | Default path | Escalation |
| --- | --- | --- |
| archive_search | deterministic FTS | none |
| selective_extraction | cheap structured model | stronger model only for failed high-priority posts |
| answer_generation | small/standard chat model over bounded context | stronger model for complex comparison after retrieval evidence exists |
| external_verification_summary | bounded source summary | human approval for broader web research |
| evaluation | deterministic metrics first | advisory LLM judge after calibration plan |

## Cost Controls

- metadata filters before retrieval;
- top-k context caps;
- no raw corpus dump;
- batch enrichment only for priority queues;
- retry limit per task;
- cost receipt per AI workflow;
- monthly rollup via `tools/cost_rollup.py` when telemetry exists.

## PRM-6 Selective Extraction Boundary

`src/output/selective_enrichment.py` owns deterministic queue ordering and
budget enforcement for `selective_extraction`. It does not call an LLM provider
directly. A future approved runner must inject the extractor callable and
remain inside the receipt contract.

The planner deduplicates posts and ranks signals in this order:

```text
reaction -> repeated_search_return -> cited_answer -> watch_topic
-> active_project -> repeated_signal -> manual_save
```

The batch receipt records:

- queued posts and attempted posts;
- model-call count;
- estimated cost;
- succeeded, failed, and budget-stopped posts;
- archive search availability after failure;
- per-item failure reason.

Search availability is checked against retained archive rows and SQLite FTS, not
Knowledge Atom presence. Therefore extraction failure cannot remove or hide an
archive search result.

Budget checks are performed before every attempt. A retry is skipped when it
would exceed the cost or model-call cap; the receipt records the stop reason and
excludes raw post text, source URLs, and provider payloads.

## Routing Maturity

Current target: static routing by workload class. Dynamic routing/cascades are
not active and require a separate router eval before use.
