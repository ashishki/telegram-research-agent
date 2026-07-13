# Weekly Run Manifest Contract

Version: `weekly_run_manifest.v1`  
Status: IRX-1 time semantics implemented; IRX-2 manifest/orchestration planned
Owner: `telegram-research-agent`

The weekly run manifest is the identity and state spine for one intelligence
package. It separates generation time from analysis time and binds Knowledge
refresh, reactions, feedback, Frontier Analysis, Radar, editorial synthesis,
Brief, Atlas, and Audit Explorer to the same run.

It is not a replacement for evidence sidecars. It records which versioned
artifacts belong together and whether the package is complete, partial, failed,
or intentionally disabled at a declared stage.

## Time Semantics

All stored boundaries are UTC ISO-8601 timestamps. The analysis interval is
half-open: `analysis_period_start <= event < analysis_period_end`.

Required concepts:

| Field | Meaning |
|---|---|
| `run_date` | Calendar date on which orchestration started, derived from `generated_at` |
| `generated_at` | Exact UTC timestamp at which this manifest/run was created |
| `analysis_period_start` | Inclusive evidence boundary |
| `analysis_period_end` | Exclusive evidence boundary |
| `reporting_week` | ISO week represented by the period |
| `period_mode` | How the period was resolved |

Allowed `period_mode` values:

- `completed_iso_week`: default scheduled/manual weekly mode; resolves the last
  fully completed ISO week at run time;
- `explicit_iso_week`: operator supplied a completed `YYYY-Www`;
- `trailing_seven_days`: separate rolling mode with exact dates; must not be
  labeled as an ISO-week report;
- `partial_iso_week`: diagnostic-only opt-in for an incomplete current week;
  forces `partial=true` and a visible partial banner.

Default Monday example:

```json
{
  "run_date": "2026-07-13",
  "generated_at": "2026-07-13T07:02:52Z",
  "analysis_period_start": "2026-07-06T00:00:00Z",
  "analysis_period_end": "2026-07-13T00:00:00Z",
  "reporting_week": "2026-W28",
  "period_mode": "completed_iso_week"
}
```

The reader title uses inclusive human dates, for example:
`Недельный бриф: 6-12 июля 2026`. The generation timestamp is shown separately:
`Сформировано 13 июля 2026, 09:02 CEST`.

### Explicit Week Rules

- A completed historical `--week 2026-W28` resolves exactly to W28.
- A future week is rejected.
- The current incomplete week is rejected unless the caller explicitly selects
  `partial_iso_week`.
- `week_label` remains an additive compatibility alias for
  `reporting_week` during V1/V2 migration.
- Period resolution must be shared by report context, Frontier Analysis,
  reaction eligibility, feedback snapshot, opportunity seeds, and Radar.

## Manifest Shape

```json
{
  "schema_version": "weekly_run_manifest.v1",
  "run_id": "tra-weekly-2026-W28-20260713T070252Z",
  "run_date": "2026-07-13",
  "generated_at": "2026-07-13T07:02:52Z",
  "reporting_week": "2026-W28",
  "week_label": "2026-W28",
  "period_mode": "completed_iso_week",
  "analysis_period_start": "2026-07-06T00:00:00Z",
  "analysis_period_end": "2026-07-13T00:00:00Z",
  "run_status": "running",
  "partial": false,
  "knowledge_refresh_status": "succeeded",
  "reaction_sync_status": "succeeded",
  "frontier_analysis_id": 42,
  "frontier_analysis_path": "data/output/frontier_analysis/2026-W28.json",
  "market_lens_path": "data/output/market_context_lens/current.json",
  "radar_status": "succeeded",
  "radar_json_path": "../Demand-to-MVP-Radar/reports/mvp_of_week/mvp-weekly-2026-W28.json",
  "weekly_brief_html_path": null,
  "weekly_brief_json_path": null,
  "atlas_html_path": null,
  "atlas_json_path": null,
  "audit_explorer_path": null,
  "feedback_snapshot": "feedback-before-2026-W28-end",
  "report_generation_status": "pending",
  "required_stages": [
    "knowledge_refresh",
    "reaction_sync",
    "frontier_analysis",
    "radar",
    "editorial_intelligence",
    "weekly_brief",
    "knowledge_atlas",
    "knowledge_audit_explorer"
  ],
  "stages": {
    "knowledge_refresh": {
      "status": "succeeded",
      "started_at": "2026-07-13T07:02:53Z",
      "finished_at": "2026-07-13T07:04:10Z",
      "artifact_path": null,
      "record_counts": {"atoms": 35, "threads": 24},
      "error": null
    },
    "reaction_sync": {
      "status": "succeeded",
      "started_at": "2026-07-13T07:04:10Z",
      "finished_at": "2026-07-13T07:04:50Z",
      "snapshot_ref": "reaction-snapshot:tra-weekly-2026-W28-20260713T070252Z",
      "record_counts": {
        "reactions_detected": 18,
        "posts_resolved": 15
      },
      "error": null
    },
    "frontier_analysis": {
      "status": "succeeded",
      "analysis_id": 42,
      "artifact_path": "data/output/frontier_analysis/2026-W28.json",
      "error": null
    },
    "radar": {
      "status": "succeeded",
      "required": true,
      "radar_run_id": "mvp-weekly-2026-W28",
      "artifact_path": "../Demand-to-MVP-Radar/reports/mvp_of_week/mvp-weekly-2026-W28.json",
      "artifact_sha256": "<sha256>",
      "reporting_week": "2026-W28",
      "error": null
    },
    "editorial_intelligence": {
      "status": "pending",
      "artifact_path": null,
      "error": null
    },
    "weekly_brief": {"status": "pending", "html_path": null, "json_path": null},
    "knowledge_atlas": {"status": "pending", "html_path": null, "json_path": null},
    "knowledge_audit_explorer": {"status": "pending", "html_path": null, "json_path": null}
  },
  "frontier_analysis_ref": {
    "id": 42,
    "path": "data/output/frontier_analysis/2026-W28.json"
  },
  "radar_json_ref": {
    "path": "../Demand-to-MVP-Radar/reports/mvp_of_week/mvp-weekly-2026-W28.json",
    "run_id": "mvp-weekly-2026-W28",
    "reporting_week": "2026-W28"
  },
  "feedback_snapshot_ref": {
    "snapshot_id": "feedback-before-2026-W28-end",
    "cutoff": "2026-07-13T00:00:00Z",
    "confirmed_event_count": 5,
    "pending_event_count": 0
  },
  "artifacts": {
    "weekly_brief_html_path": null,
    "weekly_brief_json_path": null,
    "atlas_html_path": null,
    "atlas_json_path": null,
    "audit_explorer_html_path": null,
    "audit_explorer_json_path": null,
    "editorial_json_path": null
  },
  "warnings": [],
  "failed_stages": [],
  "created_by": {
    "command": "weekly-intelligence-v2",
    "host": "<redacted-or-stable-host-id>",
    "git_commit": "<commit>"
  }
}
```

Paths are illustrative. The implementation must define explicit V2 output
directories in IRX-14 and must not infer package identity from a filename alone.

The flat status/path fields are the required manifest summary projection for
operators and simple consumers. `stages`, typed refs, and `artifacts` carry the
full execution detail. Validators require exact parity between each summary
field and its nested canonical record; neither representation may drift or be
filled from an unrelated prior run.

## Identity Rules

- `run_id` is unique and immutable.
- Every V2 sidecar contains `run_id`, `reporting_week`,
  `analysis_period_start`, `analysis_period_end`, and `manifest_path`.
- Radar binding requires matching reporting period and a declared
  `radar_run_id`; path existence alone is insufficient.
- The manifest records a checksum for cross-repository immutable inputs.
- Regeneration creates a new run ID and may name `supersedes_run_id`; it does not
  rewrite the prior manifest.
- `generated_at` may differ across stage artifacts, but their `run_id` and
  analysis period must match.

## Stage Status Contract

Allowed stage statuses:

- `pending`;
- `running`;
- `succeeded`;
- `failed`;
- `disabled`;
- `skipped_dependency`;
- `cancelled`.

Allowed run statuses:

- `running`;
- `complete`;
- `partial`;
- `failed`;
- `cancelled`.

`complete` means every required stage succeeded. A stage may be `disabled` only
when the run request declared it disabled before execution. An intentionally
disabled Radar stage may produce a complete technical package only when
`required=false`; the Brief must still say:

> MVP Radar отключен для этого запуска. Решение по сборке не сформировано.

Such a run does not pass the IRX-14 dogfood start gate.

Unexpected missing, wrong-week, wrong-run, invalid, or failed Radar always makes
the reader package partial or failed.

## Partial And Failed Behavior

| Condition | Manifest result | Reader behavior |
|---|---|---|
| Radar expected but missing | `partial`, Radar `failed` | visible partial banner; no candidate fiction |
| Radar wrong week/run | `partial`, Radar `failed` | mismatch named in technical details |
| Reaction sync failed | `partial` | receipt says reactions were not refreshed |
| Editorial model failed, deterministic fallback succeeds | `partial` | fallback banner; no claim of full editorial quality |
| Brief render failed | `failed` | do not deliver a stale prior Brief as current |
| Atlas render failed, Brief succeeds | `partial` | Brief may deliver with Atlas unavailable |
| Audit Explorer fails | `partial` | reader surfaces may deliver; technical link unavailable |
| Current-week diagnostic requested | `partial` | exact partial dates in header |
| Empty completed period with successful stages | `complete` | explicit zero-evidence report, not pipeline-failure copy |

Russian partial banner example:

> Частичный выпуск. Не завершены этапы: MVP Radar и синхронизация реакций.
> Выводы ниже ограничены; решение о сборке запрещено.

The package must never substitute a previous successful artifact without
labeling it stale and outside the current run.

## Write And Recovery Rules

1. Create the manifest before any stage and persist `running`.
2. Update a stage to `running` before invoking it.
3. Write stage outputs to temporary paths and atomically rename on validation.
4. Record `succeeded` only after schema and period/run checks pass.
5. Sanitize exceptions into a bounded `error` object; do not store secrets.
6. Recompute `partial`, `failed_stages`, and `run_status` after every stage.
7. Deliver only from the finalized manifest.
8. A resumed run retains its run ID and records `attempt` per stage.

## Orchestrator Ownership

IRX-2 will define one command that owns the package. The target flow is:

```text
resolve period
  -> create manifest
  -> refresh knowledge
  -> sync reactions
  -> snapshot confirmed feedback
  -> curate canonical threads
  -> run Frontier Analysis
  -> export aligned Radar seeds
  -> run/bind Radar
  -> synthesize editorial JSON
  -> render Brief, Atlas, Audit Explorer
  -> run reader-value gates
  -> finalize manifest
  -> deliver finalized artifacts
```

The existing standalone commands remain available for diagnostics and
historical regeneration. They do not independently claim to have produced a
complete V2 package.

## Validation Requirements

- JSON Schema or equivalent deterministic validation.
- ISO week/boundary validation, including year transitions.
- cross-artifact `run_id` and period parity.
- Radar checksum, run ID, and reporting-week parity.
- no path traversal outside declared artifact roots.
- stage status transition validation.
- `complete` cannot coexist with required failed/pending stages.
- `partial=false` cannot coexist with `run_status=partial`.
- expected output file must exist and validate before a stage succeeds.

## Planned Verification

```bash
PYTHONPATH=src python3 -m pytest \
  tests/test_reporting_period.py \
  tests/test_weekly_run_manifest.py \
  tests/test_split_intelligence_reports.py \
  tests/test_mvp_weekly_pipeline.py
```

```bash
rg -n "run_id|reporting_week|analysis_period_start|analysis_period_end|partial" \
  src/output tests systemd
```

Cross-repository:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest \
  tests/test_mvp_of_week.py \
  tests/test_telegram_research_bridge.py \
  tests/test_validation_evidence.py
```

## Stop Conditions

Stop for operator review if implementation would:

- treat a missing Radar artifact as a normal complete run;
- bind a Radar artifact from another period/run;
- weaken Radar evidence gates;
- hide a partial state from the reader;
- remove historical explicit-week generation;
- overwrite V1 artifacts without a compatibility plan;
- persist secrets, raw prompts, or private report content in the manifest.
