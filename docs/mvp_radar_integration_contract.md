# MVP Radar Integration Contract

Version: 1.1
Last updated: 2026-07-14
Status: supporting cross-repo evidence contract; IRX-2 same-run binding and
IRX-10 reader projection `implemented_and_verified`
Contract version: `tra-radar-intelligence-contract.v1`

IRX-2 added `weekly_run_manifest.v1` around this exchange. The evidence contract
remains compatible; a Report V2 package must additionally match run identity,
reporting week, and half-open analysis boundaries. Expected missing, wrong-run,
or wrong-week Radar must not crash rendering, but it must make the package
visibly partial rather than complete-looking.

IRX-2 freezes this additive identity layer as `radar_run_binding.v1`. The
manifest run ID and Radar run ID are separate. Telegram Research Agent validates
the raw Radar result, then writes an immutable binding envelope containing both
IDs, the full reporting period, contract version, seed/Radar paths and SHA-256
checksums, and the selected candidate/status projection. Existing Radar V1
evidence fields and gates are not changed by this wrapper.

This contract defines how `telegram-research-agent` and
`Demand-to-MVP-Radar` exchange intelligence. Radar is a parallel downstream
consumer and opportunity validation engine. It is not the center of the Personal
Intelligence product.

Sibling repo verified on 2026-07-10:

```text
/srv/openclaw-you/workspace/Demand-to-MVP-Radar
```

The sibling repo contains implemented RVE code and tests for validation query
planning, matched external evidence, context-only market lens handling, and
SERP/Reddit/crawler/X validation adapters. Live weekly validation still needs
dogfood evidence.

## Ownership

| Area | Owner |
|---|---|
| Knowledge Atoms, Idea Threads, market/business context pack, Weekly Brief, Atlas, Hermes retrieval | `telegram-research-agent` |
| Candidate Dossier, validation queries, external evidence matching, source gates, Radar Markdown/JSON report | `Demand-to-MVP-Radar` |
| Contract version, sidecar/rendered-output parity, stale/missing artifact behavior | cross-repo |

## Telegram Research Agent Sends To Radar

The sibling invocation receives the Radar-specific run ID as `--run-id`, the
immutable opportunity-seed export, and, when present, the immutable
live-intelligence snapshot. Period and intelligence fields below travel in
those input documents. `manifest_run_id` is Telegram-side package identity and
is not sent to the sibling process.

Required exchange inputs:

- `contract_version`: `tra-radar-intelligence-contract.v1`;
- `radar_run_id` assigned specifically to the Radar invocation;
- `intelligence_contract_version`: `tra-intelligence-contract.v1` when the row
  is derived from Telegram Research Agent canonical intelligence;
- `reporting_week` and compatibility `week_label`;
- `analysis_period_start` and `analysis_period_end`;
- `period_mode`;
- `generated_at`;
- Knowledge Thread-backed opportunity seeds;
- source atom provenance;
- source URLs and source refs;
- market/business analyst context;
- ICP hints;
- pain hypotheses;
- WTP hints;
- distribution hints;
- workflow opportunity hints;
- anti-signals;
- context freshness;
- `context_only` marker where applicable.

Market/business analyst context remains:

- `context_only`;
- hypothesis and framing input;
- source of ICP, pain, distribution, WTP, and workflow hints;
- not build-ready evidence;
- not a way to bypass external evidence gates.

## Radar Returns To Telegram Research Agent

Required raw response/result fields:

- `contract_version` or `schema_version`;
- Radar `run_id` matching the requested `radar_run_id`;
- `generated_at`;
- candidate list;
- selected candidate;
- stable candidate ID;
- dossier status;
- recommendation;
- confidence;
- source mix;
- matched external evidence;
- context-only evidence;
- missing evidence by category;
- validation query pack;
- adapter status;
- next validation action;
- decision change action;
- next experiment;
- kill criteria;
- existing-project overlap;
- artifact path.

After validating and copying the raw result, Telegram Research Agent creates
`radar_run_binding.v1`; Radar does not return this envelope. The companion adds
`manifest_run_id`, `radar_run_id`, `reporting_week`, compatibility `week_label`,
the half-open analysis boundaries, `period_mode`, declared seed/raw-result
paths and SHA-256 checksums, and the selected candidate/status projection.

The selected candidate should repeat the key contract fields so a downstream
consumer can read the selected object without chasing top-level JSON.

## IRX-10 Reader Projection

Telegram Research Agent translates the verified producer package into
`mvp_radar_reader.v1`. This projection is not another scoring engine. It reloads
the exact manifest, `radar_run_binding.v1`, raw Radar JSON, and opportunity-seed
export, verifies identity and checksums, and preserves the producer decision in
a bounded reader shape.

Authoritative reader states are:

- `available`: one selected candidate passed the complete binding and parity
  checks;
- `no_candidate`: the bound producer run succeeded and explicitly selected no
  candidate.

Non-authoritative states are `missing`, `invalid`, `disabled`, and
`unbound_legacy`. An unbound legacy file may expose a candidate or raw
recommendation only as labelled diagnostic context. It always has
`reader_decision=unavailable` and cannot authorize a build or focused
experiment.

The reader projection includes candidate identity, producer dossier status and
recommendation, `reader_decision`, source-mix state, matching KIR provenance,
matched external proof, unmatched context, missing evidence, producer reason,
decision-change condition, next validation, experiment, kill criteria, and
artifact identity. `available` and `no_candidate` require a current manifest
whose Radar stage is `succeeded`; self-declared schema/state markers are not
authority.

The loader is bounded before JSON parsing and fails closed on oversized files,
invalid UTF-8, non-finite values, excessive nesting, oversized integers,
malformed shapes, path escape, replay, or checksum mismatch. Brief, canonical
exchange, retrieval, visual, editorial, and Hermes/PI consumers may recover
permission-shaped fields only from this manifest-bound path.

## Required Rules

- Market/business Telegram pack remains context-only.
- Telegram commentary does not pass external evidence gates.
- Market context cannot raise a candidate to `build`.
- Radar may return `investigate` or `reject`; no build-ready candidate is a
  valid outcome.
- Weekly Brief must not hide Radar evidence gaps.
- Hermes must explain which conclusions came from market lens and which came
  from matched external evidence.
- Stale Radar artifact must be explicitly marked.
- Missing Radar artifact must not crash Atlas or Brief rendering; when Radar is
  required, it must make the run partial or failed.
- V1 diagnostic pipelines may remain separately callable. A complete V2 weekly
  package is manifest-linked and requires its declared Radar stage.
- Filename adjacency and a week-shaped filename are never identity proof. The
  raw result `run_id`, binding envelope, validated seed period, and SHA-256 must
  agree before the Radar stage succeeds.
- Manifest-aware consumers treat the bound raw result and envelope as
  authoritative. If either file, identity, period, path, or checksum is missing
  or mismatched, they report the Radar artifact unavailable/invalid and do not
  recover a candidate from an older Brief or adjacent week-named file.
- Cross-repo schema changes must be versioned and tested.
- Sidecar JSON and rendered Markdown/HTML must not contradict each other.

IRX-2 implemented the identity and orchestration wrapper. IRX-10 added the
strict reader projection and diagnostic adapter. Candidate evidence categories,
source matching, recommendation semantics, `context_only` exclusion, and every
existing Radar gate remain unchanged.

## Skill-Assisted Research Boundary

Codex may use locally installed research skills from
`artwist-polyakov/polyakov-claude-skills` as an auxiliary discovery layer:
`reddit-skill`, `x-research`, `yandex-search-api`, `yandex-wordstat`,
`telegram-channel-parser`, and `crawl4ai-seo`.

This layer is not a source-of-truth shortcut. Skill output must be treated as
one of:

- `context_only`;
- `matched_external`;
- `negative`;
- `irrelevant`;
- `credential_limited`;
- `not_run`.

Only `matched_external` records that reference the same selected candidate,
ICP, pain, and workaround may contribute to Radar gates. Search volume, Telegram
commentary, market/business context, or X/Twitter discussion cannot upgrade a
candidate by themselves. See `docs/mvp_skill_research_sources.md` for the local
operator workflow.

## Evidence Roles

| Role | Can satisfy Radar gate? | Notes |
|---|---:|---|
| Knowledge Thread seed | no by itself | useful candidate provenance |
| Market/business analyst context | no | context-only framing and hints |
| Live source intelligence snapshot | no | context-only freshness and repeated-claim hint |
| Skill-assisted Telegram channel parse | no by itself | useful fresh context; same Telegram-only gate boundary |
| Matched external SERP/search demand | sometimes | must match selected candidate and pass source gate |
| Matched Yandex SERP/search demand | sometimes | must verify intent and candidate match |
| Yandex Wordstat demand volume | no by itself | volume/context only unless paired with verified intent evidence |
| Matched Reddit/forum complaint | sometimes | same pain and candidate, not adjacent topic |
| Matched competitor/workaround crawler evidence | sometimes | bounded source, same ICP/pain, not hype-only |
| X/Twitter corroboration | no by itself | lower-confidence corroboration only |
| Negative signal | no | must remain visible and can lower confidence |

## Stale And Missing Artifact Semantics

Legacy/V1 diagnostic paths may classify Radar state as:

- `current`: Radar week matches Brief week and generated timestamp is within
  expected freshness window.
- `stale`: artifact exists but week/timestamp is older than the Brief.
- `missing`: no artifact was provided or discovered.
- `invalid`: JSON/Markdown violates the contract or cannot parse.

Legacy/V1 Brief and Hermes diagnostic behavior:

- `current`: show available fields as diagnostic-only unless the current
  manifest and binding are also present and valid.
- `stale`: show a diagnostic candidate only when useful, label it stale, and
  forbid new weekly decisions.
- `missing`: show "Radar not available" and continue Brief/Atlas.
- `invalid`: show contract error and do not summarize candidate as valid.

Manifest-bound V2 behavior is stricter: an old or wrong-period artifact is an
unavailable/invalid binding, no candidate is exposed from it, and consumers do
not fall back to an older Brief or adjacent week-named file. The required Radar
stage then keeps the package visibly partial or failed according to the frozen
stage policy.

Telegram-side PGI-003 implementation note: Weekly Brief sidecars expose
`mvp_radar_gate`, Brief HTML renders the same gate decision, and Hermes exposes
read-only artifact status for Weekly Brief, Knowledge Atlas, and MVP Radar.
Missing Radar is an explicit warning and cannot permit build/focused decisions.

## Cross-Repo Acceptance

For any schema or contract change:

- update this file and the sibling Radar contract doc;
- bump or explicitly retain `tra-radar-intelligence-contract.v1`;
- add/adjust tests in the owning repo;
- verify sidecar/rendered-output parity;
- verify market context remains context-only;
- verify missing/stale artifacts degrade gracefully.

## Verification Commands

From `telegram-research-agent`:

```bash
PYTHONPATH=src python3 -m pytest tests/test_split_intelligence_reports.py tests/test_mvp_weekly_pipeline.py tests/test_opportunity_seed_export.py
PYTHONPATH=src python3 -m unittest tests.test_mvp_radar_reader tests.test_ai_report_contract tests.test_intelligence_retrieval_items tests.test_pi_facade
```

From `Demand-to-MVP-Radar`:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py tests/test_mvp_report_quality.py tests/test_telegram_research_bridge.py
```

## Current Follow-Up Tasks

- `PGI-001`: completed locally. Telegram-side opportunity seed/context rows and
  Weekly Brief sidecars explicitly carry `tra-radar-intelligence-contract.v1`;
  Brief sidecars also embed a `radar_exchange` summary inside
  `tra-intelligence-contract.v1`.
- `PGI-003`: completed locally. Weekly Brief and Hermes consume Radar artifacts
  read-only, preserve matched external evidence fields, warn on missing/stale
  state, and keep market/business context `context_only`.
- `PGI-005`: completed locally. Project/Learning Intelligence may display
  existing-project overlap as a consumer projection, but it cannot satisfy Radar
  build/focused gates. Broad project overlap remains rejected unless backed by
  matched, source-specific evidence.
- `IRX-10`: implemented and verified. The manifest-bound reader projection is
  the only consumer authority; legacy JSON remains diagnostic-only. IRX-6 is
  the next reader task.
- `RADAR-PGI-001`: add Radar-side cross-link and fixture parity checks for this
  contract version without changing runtime gates.
- `RADAR-PGI-003`: run a bounded weekly validation dogfood pass when fresh
  candidate artifacts and credentials/cache fixtures are available.
