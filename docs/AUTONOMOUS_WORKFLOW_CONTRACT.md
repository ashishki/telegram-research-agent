# Autonomous Workflow Contract

Status: proposed

## Workflows

| Workflow | Trigger | Required behavior |
| --- | --- | --- |
| ingestion | scheduled/manual | idempotently sync retained posts without report generation side effects |
| archive indexing | after ingestion | keep FTS/index freshness visible and rollback-safe |
| reaction fast lane | after reaction sync | mark reacted posts searchable and enqueue enrichment |
| enrichment queue | scheduled/manual | process priority posts within cost and retry limits |
| weekly projection | scheduled/manual | generate secondary Brief/Library views from current state |

## Requirements

- idempotency key per run;
- run receipt with inputs, outputs, counts, failures, cost, and freshness;
- no raw post text in normal logs;
- partial failure degrades only the affected projection/tool;
- failed enrichment does not remove archive search availability;
- rollback and reindex path documented before activation.

## Forbidden During Planning

- live Telegram ingestion;
- reaction sync;
- LLM extraction;
- Frontier or Radar generation;
- weekly report generation;
- full archive indexing changes;
- embeddings.
