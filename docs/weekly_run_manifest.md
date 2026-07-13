# Weekly Run Manifest Contract

Version: `weekly_run_manifest.v1`  
Status: IRX-2 through IRX-5 `implemented_and_verified`; canonical curation and
editorial synthesis remain additive/opt-in and do not change the frozen IRX-2
stage policy
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

The following policy-bearing example is abridged only at the common per-stage
bookkeeping level. The required-stage set, complete stage-policy membership,
and disabled later-owned stages are normative.

```json
{
  "schema_version": "weekly_run_manifest.v1",
  "pipeline_profile": "irx2_orchestration.v1",
  "run_id": "tra-weekly-2026-W28-20260713T070252Z",
  "supersedes_run_id": null,
  "run_date": "2026-07-13",
  "generated_at": "2026-07-13T07:02:52Z",
  "reporting_week": "2026-W28",
  "week_label": "2026-W28",
  "period_mode": "completed_iso_week",
  "analysis_period_start": "2026-07-06T00:00:00Z",
  "analysis_period_end": "2026-07-13T00:00:00Z",
  "run_status": "running",
  "partial": false,
  "cancellation_requested": false,
  "finalized_at": null,
  "knowledge_refresh_status": "pending",
  "reaction_sync_status": "pending",
  "frontier_analysis_id": null,
  "frontier_analysis_path": null,
  "market_lens_path": null,
  "radar_status": "pending",
  "radar_json_path": null,
  "weekly_brief_html_path": null,
  "weekly_brief_json_path": null,
  "atlas_html_path": null,
  "atlas_json_path": null,
  "audit_explorer_path": null,
  "feedback_snapshot": null,
  "report_generation_status": "pending",
  "required_stages": [
    "knowledge_refresh",
    "reaction_sync",
    "feedback_snapshot",
    "frontier_analysis",
    "radar",
    "weekly_brief",
    "knowledge_atlas"
  ],
  "stage_policy": {
    "knowledge_refresh": {
      "enabled": true,
      "required": true,
      "fatal": true,
      "degrades_on_failure": false
    },
    "reaction_sync": {
      "enabled": true,
      "required": true,
      "fatal": false,
      "degrades_on_failure": true
    },
    "feedback_snapshot": {
      "enabled": true,
      "required": true,
      "fatal": false,
      "degrades_on_failure": true
    },
    "canonical_thread_curation": {
      "enabled": false,
      "required": false,
      "fatal": false,
      "degrades_on_failure": false
    },
    "frontier_analysis": {
      "enabled": true,
      "required": true,
      "fatal": false,
      "degrades_on_failure": true
    },
    "radar": {
      "enabled": true,
      "required": true,
      "fatal": false,
      "degrades_on_failure": true
    },
    "editorial_intelligence": {
      "enabled": false,
      "required": false,
      "fatal": false,
      "degrades_on_failure": false
    },
    "weekly_brief": {
      "enabled": true,
      "required": true,
      "fatal": true,
      "degrades_on_failure": false
    },
    "knowledge_atlas": {
      "enabled": true,
      "required": true,
      "fatal": false,
      "degrades_on_failure": true
    },
    "knowledge_audit_explorer": {
      "enabled": false,
      "required": false,
      "fatal": false,
      "degrades_on_failure": false
    },
    "reader_value_gates": {
      "enabled": false,
      "required": false,
      "fatal": false,
      "degrades_on_failure": false
    }
  },
  "stages": {
    "knowledge_refresh": {
      "status": "pending",
      "started_at": null,
      "finished_at": null,
      "artifact_path": null,
      "record_counts": {},
      "error": null
    },
    "reaction_sync": {
      "status": "pending",
      "started_at": null,
      "finished_at": null,
      "snapshot_ref": null,
      "record_counts": {},
      "error": null
    },
    "feedback_snapshot": {
      "status": "pending",
      "snapshot_id": null,
      "cutoff": null,
      "confirmed_event_count": 0,
      "pending_event_count": 0,
      "error": null
    },
    "canonical_thread_curation": {
      "status": "disabled",
      "artifact_path": null,
      "error": null
    },
    "frontier_analysis": {
      "status": "pending",
      "analysis_id": null,
      "artifact_path": null,
      "error": null
    },
    "radar": {
      "status": "pending",
      "required": true,
      "radar_run_id": null,
      "artifact_path": null,
      "artifact_sha256": null,
      "reporting_week": null,
      "error": null
    },
    "editorial_intelligence": {
      "status": "disabled",
      "artifact_path": null,
      "error": null
    },
    "weekly_brief": {"status": "pending", "html_path": null, "json_path": null},
    "knowledge_atlas": {"status": "pending", "html_path": null, "json_path": null},
    "knowledge_audit_explorer": {"status": "disabled", "html_path": null, "json_path": null},
    "reader_value_gates": {"status": "disabled", "artifact_path": null}
  },
  "frontier_analysis_ref": {
    "id": null,
    "path": null
  },
  "radar_json_ref": {
    "path": null,
    "sha256": null,
    "binding_path": null,
    "binding_sha256": null,
    "run_id": null,
    "reporting_week": "2026-W28"
  },
  "feedback_snapshot_ref": {
    "snapshot_id": null,
    "cutoff": "2026-07-13T00:00:00Z",
    "confirmed_event_count": 0,
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

## IRX-2 Orchestration Profile

IRX-2 implements `pipeline_profile=irx2_orchestration.v1`. This is a complete
technical package against the IRX-2 stage policy; it is not a claim that Report
V2 or the IRX-14 dogfood gate is complete.

The initial manifest freezes `stage_policy` before execution. Each entry has
`enabled`, `required`, `fatal`, and `degrades_on_failure`. Membership in
`required_stages` must exactly match `required=true`.

Required and enabled by default in this profile:

- `knowledge_refresh` (the existing bounded Idea Thread refresh/bind step);
- `reaction_sync`;
- `feedback_snapshot`;
- `frontier_analysis`;
- `radar`;
- `weekly_brief`;
- `knowledge_atlas`.

Predeclared disabled/non-required in this frozen profile:

- `canonical_thread_curation` (implemented by IRX-4 as an additive registry,
  not activated as a manifest stage);
- `editorial_intelligence` (implemented by IRX-5 as an opt-in post-V1 shadow,
  not activated as a manifest stage);
- `knowledge_audit_explorer` as a dedicated surface (IRX-7);
- `reader_value_gates` (IRX-11).

The current detailed Atlas remains inspectable through its V1 compatibility
path; IRX-2 does not relabel or redesign it. Aligned opportunity-seed export,
market-lens inputs, and their checksums are canonical dependencies inside the
Radar stage rather than independent reader stages.

An operator may predeclare Radar disabled. In that case its policy is
`enabled=false`, `required=false`, its stage starts `disabled`, the Brief states
that no build decision was produced, and the manifest records a dogfood-blocking
warning. Unexpected Radar absence is never converted into this state.

`report_generation_status` is a deterministic flat projection: `pending` or
`running` while either reader stage is active, `failed` when either render stage
fails, and `succeeded` only when both Brief and Atlas succeed. The overall run
may still be `partial` when Atlas fails but a valid Brief exists. Dedicated
Audit Explorer paths remain null under this profile. `market_lens_path` must
equal the Radar stage dependency ref, and all other flat refs must equal their
nested canonical records.

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

Manifest `run_id` and Radar `radar_run_id` are distinct identifiers. IRX-2 uses
an additive `radar_run_binding.v1` envelope containing both IDs, all reporting
period fields, Radar contract/schema version, seed export path/checksum, Radar
JSON path/checksum, and the selected candidate/status projection. The raw Radar
V1 payload remains gate-authoritative; the envelope proves which immutable raw
bytes belong to the weekly run. A zero-seed export receives the same companion
identity envelope, because a bare empty JSON array cannot prove period identity.

The reaction stage records `snapshot_ref` and `observed_through`. The latter is
the successful sync completion timestamp and may be later than manifest
`generated_at`; source-post eligibility still uses the analysis period. If sync
fails, the report uses only the pre-run cutoff and declares the reaction
snapshot partial. Feedback snapshot cutoff remains the exclusive analysis
period end unless its owning future task versions that semantic.

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

Every stage record contains immutable `enabled`, `required`, `fatal`, and
`degrades_on_failure`, plus `status`, `attempt`, nullable start/finish times,
bounded sanitized `error`, `record_counts`, dependency/artifact refs, and
checksums. A `degraded=true` marker represents a validated fallback without
pretending that ordinary `succeeded` is full quality.

Allowed transitions are:

```text
pending -> running | skipped_dependency | cancelled
running -> succeeded | failed | cancelled
failed | skipped_dependency | cancelled -> running
  only while the manifest is still unfinalized, with attempt incremented
succeeded | disabled -> terminal
```

Enabled stages start `pending`; predeclared disabled stages start `disabled`.
Terminal manifests are immutable. The state machine permits a failed, skipped,
or cancelled stage to transition back to `running` only inside an unfinalized
manifest and increments its attempt counter. The public
`weekly-intelligence-v2` CLI does not expose same-ID resume: an operational retry
creates a new `run_id` and may set `supersedes_run_id`.

Run aggregation order is deterministic:

1. explicit cancellation -> `cancelled`;
2. manifest validation or a fatal stage failure, including Weekly Brief render
   failure -> `failed`;
3. otherwise any partial period, required/nonfatal failure, unexpected enabled
   stage failure/skip, failed reaction or feedback snapshot, unavailable exact
   Frontier result, Radar mismatch/failure, validated fallback, or Atlas failure
   -> `partial`;
4. otherwise all required stages succeeded with no degradation -> `complete`.

An empty completed period is `complete` when all stages succeed. `partial` is a
derived boolean and is always true for `run_status=partial`; it is never used to
hide a failed run.

## Partial And Failed Behavior

| Condition | Manifest result | Reader behavior |
|---|---|---|
| Radar expected but missing | `partial`, Radar `failed` | visible partial banner; no candidate fiction |
| Radar wrong week/run | `partial`, Radar `failed` | mismatch named in technical details |
| Reaction sync failed | `partial` | receipt says reactions were not refreshed |
| Any enabled stage is explicitly marked `degraded` after a validated fallback | `partial` | degraded stage named; no complete-quality claim |
| Brief render failed | `failed` | do not deliver a stale prior Brief as current |
| Atlas render failed, Brief succeeds | `partial` | Brief may deliver with Atlas unavailable |
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
8. The core records `attempt` for transitions inside an unfinalized manifest;
   the public CLI retries as a new run, optionally linked by
   `supersedes_run_id`.

IRX-2 uses a provisional internal run-scoped root
`data/output/weekly_intelligence_runs/<run_id>/`. This does not choose final V2
aliases or retention; IRX-14 still owns those decisions. Initial creation is
exclusive, manifest updates use a same-directory temporary file plus validated
atomic rename, and terminal manifests/artifacts are immutable. V1 week-named
paths remain diagnostic compatibility surfaces and are never package identity.

## Orchestrator Ownership

IRX-2 defines the explicit additive `weekly-intelligence-v2` command as the
owner of the technical package. Its target lifecycle is:

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

Under `irx2_orchestration.v1`, curation, editorial, Audit Explorer, and
reader-gate steps in the target flow are recorded as predeclared disabled
stages. The additive IRX-4 registry and IRX-5 shadow artifact do not mutate this
policy or their disabled stage records. The existing standalone commands remain
available for diagnostics and historical regeneration. They do not
independently claim to have produced a complete V2 package.

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

## Implementation Verification

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_reporting_period \
  tests.test_weekly_run_manifest \
  tests.test_weekly_intelligence_orchestrator \
  tests.test_split_intelligence_reports \
  tests.test_mvp_weekly_pipeline \
  tests.test_pi_facade
```

```bash
rg -n "run_id|reporting_week|analysis_period_start|analysis_period_end|partial" \
  src/output tests systemd
```

Cross-repository:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest \
  tests/test_mvp_of_week.py
```

The IRX-2 focused local suites and the unchanged sibling Radar focused suite
passed during implementation review. Heavy/live pipelines and the full suite
were intentionally not run.

## IRX-2 Implementation Receipt

Implemented on 2026-07-13 as an additive path beside the V1 commands:

- one immutable run directory and atomically replaced manifest per invocation;
- frozen stage policy, deterministic transitions/aggregation, sanitized errors,
  warnings, failed-stage disclosure, and validated terminal delivery;
- exact run/period/checksum binding for the seed export, optional immutable
  `radar/live-intelligence.json`, market lens, raw Radar result,
  `radar_run_binding.v1`, Frontier snapshot, Brief, and Atlas;
- one exclusive `analysis_period_end` feedback cutoff shared by the snapshot,
  readers, and Frontier cache identity, plus a content fingerprint that rejects
  a concurrently replaced Frontier week row before it is bound;
- manifest-aware Hermes/PI artifact selection that rejects failed, stale,
  mismatched, or tampered same-run inputs instead of falling back to adjacency;
- visible partial/disabled behavior while the frozen profile keeps curation,
  editorial synthesis, the dedicated Audit Explorer, and reader-value gates
  disabled; later additive implementations do not implicitly activate them.

Existing V1 commands and paths remain compatibility surfaces. No generated
report was edited or committed, and no Radar evidence or context-only gate was
changed. The historical IRX-3 handoff is closed by the additive binding below;
the subsequent IRX-4 handoff is closed by its additive registry receipt.

## IRX-3 Reaction Snapshot And Effect Binding

Implemented on 2026-07-13 without changing `weekly_run_manifest.v1` or the
`irx2_orchestration.v1` policy identity:

- a new IRX-3 invocation accepts reaction sync as successful only when it
  returns the rich current-attempt outcome and binds
  `reaction_sync/reaction-snapshot.json` by exact manifest identity, declared
  path, SHA-256 checksum, `snapshot_ref`, and `observed_through`;
- `reaction_visibility_snapshot.v1` records exact IRX-1 period identity,
  candidate/checked coverage, observed-post count, event count, and opaque
  per-post/per-emoji provenance. Candidate/checked and event-count parity is
  required; partial, failed, truncated, wrong-period, stale, or tampered input
  cannot create a fresh ranking signal;
- the reaction stage records both unique reacted posts and raw personal emoji
  events. Multiple visible emoji remain separate provenance events but collapse
  to one equal positive interest signal per post; aggregate-only reactions are
  not personal events;
- every succeeded Brief and Atlas in a run with a verified rich snapshot must
  carry a strict `reaction_personalization.v1` effect receipt. The manifest
  binds each receipt to the same run, period, snapshot, source-post lineage,
  funnel, attribution, and actual surface refs, and rejects lost or
  double-consumed reaction events;
- Brief and Atlas may legitimately differ in surface-specific selected items,
  influence status, and bounded unconsumed reasons. Their common identity,
  snapshot lineage, pre-surface funnel, policy, and attribution must agree, and
  each sidecar/HTML disclosure must match its own receipt;
- legacy IRX-2 manifests without the rich snapshot binding remain readable,
  and the legacy count-only reaction-sync API remains available. A new IRX-3
  orchestration run does not treat that count-only result as an attested
  snapshot and therefore fails closed to a visible partial state.

No canonical thread registry or historical period-end thread membership was
added by IRX-3. Those versioned lineage guarantees were its explicit IRX-4
handoff; IRX-3 receipts continue to retain compatibility refs while the stored
IRX-4 resolver fills their nullable canonical refs.

## IRX-4 Canonical Registry Binding

Implemented on 2026-07-13 without changing `weekly_run_manifest.v1`,
`irx2_orchestration.v1`, required-stage membership, or Radar binding:

- curator decisions may carry the existing immutable run identity for audit,
  while canonical lifecycle and membership are resolved historically against
  the same exclusive `analysis_period_end` used by the run;
- canonical persistence is append-only and separate from raw threads. Existing
  manifests, raw compatibility refs, checksums, stage transitions, and terminal
  aggregation remain readable and unchanged;
- the predeclared `canonical_thread_curation` stage remains disabled and
  non-required in the frozen IRX-2 profile. Enabling or revising orchestration
  policy is not implicit in registry implementation and was outside IRX-4;
- report/Frontier sidecars carry bounded canonical snapshots additively, so a
  same-period curator correction invalidates its exact dependent cache without
  weakening manifest or Radar freshness checks.

No generated package, live pipeline, Radar artifact, evidence rule, or sibling
repository was changed.

## IRX-5 Editorial Shadow Binding

Implemented on 2026-07-13 without changing `weekly_run_manifest.v1`,
`irx2_orchestration.v1`, required-stage membership, terminal aggregation, or
Radar gate behavior:

- `editorial_intelligence` remains explicitly `enabled=false`,
  `required=false`, and `status=disabled` in the frozen profile. IRX-5 does not
  write an editorial stage transition, add the shadow path to a finalized
  manifest, or claim that a V2 package was produced;
- `generate_split_intelligence_reports(..., editorial_output_root=...)` is an
  explicit opt-in compatibility hook. It renders both unchanged V1 artifacts
  first and only then attempts one run-scoped shadow artifact. With no opt-in,
  the editorial generator is not imported or called;
- production editorial generation treats the persisted manifest as authority.
  It reloads exact run/date/period/profile identity and verifies that paths stay
  inside the run directory. For a rich current run it verifies the bound
  reaction snapshot and effect receipt; the legacy no-eligible-reaction path
  cannot create personalization. It also verifies a succeeded feedback stage
  with exact cutoff/count and a succeeded Radar stage with binding/artifact
  schemas, run/period parity, and SHA-256 checksums. An in-memory Radar binding
  is accepted only as comparison material against those persisted bytes;
- any missing, stale, partial, wrong-run, wrong-period, out-of-root, malformed,
  or tampered manifest/Radar/reaction/feedback input fails closed. The release
  policy forbids the model call and permits only a visibly partial exact
  deterministic artifact; it never upgrades absence into a normal complete
  result or weakens Radar permission;
- the shadow file is exclusively created under its own `run_id`; a complete
  cache hit requires the same validated input hash and requested model, while a
  partial, mismatched, or malformed existing path is immutable and requires a
  new run ID;
- shadow import, input, model, validation, and persistence exceptions are
  isolated after V1 rendering. Brief and Atlas summaries/paths still return,
  `editorial_intelligence` is null, and the audit-only
  `editorial_intelligence_error` records the exception class without exposing
  message contents.

The 67-test focused editorial matrix, exact 49-test required acceptance command,
and 149 extended affected-surface tests passed. No live LLM call, generated
report mutation, cross-repository change, or Radar gate change was made. Shadow
comparison evidence, manifest-stage activation, V2 renderer consumption,
delivery rollout, and dogfood remain deferred to their owning tasks.

## Stop Conditions

Stop for operator review if implementation would:

- treat a missing Radar artifact as a normal complete run;
- bind a Radar artifact from another period/run;
- weaken Radar evidence gates;
- hide a partial state from the reader;
- remove historical explicit-week generation;
- overwrite V1 artifacts without a compatibility plan;
- persist secrets, raw prompts, or private report content in the manifest.
