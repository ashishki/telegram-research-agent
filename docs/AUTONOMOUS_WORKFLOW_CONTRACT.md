# Autonomous Workflow Contract

Status: PRM-17 deterministic contract implemented; runtime activation still
requires human approval
Last updated: 2026-07-29

## Current Runtime State

As of 2026-07-29, no Telegram Research Agent workflow is active in systemd.
The legacy live bot and Report V2 weekly timer were stopped and disabled after
PRM-18 confirmed that dogfood is blocked:

- `telegram-bot.service`: disabled, inactive;
- `telegram-ai-split-report.timer`: disabled, inactive;
- `telegram-ai-split-report.service`: disabled, inactive.

Do not restart those units as PRM dogfood. Future runtime activation should use
a dedicated PRM assistant mode that exposes only approved read-only and
confirmation-gated tools.

## Implementation Boundary

PRM-17 implements the contract registry and telemetry receipt sanitizer in
`src/processing/workflow_telemetry.py`. It does not start scheduled jobs, read
production databases, run live Telegram ingestion, call providers, run Radar,
generate reports, or write production telemetry.

Every workflow contract must list:

- trigger;
- inputs;
- outputs;
- idempotency key;
- retry policy;
- fallback;
- receipt;
- rollback.

## Workflow Registry

| Workflow | Trigger | Inputs | Outputs | Idempotency key | Retry policy | Fallback | Receipt | Rollback |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `telegram_ingestion` | scheduled or manually approved | channel allowlist, cursor, Telegram session ref | raw post upsert counts, cursor receipt | `telegram_ingestion:{channel_set}:{cursor_window}` | max 1 retry for rate limit/network timeout | keep previous archive/search state and mark ingestion freshness stale | run ID, channel count, new/updated counts, cursor before/after, freshness | rerun same cursor window idempotently; restore DB backup only in approved maintenance |
| `archive_indexing` | after ingestion or manually approved | raw/posts counts, index contract version | FTS counts, missing-index counts, freshness receipt | `archive_indexing:{index_contract_version}:{source_count}:{window}` | max 1 retry after backup check for SQLite busy/transient IO | serve prior FTS if integrity passes; otherwise degrade archive search only | source/index counts, missing rows, freshness | restore previous derived index backup or rebuild derived FTS from canonical rows in approved maintenance |
| `reaction_fast_lane` | after reaction sync or manually approved | reaction snapshot ref, archive document IDs, feedback counts | searchable reacted-post count, enrichment queue count, reaction receipt | `reaction_fast_lane:{snapshot_ref}:{archive_contract_version}` | max 1 retry for SQLite busy | preserve archive search and mark reaction personalization stale | reaction count, resolved count, queued count, queue age | append compensating queue/receipt events; do not delete operator reactions |
| `selective_enrichment` | scheduled or manually approved | priority queue snapshot, budget limits, extractor version | enrichment receipts, queue-age receipt, cost receipt | `selective_enrichment:{queue_snapshot}:{budget_window}:{extractor_version}` | max 1 retry per failed item for provider timeout/rate limit | stop on budget or extractor failure; archive search remains available | attempted/succeeded/failed counts, model cost/calls, queue age | disable generated enrichment projection or append compensating events; never mutate raw posts |
| `weekly_brief_v3` | scheduled or manually approved | watch topics, reactions, questions, saved notes, projects, experiments, feedback | Brief V3 JSON, static HTML, visual receipt | `weekly_brief_v3:{week_id}:{context_snapshot_hash}` | max 1 static rerender retry | skip Brief V3 delivery while assistant, archive search, and Knowledge Library remain available | week ID, source-ref count, generation latency, tool calls, no-answer rate | discard generated Brief V3 artifacts; source memory/archive rows unchanged |
| `knowledge_library_projection` | manual query or confirmed Watch Topic | topic, bounded archive hits, confirmed memory events | topic page JSON, static HTML, visual receipt | `knowledge_library_projection:{topic_id}:{context_snapshot_hash}` | max 1 static rerender retry | leave existing topic pages intact and mark requested page unavailable | topic ID, source-ref count, retrieval/generation latency | discard regenerated derived page; confirmed memory/archive rows unchanged |
| `backup_snapshot` | before approved migration, reindex, or rollback | database path ref, aggregate counts, schema version | backup ref, backup checksum, aggregate-count receipt | `backup_snapshot:{database_ref}:{schema_version}:{started_at}` | max 1 retry for transient IO | block maintenance action when backup cannot be verified | backup ref, checksum, source row counts, finished time | use only verified backup refs; never overwrite canonical rows without approval |
| `rollback_reindex_dry_run` | manually approved maintenance | backup ref, aggregate counts, index contract version, dry-run flag | dry-run receipt, integrity counts, rollback decision | `rollback_reindex_dry_run:{backup_ref}:{index_contract_version}:{dry_run_flag}` | no retry without human review | leave production state unchanged and require human review | dry-run flag, source/index counts, error class | dry-run only unless a separate approved maintenance receipt exists |

## Telemetry Receipt

Schema: `workflow_telemetry_receipt.v1`.

Required aggregate metrics:

- index freshness seconds;
- queue age seconds;
- retrieval latency milliseconds;
- generation latency milliseconds;
- model cost USD;
- model calls;
- tool calls;
- no-answer count and rate;
- error class.

Privacy controls:

- raw post text is not logged;
- provider payloads are not logged;
- raw Telegram corpus egress remains false;
- redaction provenance is `deterministic_key_allowlist`;
- raw fields supplied to the builder are recorded only by redacted field name.

Budget controls:

- default weekly workflow ceiling is `$10.00`;
- default weekly model-call ceiling is `500`;
- a telemetry receipt sets `approval_required=true` when either limit is
  exceeded.

Verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_workflow_telemetry.py -q
```

## Forbidden During Planning Or Without Explicit Approval

- live Telegram ingestion;
- reaction sync;
- LLM extraction;
- Frontier or Radar generation;
- weekly report generation;
- full archive indexing changes;
- embeddings.
