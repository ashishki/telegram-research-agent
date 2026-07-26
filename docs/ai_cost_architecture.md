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

## Routing Maturity

Current target: static routing by workload class. Dynamic routing/cascades are
not active and require a separate router eval before use.
