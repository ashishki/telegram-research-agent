# Pathway Live Source Intelligence Roadmap

Status: active implementation roadmap
Last updated: 2026-06-12

## Architectural Verdict

Pathway is a good fit for live source intelligence and incremental indexing, but
not as a replacement for the current SQLite-first weekly agent. The safe shape is
an optional sidecar:

```text
canonical Telegram/Radar state
  -> append-only source events
  -> optional Pathway live index / deterministic fallback snapshot
  -> derived live intelligence artifact
  -> Radar reads the artifact as context only
```

SQLite remains the source of truth for posts, feedback, receipts, decisions, and
weekly artifacts. Pathway-derived state is refreshable and must not become
operator-authored feedback or source-trust fact by itself.

## Task Plan

### PTH-TRA-1 - Agent Source Event Log

Status: implemented.

Goal: emit a Pathway-ready append-only event stream from Telegram ingestion
without changing canonical SQLite state.

Implemented via `output.source_events` and ingestion hooks in bootstrap and
incremental ingestion. Events are appended after SQLite commit.

Acceptance:

- Bootstrap and incremental ingest append one JSONL event for each newly inserted
  Telegram post after the SQLite transaction commits.
- Event records include stable upstream id, source type, channel, message id,
  posted/captured timestamps, text, source URL, media type, and view count.
- Generated event files live under `data/events/source_events/` and are not
  committed.
- Ingestion still succeeds if event writing fails only after logging a warning.

### PTH-TRA-2 - Live Source Intelligence Snapshot

Status: implemented.

Goal: build a bounded live-source snapshot from source events for operator and
Radar consumption.

Implemented via `live-source-index`, with optional `--backfill-from-db` for
building an initial event stream from existing `raw_posts`.

Acceptance:

- CLI: `live-source-index --days N` writes
  `data/output/live_source_intelligence/YYYY-WNN.json`.
- Snapshot contains event count, channel activity, demand-surface counts,
  repeated-claim candidates, Radar context hints, and explicit generation mode.
- The default builder is deterministic and local-only.
- If Pathway is installed later, the event contract is ready for a Pathway
  sidecar to consume the same JSONL stream.

### PTH-RADAR-1 - Radar Live Intelligence Context

Status: implemented.

Goal: let Demand-to-MVP Radar read the live intelligence snapshot as context
without treating it as decision-grade external evidence.

Implemented in Demand-to-MVP Radar commit `cfa5c21`: Radar accepts
`--live-intelligence PATH`, renders a `Live Source Intelligence` section, and
keeps source-mix gates unchanged.

Acceptance:

- Radar CLI accepts `--live-intelligence PATH`.
- Candidate Dossier includes a `Live Source Intelligence` section when supplied.
- JSON output and `source_counts` expose the live intelligence summary.
- The context does not increase external evidence counts, source-mix readiness,
  or build/focused-experiment gates.

### PTH-TRA-3 - Agent-to-Radar Bridge

Status: implemented.

Goal: pass the latest generated live intelligence snapshot to Radar during
`mvp-weekly` when available or explicitly generated.

Implemented via `mvp-weekly --with-live-source-index`, optional
`--live-intelligence-path`, and `--backfill-live-source-events`.

Acceptance:

- `mvp-weekly` can generate/pass live intelligence without requiring Pathway.
- Telegram notification may mention live intelligence availability, but not as
  validation.
- If the snapshot is missing, Radar continues normally.

## Deep Review Gates

After each phase:

- Run focused tests for the touched project.
- Confirm no generated `data/output` or `data/events` artifacts are committed.
- Confirm source-mix gates still prevent Telegram-only or live-context-only
  candidates from becoming build-ready.
- Commit and push before moving to the next project.

## Current State

All initial Pathway live source intelligence tasks are implemented. Future work
should only add an actual long-running Pathway sidecar after the JSONL event
contract proves useful in weekly operation.
