# MVP Radar Integration Contract

Version: 1.0
Last updated: 2026-07-10
Status: supporting cross-repo contract
Contract version: `tra-radar-intelligence-contract.v1`

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

Required fields:

- `contract_version`: `tra-radar-intelligence-contract.v1`;
- `intelligence_contract_version`: `tra-intelligence-contract.v1` when the row
  is derived from Telegram Research Agent canonical intelligence;
- `week_label`;
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

Required fields:

- `contract_version` or `schema_version`;
- `week_label`;
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

The selected candidate should repeat the key contract fields so a downstream
consumer can read the selected object without chasing top-level JSON.

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
- Missing Radar artifact must not break Atlas or Brief generation.
- AI Intelligence and Radar pipelines are contract-linked but not fully
  blocking.
- Cross-repo schema changes must be versioned and tested.
- Sidecar JSON and rendered Markdown/HTML must not contradict each other.

## Evidence Roles

| Role | Can satisfy Radar gate? | Notes |
|---|---:|---|
| Knowledge Thread seed | no by itself | useful candidate provenance |
| Market/business analyst context | no | context-only framing and hints |
| Live source intelligence snapshot | no | context-only freshness and repeated-claim hint |
| Matched external SERP/search demand | sometimes | must match selected candidate and pass source gate |
| Matched Reddit/forum complaint | sometimes | same pain and candidate, not adjacent topic |
| Matched competitor/workaround crawler evidence | sometimes | bounded source, same ICP/pain, not hype-only |
| X/Twitter corroboration | no by itself | lower-confidence corroboration only |
| Negative signal | no | must remain visible and can lower confidence |

## Stale And Missing Artifact Semantics

`telegram-research-agent` should classify Radar state as:

- `current`: Radar week matches Brief week and generated timestamp is within
  expected freshness window.
- `stale`: artifact exists but week/timestamp is older than the Brief.
- `missing`: no artifact was provided or discovered.
- `invalid`: JSON/Markdown violates the contract or cannot parse.

Brief and Hermes behavior:

- `current`: show Radar Gate Card normally.
- `stale`: show candidate, but label stale and avoid new weekly decisions.
- `missing`: show "Radar not available" and continue Brief/Atlas.
- `invalid`: show contract error and do not summarize candidate as valid.

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
- `RADAR-PGI-001`: add Radar-side cross-link and fixture parity checks for this
  contract version without changing runtime gates.
- `RADAR-PGI-003`: run a bounded weekly validation dogfood pass when fresh
  candidate artifacts and credentials/cache fixtures are available.
