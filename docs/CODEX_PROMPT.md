# CODEX_PROMPT - Compact Session Handoff

Version: 5.6
Date: 2026-07-14
State: IRX-1 through IRX-5 and IRX-8 `implemented_and_verified`; IRX-9 is the
next planned implementation task; dogfood is blocked until IRX-14

## Current Product Direction

`telegram-research-agent` is no longer a Telegram digest project. It is becoming
a private Personal AI Decision & Learning Intelligence System:

```text
source observations -> evidence -> claims -> atoms -> threads ->
Brief / Atlas / Hermes / Project Intelligence / Learning Intelligence ->
decisions -> experiments -> outcomes -> feedback/evaluation
```

Active Report V2 roadmap:

```text
docs/intelligence_report_v2_roadmap.md
```

Broader product roadmap: `docs/portfolio_grade_intelligence_roadmap.md`.

Canonical active backlog:

```text
docs/tasks.md
```

Next implementation task:

```text
IRX-9 - Project Intelligence V2
```

## W29 Product Correction

The W29 Brief and Atlas are structurally valid but failed as reader products.
The default run analyzed the newly started W29, missed the valid W28 Radar
artifact, did not expose reaction influence, repeated generic actions, rendered
entity-fragmented threads, and provided no meaningful visual map. The current
detailed Atlas becomes the Knowledge Audit Explorer foundation. IRX-1 fixed the
shared completed-period semantics, IRX-2 added the manifest-bound package,
IRX-3 added bounded auditable reaction personalization, IRX-4 added canonical
curation, IRX-5 added a strict run-bound editorial shadow artifact, and IRX-8
added the shared deterministic offline visualization contract and fixture
gallery. Reader V2 surfaces remain planned, and dogfood has not started.

## Verified Baseline

- Knowledge Atom storage/extraction exists and has focused tests.
- Idea Thread storage/momentum exists and has focused tests.
- Weekly AI visual report/workbook contract exists, but the workbook is now a
  historical/legacy surface rather than the target main product surface.
- Split Weekly Intelligence Brief and Knowledge Atlas artifacts exist. PGI-003
  completed the Brief decision cockpit and Radar gate behavior; PGI-004 added
  Atlas thread navigation and drill-down retrieval items; PGI-005 added
  durable Project/Learning Intelligence projections to Brief/Atlas sidecars,
  rendered HTML, canonical contract projections, and retrieval items.
- IRX-1 adds one immutable shared `ReportingPeriod`, defaults weekly generation
  to the last fully completed ISO week, preserves explicit completed history,
  labels rolling/diagnostic partial modes honestly, and propagates exact
  half-open UTC boundaries through report, Frontier, reaction, opportunity,
  Radar-seed, live/market, and MVP weekly paths.
- IRX-2 adds `weekly_run_manifest.v1`, immutable run-scoped packages, the
  explicit `weekly-intelligence-v2` command, deterministic stage aggregation,
  exact sidecar/checksum identity, same-run `radar_run_binding.v1`, and
  manifest-aware Hermes/PI selection. V1 commands remain available and Radar
  evidence/context-only gates are unchanged.
- IRX-3 adds strict `reaction_visibility_snapshot.v1` and
  `reaction_personalization.v1` validation, exact stored-identity
  post/atom/current-thread attribution, one weak bounded adjacent promotion,
  Brief/Atlas surface receipts, additive PI/retrieval/Obsidian projections, and
  advisory-only repeated-pattern proposals.
- IRX-4 adds the separate durable canonical registry, deterministic proposal
  and lifecycle validation, append-only merge/split/alias history, exclusive
  period-end as-of resolution, stored IRX-3 canonical attribution, and bounded
  additive report/retrieval/Obsidian projections. Mutable compatibility threads
  remain raw audit provenance rather than canonical identity.
- IRX-5 adds the separate opt-in `editorial_intelligence.v1` shadow artifact,
  one strong-route synthesis call over a bounded deterministic package, strict
  Russian/schema/evidence/confidence/reaction/confirmed-feedback/project/Radar
  validation, exact deterministic partial and zero-change projections, an
  immutable run path, and an audit-only model/token/cost/latency receipt. V1
  renderers and the frozen IRX-2 stage policy remain unchanged.
- IRX-8 adds one strict `report_visuals.v1` library for ten deterministic,
  offline, accessible component schemas plus a sanitized standalone fixture
  gallery. It validates exact run/period identity, data states, evidence
  boundaries, safe refs, numeric bounds, honest partial/empty/stale output, and
  collision-free DOM/SVG IDs. V1 renderers do not consume it yet.
- Canonical intelligence sidecar contract `tra-intelligence-contract.v1` is now
  implemented locally for workbook/Brief/Atlas projections with sanitized eval
  fixtures.
- Hermes/PI facade, tools, chat, and intent routing exist as a read-only,
  bounded foundation. PGI-003 added artifact freshness awareness for Brief,
  Atlas, and Radar; product dogfood/evals remain incomplete.
- Feedback intake/action-status helpers now include PGI-002 provenance,
  correction/effect-window metadata, no-feedback unknown semantics, and
  sidecar-backed ranking explanations for top action/read/try items.
- PGI-006 adds deterministic `weekly-intelligence-scorecard.v1` scorecards over
  correctness, relevance, decisions/actions, learning, UX, Radar, and
  operations. Unknown/not-measured metrics stay explicit; false-confidence
  incidents can be recorded without LLM calls.
- Strategy Reviewer exists as advisory-only and must not mutate code/config.
- Market/business context for Radar exists and is `context_only`.
- Sibling `Demand-to-MVP-Radar` repo exists at
  `/srv/openclaw-you/workspace/Demand-to-MVP-Radar`; RVE query planning,
  matched external evidence, adapters, and gate tests are implemented there.
  Live weekly validation still needs dogfood.
- Auxiliary research skills from
  `artwist-polyakov/polyakov-claude-skills` are installed under
  `/root/.codex/skills/`: `reddit-skill`, `x-research`,
  `yandex-search-api`, `yandex-wordstat`, `telegram-channel-parser`, and
  `crawl4ai-seo`. Use them only as gate-safe research collectors; raw skill
  output is context until normalized and matched to a Radar candidate.
- GitHub connector returned no open PRs or open issues for either repo on
  2026-07-10.

## Active Task Graph

Active Report V2 sequence:

```text
IRX-0 -> IRX-1 -> IRX-2 -> IRX-3 -> IRX-4 -> IRX-5
  -> IRX-8 -> IRX-9 -> IRX-10 -> IRX-6 -> IRX-11
  -> IRX-7 -> IRX-12 -> IRX-13 -> IRX-14
```

Parallel Radar sequence:

```text
RADAR-PGI-001 -> RADAR-PGI-002 -> RADAR-PGI-003
```

Do not restart from KIR/HPI/RVE or continue Report V2 work under generic PGI.
Those records are reconciled in `docs/intelligence_report_v2_roadmap.md` and
`docs/tasks.md`.

## IRX-1 Completion

Status: implemented and verified on 2026-07-13.

Implemented:

- immutable typed resolver in `src/output/reporting_period.py` with
  `run_date`, exact UTC `generated_at`, inclusive
  `analysis_period_start`, exclusive `analysis_period_end`, `reporting_week`,
  `period_mode`, and additive `week_label`;
- completed-ISO-week default, completed historical `--week` compatibility,
  separately labelled trailing-seven-day mode, and diagnostic opt-in
  `partial_iso_week`;
- identical half-open boundaries across Brief, Atlas, split context, Frontier,
  marked-post/reaction eligibility, opportunity/Radar seeds, live/market
  projections, MVP weekly plumbing, and existing sidecars;
- bounded historical atoms/source posts plus thread aggregates recomputed from
  bounded evidence;
- inclusive human title dates with generation time shown separately.

Verification:

- required focused suite: 44 tests passed;
- extended affected-surface suite: 38 tests passed;
- feedback semantics recheck: 14 tests passed;
- `py_compile` and `git diff --check`: passed;
- heavy pipelines and the full suite: intentionally not run.

Compatibility and handoff:

- existing command names, filename conventions, V1 contracts, `week_label`,
  scoring, prompts, feedback semantics, database schema, and Radar gates remain
  compatible; weekly default semantics intentionally changed and period flags
  and sidecar fields are additive. No generated artifact files were edited;
- destructive mutation of an existing atom/thread cannot be reconstructed
  perfectly without versioned history; that schema/curation problem is outside
  IRX-1;
- IRX-1 intentionally left persisted manifest/orchestration and same-run Radar
  binding to IRX-2; that historical handoff is now closed.

## IRX-2 Completion

Status: implemented and focused-test verified on 2026-07-13.

Implemented:

- typed `weekly_run_manifest.v1` state machine with immutable identity, frozen
  `irx2_orchestration.v1` policy, exclusive run directories, atomic validated
  writes, sanitized errors, and deterministic terminal aggregation;
- one explicit additive `weekly-intelligence-v2` orchestration command sharing
  the unchanged IRX-1 `ReportingPeriod` across knowledge refresh, reaction sync,
  feedback snapshot, Frontier, Radar, Brief, and Atlas;
- predeclared disabled/non-required placeholders for IRX-4 curation, IRX-5
  editorial intelligence, IRX-7 Audit Explorer separation, and IRX-11
  reader-value gates;
- immutable seed/optional-live-intelligence/market/raw-Radar/binding/Frontier/
  Brief/Atlas paths and SHA-256 checksums, with distinct manifest and Radar run
  IDs and strict cross-artifact period/identity validation;
- one exclusive period-end feedback cutoff shared by the snapshot, readers,
  and Frontier cache identity, with a content fingerprint preventing a
  concurrently replaced Frontier week row from being bound;
- partial/failed/disabled reader disclosure and manifest-aware Hermes/PI reads
  that do not reuse a stale prior candidate or live database state for a bound
  historical package.

Verification and compatibility:

- focused local manifest/orchestrator/report/PI suites and the unchanged sibling
  Radar focused suite passed; live/heavy pipelines and the full suite were not
  run;
- existing V1 commands, week-named diagnostics, sidecar contracts, scoring,
  prompts, feedback semantics, database schema, IRX-1 time behavior, Radar
  evidence logic, and context-only gates remain unchanged;
- no generated report artifacts or sibling Radar code were edited or committed;
- terminal retries create a new run and may set `supersedes_run_id`; the public
  CLI does not expose same-ID resume, while core retry transitions are limited
  to an unfinalized manifest;
- at the IRX-2 boundary, reaction ranking/effect receipt, canonical curation,
  editorial synthesis, reader V2 redesign, and reader-value gates remained
  intentionally open. The IRX-3 handoff is now closed by the completion record
  below; that historical IRX-4 handoff is now closed by its completion record.

## IRX-3 Completion

Status: implemented and focused-test verified on 2026-07-13.

Implemented:

- immutable rich reaction visibility snapshots bound to the same IRX-2 run,
  period, declared path, checksum, coverage, observed-post count, and event
  count; only a complete verified current snapshot can create a fresh boost;
- equal positive semantics for every operator-visible emoji, deduplicated once
  per post; aggregate reactions are ignored and absence/removal remains unknown;
- exact stored-identity lineage from Telegram channel/message through raw and
  normalized post, period-bounded atom, and `idea_thread_atoms` to a current
  compatibility thread, with opaque provenance refs and explicit nullable
  canonical attribution;
- one weak adjacent promotion only among otherwise equal eligible candidates,
  below evidence/safety/freshness/deduplication gates and confirmed explicit
  feedback, with deterministic selection/rank/linked-only counterfactuals;
- strict additive `reaction_personalization.v1` receipts for the exact Brief
  four-action and Atlas twelve-thread selectors, with cross-surface common
  identity/policy, pre-selection funnel, non-selection attribution, and
  snapshot-lineage validation; selector-dependent results may differ, while
  each receipt's JSON/HTML totals and surface refs must agree internally;
- additive reaction-effect projections for split contexts, retrieval,
  Hermes/PI, Obsidian, and Strategy Reviewer; repeated patterns require three
  completed weeks and four distinct posts and create an unapproved proposal
  only, never an automatic mutation.

Verification and compatibility:

- 145 core reaction/report/feedback/Strategy/split/retrieval/PI tests and 45
  manifest/orchestrator tests passed; `git diff --check` passed; live/heavy
  pipelines and the full suite were intentionally not run;
- standalone/V1 behavior without a bound snapshot, legacy reaction-sync integer
  results, tag aliases, existing sidecar consumers, IRX-1/IRX-2 identities,
  global scoring, prompts, feedback semantics, database schema, and Radar gates
  remain compatible; additions are optional/additive;
- legacy count-only IRX-2 reaction output remains explicitly
  unbound/unavailable, creates no fresh boost, and does not require a rich
  reader receipt;
- no generated report artifact, standing profile/config/project/source setting,
  cross-repository code, or sibling Radar gate was changed;
- Historical handoff: IRX-4 was the next scope and had to add the durable
  canonical registry without changing IRX-3 provenance or reaction semantics;
  that handoff is now closed below.

## IRX-4 Completion

Status: implemented and focused-test verified on 2026-07-13.

Implemented:

- additive canonical current/version, atom/alias history, ancestry, and curator
  decision persistence with stable IDs/slugs and raw provenance preserved;
- atomic incremental create/update/merge/split/stale/operator-correction
  transitions with deterministic rejection of atom loss, ambiguous ownership,
  duplicate active title/membership, alias collisions, cycles, and slug churn;
  curator snapshot/semantic checks share the same writer transaction, and
  merge/update identities are bound to the candidate's exact current owners;
- bounded deterministic grouping and proposal-only strong-model curation, with
  entity/vendor-only merge and model-version-only split explicitly rejected;
- exact historical canonical lifecycle and membership resolution as of the
  exclusive `analysis_period_end`, plus stored stable-slug canonical refs for
  the unchanged IRX-3 resolver;
- bounded additive canonical projections for Brief/Atlas/Frontier, Hermes/PI,
  retrieval, Obsidian, Strategy Reviewer, and sidecars while raw/V1 audit
  projections remain available. Atlas primary canonical input is capped at 12.

Verification and compatibility:

- the exact required compatibility matrix passed 83 tests; canonical
  persistence/curator tests passed 28 tests; an extended affected-surface
  matrix passed 109 tests; focused compilation and `git diff --check` passed;
- no live/expensive pipeline, archive regeneration, or full suite was run;
- no generated artifact, IRX-3 reaction semantic, global evidence score,
  explicit-feedback semantic, IRX-1 period rule, IRX-2 manifest/Radar binding,
  Radar gate, standing configuration, or cross-repository code changed;
- At the IRX-4 boundary, IRX-5 and later work remained planned and were not
  implemented; the subsequent IRX-5 completion is recorded below.

## IRX-5 Completion

Status: `implemented_and_verified` on 2026-07-13.

Implemented:

- separate run-bound `editorial_intelligence.v1` shadow JSON with an exact
  schema, at most three signals, bounded project-action references, explicit
  partial status, and no direct rendering markup;
- one strong synthesis-route call for a full eligible package, with zero calls
  for deterministic preflight partials or exact complete cache hits;
- bounded deterministic inputs tied to the exact run/period, canonical snapshot,
  eligible evidence, reaction receipt, confirmed-feedback classifications,
  project permissions, and same-run Radar authority; raw archive access,
  model-owned ranking/gates, and persistent mutation are prohibited;
- strict Russian string and plain-language validation, exact unpadded refs and
  matrix coverage, evidence-derived confidence ceilings, per-field cautious
  wording, exact reaction/feedback/Radar projections, and rejection of generic,
  deployment, readiness, or unauthorized project narratives;
- exact host-owned deterministic partial and zero-change projections that
  cannot be relabelled complete, plus immutable per-run persistence and a
  host-only prompt/schema/model/input-hash/token/cost/latency/attempt receipt;
- production verification of persisted manifest/Radar identity and checksums,
  reaction identity/completeness, and feedback snapshot count/cutoff before a
  complete release.

Verification and compatibility:

- 67 focused IRX-5 tests, the 49-test required acceptance matrix, and 149
  extended compatibility tests passed; focused compilation and
  `git diff --check` passed;
- Ruff passed on IRX-5-owned files; pre-existing `ai_report` Ruff findings were
  excluded as outside this slice;
- V1 Brief/Atlas generation and delivery remain unchanged and do not consume
  editorial JSON. Shadow generation is explicit opt-in and failure-isolated;
  the frozen disabled/non-required `irx2_orchestration.v1` editorial stage was
  not activated or changed;
- no live or expensive LLM call, generated report run, archive regeneration,
  cross-repository code change, Radar gate change, visualization implementation,
  V2 renderer, rollout, or dogfood start was performed;
- At the IRX-5 boundary IRX-8 was the next task; its completion is recorded
  below.

## IRX-8 Completion

Status: `implemented_and_verified` on 2026-07-14.

Implemented:

- one stdlib-only shared renderer with exact schemas and deterministic output
  for decision matrix, reaction lineage, Radar gate, project impact, knowledge
  graph, 12-week timeline, source/thread heatmap, evidence maturity, learning
  progression, and evidence badge components;
- accessible semantic HTML and inline SVG, offline CSP, responsive/print styles,
  namespaced IDs, explicit `available`/`empty`/`unavailable`/`stale` states, and
  machine-readable component/render/data/source/role markers;
- strict closed-world validation for run and completed-week identity, bounded
  numbers, safe source references, evidence and decision authority, non-laundered
  host labels, honest zero/unknown semantics, and accessible component-local
  failures, including multiple malformed specs in one standalone document;
- a sanitized ten-component JSON fixture pack and byte-exact standalone HTML
  gallery. The shared API is ready for both future reader surfaces without
  duplicating markup.

Verification and compatibility:

- 23 focused IRX-8 tests and the combined 54-test visualization/V1 compatibility
  matrix passed; Ruff format/check, focused compilation, and
  `git diff --check` passed;
- systematic mutation probes covered 5,324 malformed component variants without
  an uncaught component-render exception; adversarial review also covered URL,
  period/stale, Radar escalation, graph audit-link, document identity, DOM/ARIA,
  and empty/zero boundaries;
- V1 Brief/Atlas renderers, editorial output, the frozen IRX-2 stage policy,
  project computation, Radar gates, cross-repository code, and generated private
  reports remain unchanged. IRX-8 did not claim browser screenshot evidence;
  the documented desktop/mobile regression harness remains IRX-13 scope.
- IRX-9 is the next implementation task.

## PGI-001 Completion

Status: completed locally on 2026-07-10.

Implemented:

- `tra-intelligence-contract.v1` constants, builder, and validator in
  `src/output/ai_report_contract.py`.
- Explicit SourceObservation, EvidenceItem, Claim, KnowledgeAtom, IdeaThread,
  Decision, Experiment, Outcome, and projection-boundary fields in sidecars.
- Weekly Brief and Knowledge Atlas sidecars now include `contract_version`,
  `intelligence_contract`, and rendered HTML meta tags for contract parity.
- Retrieval adds `canonical_claim` and `canonical_evidence` items while legacy
  workbook readers remain compatible.
- Hermes facade strong-signal fallback can read canonical claims when
  `claim_cards` are absent.
- Opportunity seeds and market context seed rows carry
  `tra-radar-intelligence-contract.v1` plus
  `intelligence_contract_version=tra-intelligence-contract.v1`.
- Context-only Radar evidence remains unable to satisfy demand/build gates.
- Sanitized fixtures were added under
  `tests/fixtures/intelligence_contract/`.

Files changed for PGI-001:

- `src/output/ai_report_contract.py`
- `src/output/weekly_intelligence_brief.py`
- `src/output/knowledge_atlas_report.py`
- `src/output/intelligence_retrieval_items.py`
- `src/output/opportunity_seed_export.py`
- `src/output/market_context_lens.py`
- `src/assistant/pi_facade.py`
- `tests/test_ai_report_contract.py`
- `tests/test_split_intelligence_reports.py`
- `tests/test_intelligence_retrieval_items.py`
- `tests/test_opportunity_seed_export.py`
- `tests/fixtures/intelligence_contract/`

Verification passed:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ai_report_contract.py tests/test_split_intelligence_reports.py tests/test_intelligence_retrieval_items.py tests/test_opportunity_seed_export.py
PYTHONPATH=src python3 -m pytest tests/test_ai_visual_report.py tests/test_pi_facade.py tests/test_pi_tools.py
git diff --check
```

Review notes:

- Correctness: unsupported decision-grade claims and context-only gate misuse
  fail contract validation.
- Provenance/evidence safety: decision-grade evidence requires source
  observation refs, verified quote/excerpt, non-weak tier, and non-context-only
  status.
- Sidecar/rendered parity: Brief/Atlas HTML meta tags match sidecar contract
  versions.
- Backward compatibility: old workbook/split fixtures still read through legacy
  readers; new canonical retrieval items are additive.
- Privacy/secrets: fixtures are sanitized; no `.env`, secrets, private
  generated reports, migrations, LLM runs, or full backfills were added.
- Hermes/Radar: Hermes remains read-only; Radar context-only records still do
  not satisfy demand gates.

## PGI-002 Completion

Status: completed locally on 2026-07-10.

Implemented:

- Confirmed feedback events now expose `confirmation_state`, `signal_strength`,
  `feedback_provenance`, `effect_window`, and append-only correction metadata.
- Added correction/retraction/accidental-feedback events against
  `target_type=feedback_event`; prior events are preserved.
- Updated SQLite schema and idempotent migration rebuild for the expanded
  feedback event/target CHECK constraints.
- Pending feedback intakes remain drafts until explicitly confirmed.
- `read` is a weak observation, not a promotion signal; no feedback is
  `unknown`, never negative.
- AI report and Weekly Brief JSON sidecars include `ranking_factors` and
  `why_selected`; rendered HTML copies "Why selected" from sidecar data.
- PI/Hermes facade exposes ranking explanation fields read-only; no mutation
  tools were added.

Files changed for PGI-002:

- `src/db/ai_report_feedback.py`
- `src/db/migrate.py`
- `src/db/schema.sql`
- `src/output/ai_intelligence_report.py`
- `src/output/weekly_intelligence_brief.py`
- `src/output/ai_report_contract.py`
- `src/output/frontier_analysis.py`
- `src/output/strategy_reviewer.py`
- `src/assistant/pi_facade.py`
- `src/assistant/feedback_prompts.py`
- `tests/test_ai_report_feedback.py`
- `tests/test_ai_intelligence_report.py`
- `tests/test_pi_facade.py`
- `tests/test_split_intelligence_reports.py`

Verification passed:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ai_report_feedback.py tests/test_ai_intelligence_report.py tests/test_pi_facade.py tests/test_action_status.py
PYTHONPATH=src python3 -m pytest tests/test_split_intelligence_reports.py tests/test_strategy_reviewer.py
PYTHONPATH=src python3 -m pytest tests/test_pi_tools.py tests/test_pi_chat.py tests/test_intelligence_retrieval_items.py
git diff --check
```

Review notes:

- Correctness: old SQLite feedback CHECK constraints rebuild without losing
  existing events; corrections append and require an existing prior event.
- Provenance/evidence safety: feedback effects include source/provenance and
  future-only effect windows; no already-rendered artifact is rewritten.
- Sidecar/rendered parity: AI report and Brief HTML explanations are backed by
  sidecar `why_selected`/`ranking_factors`.
- Backward compatibility: fields are additive for readers; migration preserves
  existing rows and indexes.
- Privacy/secrets: no `.env`, secrets, private generated artifacts, expensive
  LLM runs, production config changes, or full archive backfills.
- Hermes/Radar: Hermes remains read-only; no Radar gate behavior changed.

## PGI-003 Handoff

Status: completed locally on 2026-07-10.

Implemented:

- Weekly Brief sidecars include `decision_cockpit` and `mvp_radar_gate`.
- The first Brief section renders decision snapshot, top personal changes,
  evidence/trust summary, what to do, ignore/defer, project impact, MVP Radar
  gate, and exact feedback targets.
- MVP Radar gate decisions require matched decision-grade external evidence
  before focused/build allowance; market/business context remains
  `context_only`.
- Missing Radar artifacts do not break Brief/Atlas generation and render an
  explicit warning.
- Hermes/PI facade exposes read-only `get_artifact_status` for current, stale,
  and missing Weekly Brief, Knowledge Atlas, and MVP Radar artifacts.
- Hermes chat planner/fallback can request artifact status and the answer
  prompt distinguishes source-backed facts, interpretation, model background,
  market context, and matched external evidence.
- Radar JSON retrieval normalization preserves validation queries, matched
  external evidence, missing evidence categories, adapter status, decision
  context, and decision-change action fields.

Files changed for PGI-003:

- `src/output/weekly_intelligence_brief.py`
- `src/output/intelligence_retrieval_items.py`
- `src/assistant/pi_facade.py`
- `src/assistant/pi_chat.py`
- `src/assistant/pi_tools.py`
- `src/assistant/pi_prompts.py`
- `tests/test_split_intelligence_reports.py`
- `tests/test_pi_facade.py`
- `tests/test_pi_chat.py`
- `tests/test_pi_tools.py`

Verification passed:

```bash
PYTHONPATH=src python3 -m pytest tests/test_split_intelligence_reports.py tests/test_pi_chat.py tests/test_pi_tools.py tests/test_mvp_weekly_pipeline.py
PYTHONPATH=src python3 -m pytest tests/test_pi_facade.py tests/test_intelligence_retrieval_items.py
```

Review notes:

- Correctness: Brief cockpit sidecar and rendered HTML share the same Radar
  gate DTO; no build/focused decision is allowed without matched external
  evidence.
- Provenance/evidence safety: Radar market/business context is rendered and
  exposed as `context_only`; missing Radar remains an explicit warning.
- Sidecar/rendered parity: first-screen cockpit blocks and exact feedback
  targets are sidecar-backed.
- Backward compatibility: fields are additive; legacy workbook summaries still
  load, and missing split/Radar artifacts return read-only DTOs instead of
  crashing.
- Privacy/secrets: no `.env`, secrets, private generated artifacts, expensive
  LLM runs, production config changes, or full archive backfills.
- Hermes/Radar: Hermes remains read-only and does not run Codex or Radar.

## PGI-004 Handoff

Status: completed locally on 2026-07-10.

Goal: make Knowledge Atlas a navigable cumulative map of understanding with
thread timeline, current understanding, evidence, contradictions, source
diversity, project connections, decisions, open questions, and study-next cues.

Implemented:

- `thread_navigation` sidecar DTO
  (`knowledge_atlas_thread_navigation.v1`) with timeline, current
  understanding, evidence, contradictions, source diversity, maturity,
  momentum-vs-evidence data, project connections, decision projections, open
  questions, study-next items, and original source links.
- Rendered Atlas `Thread Navigation` section with thread index, detail cards,
  Thread Timeline, Evidence Pane, Source Diversity, Project Connections,
  Decisions, Open Questions, Study Next, and Original Source Links.
- `atlas_thread` retrieval items so Hermes/search can drill into Atlas threads
  with source refs, atom IDs, and thread slugs.
- Atlas remains bounded to curated Idea Threads and Knowledge Atoms; no raw
  Telegram mirror, full archive backfill, or decorative graph.

Files changed for PGI-004:

- `src/output/knowledge_atlas_report.py`
- `src/output/intelligence_retrieval_items.py`
- `tests/test_split_intelligence_reports.py`
- `tests/test_intelligence_retrieval_items.py`

Verification passed:

```bash
PYTHONPATH=src python3 -m pytest tests/test_split_intelligence_reports.py tests/test_intelligence_retrieval_items.py
PYTHONPATH=src python3 -m pytest tests/test_ai_report_contract.py tests/test_pi_tools.py tests/test_pi_chat.py tests/test_pi_facade.py
```

Review notes:

- Correctness: Atlas sidecar and rendered HTML now expose the same thread
  navigation concepts.
- Provenance/evidence safety: evidence panes carry atom IDs and source URLs;
  Atlas states it is not raw Telegram firehose.
- Sidecar/rendered parity: test coverage checks both sidecar DTO and rendered
  navigation labels.
- Backward compatibility: fields are additive; existing workbook/split readers
  still load.
- Privacy/secrets: no `.env`, secrets, private generated artifacts, expensive
  LLM runs, production config changes, or full archive backfills.
- Hermes/Radar: Hermes remains read-only; Radar gate behavior unchanged.

## PGI-005 Completion

Status: completed locally on 2026-07-10.

Implemented:

- Additive `project-learning-projection.v1` DTO in
  `src/output/learning_layer.py`.
- Weekly Brief and Knowledge Atlas sidecars/rendered HTML expose Project
  Intelligence fields: external signals, confirmed implications, weak watches,
  rejected overlaps, tiny PR ideas, stale decisions, research debt, and
  repeated themes without action.
- Learning Intelligence distinguishes `read`, `understood`, `explained`,
  `reproduced`, `implemented`, `tested`, `project-applied`, `measured`,
  `stale`, and `prerequisite_gap`.
- Canonical sidecars carry additive `project_implications`,
  `learning_objectives`, and experiment/outcome projections derived from
  source-backed action/feedback state.
- Retrieval emits `project_intelligence` and `learning_objective` items.

Review notes:

- Correctness: broad-only `higher` project links are rejected and do not become
  confirmed leads, weak watches, or tiny PR ideas.
- Provenance/evidence safety: confirmed project implications require source
  refs/atom IDs; market/business signals are marked `context_only`.
- Sidecar/rendered parity: Brief and Atlas render the same projection categories
  carried in sidecars.
- Backward compatibility: fields are additive; no DB migration.
- Privacy/secrets: no `.env`, secrets, private generated artifacts, expensive
  LLM runs, production config changes, or full archive backfills.
- Hermes/Radar: Hermes remains read-only; Radar gate behavior unchanged.

Verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ai_report_contract.py tests/test_split_intelligence_reports.py tests/test_action_status.py
PYTHONPATH=src python3 -m pytest tests/test_learning_layer.py tests/test_intelligence_retrieval_items.py
python3 -m py_compile src/output/learning_layer.py src/output/ai_report_contract.py src/output/weekly_intelligence_brief.py src/output/knowledge_atlas_report.py src/output/intelligence_retrieval_items.py
git diff --check
```

## PGI-006 Completion

Status: completed locally on 2026-07-10.

Implemented:

- `weekly-intelligence-scorecard.v1` builder, validator, Markdown/JSON writer,
  and file-based fixture loader in `src/output/dogfood_review.py`.
- Scorecard dimensions: correctness, relevance, decisions/actions, learning,
  UX, Radar, and operations.
- Explicit `unknown_metrics` for unknown/not-measured values; no false zeroes or
  fabricated precision.
- False-confidence incidents as structured scorecard records.
- Sanitized fixture-file path that runs without LLM calls.

Review notes:

- Correctness: scorecard is deterministic over sidecar/dogfood/observation
  inputs and validates all required dimensions.
- Provenance/evidence safety: metric sources point to sidecar paths/fields; no
  generated private reports are committed.
- Sidecar/rendered parity: scorecard consumes Brief/Atlas sidecars and writes
  JSON/Markdown artifacts from the same DTO.
- Backward compatibility: existing dogfood review API remains intact.
- Privacy/secrets: no `.env`, secrets, private generated artifacts, expensive
  LLM runs, production config changes, or full archive backfills.
- Hermes/Radar: Hermes remains read-only; Radar gate behavior unchanged and
  context-only gate violation count remains explicit.

Verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_dogfood_review.py tests/test_ai_report_contract.py
python3 -m py_compile src/output/dogfood_review.py
git diff --check
```

## Executed Codex Prompt - IRX-4

The following prompt was executed unchanged for the IRX-4 implementation task:

```text
You are Codex working in /srv/openclaw-you/workspace/telegram-research-agent.
Mode: IMPLEMENTATION for IRX-4 only.
Implement IRX-4, using these binding docs:
  docs/intelligence_report_v2_roadmap.md
  docs/intelligence_report_v2_contract.md
  docs/weekly_run_manifest.md
  docs/reaction_personalization_contract.md
Do not implement IRX-5 or later work: no editorial-intelligence LLM, V2 information-architecture or visual redesign, project-intelligence redesign, Radar reader redesign, reader-value gates, report-specific feedback redesign, rollout, or dogfood start. Do not change IRX-3 reaction semantics or Radar gates.
Before editing run:
  git status
  git branch
  git log --oneline -20
  git diff --stat
Preserve pre-existing dirty changes. Do not edit or commit generated reports.
Read the current raw Idea Thread storage/membership/lifecycle, historical period bounding, IRX-3 compatibility resolver and provenance, Brief/Atlas/Frontier contexts, retrieval/Obsidian adapters, and focused tests for:
  src/db/idea_threads.py,
  src/output/idea_threads.py,
  src/output/reaction_personalization.py,
  src/output/ai_intelligence_report.py,
  src/output/frontier_analysis.py,
  src/output/intelligence_retrieval_items.py,
  src/output/obsidian_export.py,
  tests/test_idea_threads.py,
  tests/test_ai_intelligence_report.py,
  tests/test_frontier_analysis.py,
  tests/test_intelligence_retrieval_items.py,
  tests/test_obsidian_export.py, and tests/test_reaction_personalization.py.
Add an incremental canonical Idea Thread registry, deterministic lifecycle validator, compatibility/alias projection, and bounded curator proposal flow. Prefer additive persistence and compatibility views; preserve raw threads and memberships as audit provenance. Reuse the IRX-1 ReportingPeriod, IRX-2 run identity, and IRX-3 reaction receipt/provenance unchanged.
Required behavior:
1. Give every canonical thread a stable identity/slug, titles, thesis, lifecycle status, first/last seen, raw-thread aliases, atom/source provenance, merge/split ancestry, and curator version. Never relabel a mutable raw/entity cluster as canonical.
2. Generate deterministic grouping candidates. Same-vendor/entity overlap alone cannot merge; model-version difference alone cannot split. Any strong-model curator output is proposal-only until strict deterministic validation passes.
3. Preserve raw threads, atom memberships, source provenance, and old references. Reject atom loss, ambiguous ownership, duplicate active membership/title, alias collisions, merge/split cycles, and unstable slug churn.
4. Support incremental create/update/merge/split/stale transitions and auditable operator corrections without destructive history rewrite or full regeneration.
5. Resolve historical reports against canonical membership and lifecycle state as of analysis_period_end. Do not infer historical canonical state from only the current raw thread or current alias map.
6. Implement the IRX-3 ThreadResolver canonical side through stored identities. Preserve compatibility/current refs, opaque post/atom provenance, reaction strength, evidence/feedback precedence, counterfactuals, and surface receipts; canonical attribution must not change which reactions are eligible.
7. Feed bounded canonical threads to existing contexts while keeping raw compatibility/audit projections additive. Default Atlas input contains at most 8-12 primary canonical threads.
8. Existing V1 reports, Frontier, Hermes/PI, retrieval, Obsidian, Strategy Reviewer, IRX-2 manifests, and IRX-3 receipts remain compatible. Any DB/schema/sidecar change is additive and migrated deterministically.
Add deterministic tests for Fable/Claude-style fragmentation, false entity-only merges, model-version aliases, stable IDs/slugs, incremental reruns, merge/split provenance, aliases and old refs, lifecycle cycles/collisions, period-end as-of resolution, raw compatibility parity, reaction canonical attribution without ranking-semantic drift, bounded Atlas input, operator correction, and retrieval/Obsidian compatibility.
Do not change global evidence scoring, reaction weights/meaning, prompts outside the bounded curator contract, explicit feedback semantics, IRX-1 period behavior, IRX-2 run/Radar binding, cross-repo code, Radar evidence logic, or Radar gates. Do not run live/expensive pipelines, full archive regeneration, or the full suite.
Run:
  PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
    python3 -m unittest tests.test_idea_threads \
    tests.test_ai_intelligence_report tests.test_frontier_analysis \
    tests.test_intelligence_retrieval_items tests.test_obsidian_export \
    tests.test_reaction_personalization
  git diff --check
  git diff --stat
Report files changed, canonical identity/lifecycle/as-of semantics, compatibility behavior, exact test results, and confirmation that generated artifacts, IRX-3 reaction semantics, Radar gates, and cross-repo code were unchanged. Stop before IRX-5.
```

This exact historical prompt stopped at the IRX-4 boundary as required. IRX-4
is implemented and verified; the subsequent IRX-5 and IRX-8 handoffs are now
closed by the completion records above. IRX-9 is the next planned scope.

## Historical PGI-007 Handoff

Status: superseded as the immediate next task and blocked by IRX-14.

PGI-007 requires a four-week dogfood evidence series from operator/private
weekly runs. Do not fabricate scorecards, thresholds, or outcomes. Generated
private artifacts must remain ignored unless a sanitized sample is explicitly
requested.

Resume only after the IRX-14 Report V2 start gate passes. Do not fabricate
scorecards or use the current W29 reports as Week 1 evidence.

## Non-Negotiable Rules

- Do not run full archive backfill unless a task explicitly scopes it.
- Do not run expensive LLM jobs for ordinary verification.
- Do not implement raw Telegram firehose RAG by default.
- Do not add assistant mutation tools.
- Do not let Hermes run Codex or edit YAML/profile/projects/scoring.
- Do not treat no feedback as negative.
- Do not treat market/business Telegram context as external demand evidence.
- Do not hide Radar missing/stale/evidence-gap states.
- Do not commit private generated reports, raw exports, secrets, or `.env`.

## Key Docs

- `docs/intelligence_report_v2_audit.md`
- `docs/intelligence_report_v2_roadmap.md`
- `docs/intelligence_report_v2_contract.md`
- `docs/weekly_run_manifest.md`
- `docs/reaction_personalization_contract.md`
- `docs/static_visualization_system.md`
- `docs/portfolio_grade_intelligence_roadmap.md`
- `docs/tasks.md`
- `docs/intelligence_evaluation_framework.md`
- `docs/portfolio_evidence_plan.md`
- `docs/mvp_radar_integration_contract.md`
- `docs/mvp_skill_research_sources.md`
- `docs/operator_ai_systems_learning_roadmap.md`
- `docs/operator_workflow.md`
- `docs/hermes_pi_assistant_roadmap.md`
- `docs/ai_knowledge_intelligence_roadmap.md`
- `docs/ai_intelligence_workbook_roadmap.md`
- `docs/mvp_weekly_radar.md`

## Current Repository Caveat

`docs/artifacts/**/manual-quality-eval-*.md` is ignored by `.gitignore`. Treat
manual quality eval files as operator/private review material unless the
operator explicitly asks to sanitize and commit one.
