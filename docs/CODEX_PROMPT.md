# CODEX_PROMPT - Compact Session Handoff

Version: 6.1
Date: 2026-07-14
State: IRX-1 through IRX-7 and IRX-8 through IRX-11
`implemented_and_verified`; IRX-12 is the next planned implementation task;
dogfood is blocked until IRX-14

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
IRX-12 - Report-Specific Feedback And Learning Loop
```

## W29 Product Correction

The W29 Brief and Atlas are structurally valid but failed as reader products.
The default run analyzed the newly started W29, missed the valid W28 Radar
artifact, did not expose reaction influence, repeated generic actions, rendered
entity-fragmented threads, and provided no meaningful visual map. The current
detailed Atlas becomes the Knowledge Audit Explorer foundation. IRX-1 fixed the
shared completed-period semantics, IRX-2 added the manifest-bound package,
IRX-3 added bounded auditable reaction personalization, IRX-4 added canonical
curation, IRX-5 added a strict run-bound editorial shadow artifact, IRX-8 added
the shared deterministic offline visualization contract and fixture gallery,
and IRX-9 added the exact evidence-bound Project Intelligence V2 shadow. IRX-10
added the strict manifest-bound Radar reader, and IRX-6 added the opt-in Brief
V2 preview. IRX-11 added independent warn-only V1 and blocking V2 reader-value
gates. IRX-7 added the opt-in Knowledge Atlas V2 and versioned Knowledge Audit
Explorer split. Report-specific feedback, visual-regression consolidation,
scheduled V2 delivery, rollout, and dogfood remain unstarted.

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
- IRX-9 adds the separate opt-in `project_intelligence.v2` immutable run
  artifact and `project_action_permissions.v1` host boundary. At most two
  actions can pass exact project, canonical-thread, same-signal,
  decision-grade/non-context evidence, descriptor-copy, and confidence gates;
  weak/rejected/learning/existing states remain audit-only and an explicit
  Russian zero is valid. Its permissions may feed IRX-5 only after rebinding to
  the exact package and descriptors; V1 and retrieval projections are unchanged.
- IRX-10 adds strict `mvp_radar_reader.v1` normalization over the immutable
  same-run seed/raw/binding package. It preserves producer decisions while
  separating KIR provenance, matched external proof, and unmatched context;
  only exact manifest-bound `available` state can authorize a build or focused
  experiment. Missing, invalid, disabled, wrong-run, and legacy states are
  explicit and fail closed across Brief, visual, canonical, retrieval,
  editorial, and Hermes/PI consumers.
- IRX-6 adds the opt-in deterministic `split_ai_report.v2` Weekly Brief preview
  under a separate immutable run path. It assembles exact editorial, reaction,
  project, Radar, and shared-visual contracts into a bounded Russian decision
  surface without model calls, reranking, V1 replacement, or delivery change.
  Strict source-byte, path, package, retrieval, and PI authority checks fail
  closed on forged, wrong-run, incomplete, hostile-JSON, or symlinked input.
- IRX-11 adds the closed `report_quality.v2` evaluator with seven independent
  dimensions and actionable findings rather than one gameable score. It checks
  sidecars before rendered parity, rejects decorative/hidden/forged semantic
  visuals, warns without blocking V1, and blocks invalid opt-in Brief V2
  publication/loading while the frozen manifest stage stays disabled.
- IRX-7 adds the opt-in deterministic `split_ai_report.v2` Knowledge Atlas V2
  package and versioned Knowledge Audit Explorer. Atlas V2 is manifest-bound to
  V1 Brief/V1 Atlas/editorial/reaction/source-catalog bytes, uses exact IRX-8
  visual specs and IRX-11 blocking gates, keeps Audit Explorer technical detail
  separate, and exposes explicit compatibility adapters for Brief navigation,
  retrieval, Obsidian, and Hermes/PI without changing V1 scheduled delivery.
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
- The historical IRX-9 handoff is closed by the completion record below.

## IRX-9 Completion

Status: `implemented_and_verified` on 2026-07-14.

Implemented:

- separate pure `project_intelligence.v2` projection and immutable
  `<output>/<run_id>/project/project-intelligence.v2.json` artifact, with no
  model, network, database, clock, environment, or repository mutation;
- opt-in `project_action_permissions.v1` descriptors containing the configured
  repository, exact canonical refs, host-owned project rationale/component/
  change/files/effort/criteria/risk/priority, and one concrete future Brief V2
  adapter permission for this repository;
- exact confirmation closure over a configured permission, the same bounded
  IRX-5 signal and canonical thread, medium-or-higher confidence ceiling, and
  decision-grade non-context evidence owned by that signal. Legacy/lexical
  overlap cannot grant action authority;
- at most two distinct permission/signal actions, stable deterministic refs,
  Russian explicit-zero and non-actionable audit states, a fail-closed
  32-record diagnostic boundary, strict text/path/ref/period/schema bounds,
  immutable-byte cache reuse, and an authority-bound IRX-5 permission adapter;
- opt-in split shadow generation after unchanged V1 Brief/Atlas construction,
  shared feedback cutoff context, project-only no-LLM behavior, and independent
  project/editorial failure isolation. Non-empty permissions are revalidated
  against the exact preliminary package and loaded descriptors before use.

Verification and compatibility:

- sanitized concrete/weak/rejected/learning/existing/empty fixtures, 17 pure
  contract tests, 7 split integration tests, and the combined required 41-test
  IRX-9 matrix passed. The extended affected V1/editorial/retrieval matrix
  passed 140 tests, and 2,650 malformed mutation variants produced no uncaught
  exception. Ruff format/check, focused compilation, JSON validation, and
  `git diff --check` passed;
- V1 Brief/Atlas output, current PGI-005 projection/retrieval keys, the IRX-5
  model contract, reactions, feedback, Radar scoring/gates, generated private
  artifacts, and cross-repository code remain unchanged. No live/heavy pipeline,
  full suite, V2 reader activation, repository mutation, or dogfood run was
  performed;
- The historical IRX-10 handoff is closed by the completion record below.
  Project reader rendering was owned by IRX-6 and is closed below.

## IRX-10 Completion

Status: `implemented_and_verified` on 2026-07-14.

Implemented:

- strict deterministic `mvp_radar_reader.v1` projection from the exact
  `weekly_run_manifest.v1`, `radar_run_binding.v1`, raw producer JSON, and seed
  export, including run/week/period/schema/status/path/checksum parity;
- explicit `available`, `no_candidate`, `missing`, `invalid`, `disabled`, and
  `unbound_legacy` states with candidate identity, source mix, matching KIR
  provenance, matched external proof, unmatched context, evidence gaps,
  producer reason, actual change condition, next validation, experiment, and
  kill criteria;
- fail-closed proof eligibility: context-only, market, Telegram, X, negative,
  unsupported, malformed, or unbound input cannot satisfy gates. KIR freshness
  uses the producer's any-fresh semantics and bound candidate seed counts;
- manifest-required Brief consumption plus strict canonical exchange, visual,
  retrieval, editorial, and Hermes/PI adapters. Legacy files remain readable
  only as clearly labelled diagnostic context;
- explicit authority handoff prevents self-declared strict markers in a Brief,
  workbook, canonical exchange, or PI section from restoring candidate/proof
  permission. Bounded shared loaders fail closed on oversized or hostile JSON;
- exact Telegram-side stdout/raw producer-result parity and explicit seed
  evidence roles. Evidence-backed sibling fixes add selected reader fields,
  schema identity, and explicit no-evidence nulls without changing scoring or
  gates.

Verification and compatibility:

- the required local command passed 47 tests and the exact sibling command
  passed 16 tests. The final reader/authority matrix passed 80 tests, the
  consumer matrix passed 108 tests, and the orchestrator/required overlap
  matrix passed 66 tests. Ruff, focused compilation, and `git diff --check`
  passed;
- read-only malformed-input review exercised 4,172 public loader variants and
  5,824 projection variants without an uncaught public-boundary exception after
  the final validator fix;
- no live acquisition, expensive model call, generated private artifact,
  archive backfill, database migration, score/gate change, or dogfood result was
  performed or claimed. The historical IRX-6 handoff is closed by the
  completion record below.

## IRX-6 Completion

Status: `implemented_and_verified` on 2026-07-14.

Implemented:

- separate opt-in `split_ai_report.v2` preview package at
  `weekly_intelligence_briefs_v2/<run_id>/`, with a closed source catalog,
  immutable private HTML/JSON, and unchanged V1 generation and delivery;
- deterministic Russian reader DTO over the exact terminal manifest, IRX-5
  editorial order, IRX-3 reaction receipt, IRX-9 confirmed project actions,
  IRX-10 Radar authority, and IRX-8 visuals. It contains one thesis, four-way
  decisions, up to three signals, one primary plus up to two secondary actions,
  one defer decision, targeted feedback, and collapsed technical provenance;
- 827 initially visible words in the rich sanitized fixture, four visual
  components with three meaningful available kinds, explicit completed period,
  generation time, status/partial reasons, and no reader-visible internal IDs,
  enums, paths, raw ranking traces, or fallback diagnostics;
- bounded duplicate-free finite JSON, exact checksum-bound semantic reads,
  canonical manifest/run/source/output identities, no-follow private atomic
  publication, deterministic rebuild/HTML parity, and fail-closed retrieval/PI
  authority for hostile, incomplete, wrong-run, neighbor, legacy, or symlinked
  packages. Exactly one canonical Radar dossier is projected.

Verification and compatibility:

- the exact task-card command passed 95 tests, the primary Brief/visual/V1
  compatibility matrix passed 133 tests, and the upstream editorial/project/
  reaction/Radar/manifest/orchestrator overlap matrix passed 164 tests;
- independent compatibility and security reviews found no blockers; Ruff,
  focused compilation, and `git diff --check` passed;
- no live/expensive model run, production report generation, archive backfill,
  database migration, Radar score/gate change, sibling-repository edit, V1
  delivery switch, screenshot evidence, rollout, or dogfood claim was made.
  At that boundary IRX-11 was next; its completion is recorded below. Browser
  geometry/golden screenshots remain IRX-13 scope.

## IRX-11 Completion

Status: `implemented_and_verified` on 2026-07-14.

Implemented:

- closed deterministic `report_quality.v2` evaluation and validation with
  structural, evidence, editorial, personalization, visual,
  project-usefulness, and Radar-completeness dimensions; findings contain
  stable codes, affected items, bounded evidence, Russian reader impact, and
  repair hints, with no aggregate score;
- sidecar-first Brief checks for completed period/run/partial identity,
  thesis/evidence, bounded distinct actions and defer decisions, reaction and
  feedback receipts, concrete project actions, authoritative Radar, Russian
  reader copy, visible length, blank metrics, and semantic visuals;
- Atlas target checks for bounded canonical primary threads, duplicate
  identities/content/backlog, evidence-maturity authority, Audit Explorer
  separation, visual identity/distribution parity, and visible length;
- exact IRX-8 DOM/marker/data-state parity. Decorative SVG, forged or hidden
  markers, template/comment/disclosure laundering, supporting badges,
  duplicate component kinds, external styles/scripts, wrong-run specs, boolean
  counts, and non-string evidence cannot satisfy meaningful visual/evidence
  gates;
- V1 split evaluation in `warn_only_v1` with one bounded Russian warning and
  unchanged two-document delivery. Brief V2 applies `blocking_v2` before
  immutable publication and again during strict manifest-bound loading.

Verification and compatibility:

- sanitized W29 Brief/Atlas fixtures fail with actionable findings, while the
  rich Brief V2 and 8-thread Atlas target fixtures pass all applicable
  dimensions;
- the exact task-card command passed 64 tests, the focused Brief V2/manifest
  matrix passed 54 tests, and four extended compatibility/security shards
  passed 282 tests; Ruff, focused compilation, fixture JSON validation, and
  `git diff --check` passed;
- frozen IRX-2 stage policy, V1 sidecars/checksums and scheduled selection,
  IRX-3 reaction meaning, IRX-5 editorial authority, Radar gates, sibling code,
  generated private artifacts, screenshots, rollout, and dogfood remained
  unchanged. At that boundary IRX-7 was next; it is now closed below.

## IRX-7 Completion

Status: `implemented_and_verified` on 2026-07-14.

Implemented:

- opt-in immutable `split_ai_report.v2` Knowledge Atlas V2 sidecar and HTML
  with exact manifest/run/reporting-period/as-of identity, 8-12 canonical
  primary threads, typed evidence-backed relations, exact 12-week timeline,
  source-thread matrix, evidence maturity, separated operator interest,
  learning progression, bounded study backlog, IRX-8 visual specs, and Audit
  Explorer technical refs;
- versioned Knowledge Audit Explorer adapter preserving raw/canonical
  memberships, atoms, source quotes/links, aliases, merge/split lineage,
  diagnostics, and stable deep links outside the 1,500-word reader Atlas budget;
- strict shared package-security helpers, canonical no-follow/nonblocking reads,
  private immutable files, exact five-file package checks, source re-read
  closure, deterministic JSON/HTML parity, and hostile path/URL/JSON rejection;
- Brief navigation, split preview, retrieval, Obsidian, and Hermes/PI
  compatibility adapters that only consume an explicitly valid Atlas V2 package
  and preserve V1 summaries/paths/thread refs;
- IRX-11 `blocking_v2` gates before publication and during strict load, with
  frozen V1 warn-only delivery unchanged.

Verification and compatibility:

- dedicated Atlas focused suite passed 18 tests;
- exact consumer/quality task-card matrix passed 124 tests;
- dedicated Atlas/upstream matrix passed 126 tests;
- Ruff, focused `py_compile`, fixture JSON validation, `git diff --check`,
  `git diff --stat`, and status inspection passed;
- private/generated artifacts, frozen IRX-2 stage policy, V1 scheduled
  delivery, IRX-3 reaction semantics, IRX-5 editorial authority, Radar gates,
  sibling code, screenshots, rollout, dogfood, and IRX-12/13/14 remained
  unchanged.

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
is implemented and verified; the subsequent IRX-5, IRX-8, IRX-9, IRX-10,
IRX-6, IRX-11, and IRX-7 handoffs are now closed by the completion records
above. IRX-12 is the next planned scope.

## Executed Codex Prompt - IRX-7

```text
You are Codex working in /srv/openclaw-you/workspace/telegram-research-agent.
Mode: IMPLEMENTATION for IRX-7 only.

Implement IRX-7, using these binding docs:
  docs/intelligence_report_v2_roadmap.md
  docs/intelligence_report_v2_contract.md
  docs/weekly_run_manifest.md
  docs/static_visualization_system.md
  docs/reaction_personalization_contract.md

Do not implement IRX-12, IRX-13, or IRX-14: no report-specific feedback
redesign, screenshot/evaluation-suite consolidation, production alias or
retention migration, scheduled-delivery switch, rollout, or dogfood start. Do
not change IRX-11 gate meanings, IRX-5 editorial selection, IRX-4 canonical
lifecycle semantics, IRX-3 reaction weights/meaning, global evidence scoring,
Radar evidence logic, or Radar gates. Keep the frozen irx2_orchestration.v1
stage policy unchanged: knowledge_audit_explorer and reader_value_gates remain
disabled and non-required there.

Before editing run:
  git status
  git branch
  git log --oneline -20
  git diff --stat

Preserve pre-existing dirty changes. Do not edit or commit generated reports,
private artifacts, sibling-repository changes, secrets, or .env files.

Read the current Atlas/audit foundation, canonical registry and historical
as-of projection, editorial/reaction contracts, shared visuals, reader-value
gates, Brief V2 navigation, manifest/orchestration compatibility, retrieval,
Obsidian, PI, and focused tests for:
  src/output/knowledge_atlas_report.py
  src/db/canonical_idea_threads.py
  src/output/idea_thread_curator.py
  src/output/editorial_intelligence.py
  src/output/reaction_personalization.py
  src/output/report_visuals.py
  src/output/report_quality.py
  src/output/reader_value_quality.py
  src/output/weekly_intelligence_brief_v2.py
  src/output/weekly_run_manifest.py
  src/output/weekly_intelligence_orchestrator.py
  src/output/split_intelligence_reports.py
  src/output/intelligence_retrieval_items.py
  src/output/obsidian_export.py
  src/assistant/pi_facade.py
  tests/test_canonical_idea_threads.py
  tests/test_report_visuals.py
  tests/test_report_quality.py
  tests/test_split_intelligence_reports.py
  tests/test_intelligence_retrieval_items.py
  tests/test_obsidian_export.py
  tests/test_pi_facade.py
  tests/test_weekly_intelligence_brief_v2.py
  tests/test_weekly_run_manifest.py
  tests/test_weekly_intelligence_orchestrator.py

Add a separate opt-in Knowledge Atlas V2 reader package and a clearly
versioned Knowledge Audit Explorer compatibility surface. Prefer a dedicated
Atlas V2 module and an additive Audit Explorer adapter/module over changing the
meaning of the existing V1 artifact. Do not overwrite, delete, silently
relabel, or switch scheduled delivery away from current V1 paths.

Required behavior:

1. Produce a closed split_ai_report.v2 Atlas sidecar with
   surface=knowledge_atlas and exact manifest/run/reporting-period/as-of
   identity. Include 8-12 primary canonical thread IDs, canonical reader
   records, typed relations, an exact 12-week series, source contribution,
   evidence maturity, operator interest, learning progression, a bounded study
   backlog, shared visual specs, and Audit Explorer technical refs.
2. Resolve canonical identity/lifecycle state as of analysis_period_end from
   the durable IRX-4 registry. Preserve stable IDs/slugs, aliases, and
   merge/split provenance. Never promote current raw/entity clusters into
   canonical identity or infer a graph relation from vendor/entity overlap.
3. Consume only validated run/period-bound upstream contracts. Reuse IRX-5
   editorial output, IRX-3 reaction/confirmed-feedback provenance, IRX-8
   visuals, and IRX-11 gates without a model call, hidden reranking, or changed
   authority. Missing, stale, invalid, wrong-run, or incomplete sources must
   produce honest partial/unavailable state or fail closed.
4. Render deterministic standalone Russian HTML with no more than 1,500
   initially visible words and 8-12 primary canonical threads. The first screen
   answers what is growing, weakening/stale, attracting operator attention, and
   lacking evidence. Full evidence, quotes, atoms, memberships, internal IDs,
   raw enums, traces, and curator diagnostics stay collapsed or move to Audit
   Explorer.
5. Render the canonical graph, exact 12-week timeline, source-thread heatmap,
   and evidence-maturity distribution with validated IRX-8 components when
   data permits. Render bounded learning progression from validated fields.
   Preserve honest available/empty/unavailable/stale semantics, accessible
   non-color-only encoding, stable IDs, deterministic bytes, and visible
   source/period limitations. Decorative/hidden/forged visuals cannot count.
6. Require typed evidence-backed graph edges; distinguish timeline zero from
   missing data and preserve merge/split history. Separate independent heatmap
   support from repeated commentary. Derive maturity from authoritative
   evidence basis; self-declared counts cannot grant high maturity.
7. Keep reaction interest, evidence maturity, confirmed feedback, and learning
   stage separate. Current reactions, decayed historical attention, and
   confirmed feedback remain distinguishable. No feedback stays unknown,
   removed reactions are not negative, and reaction alone never proves
   understanding or a learning transition.
8. Bound and explain the study backlog. Reject duplicate canonical items,
   repeated titles/theses/actions, Fable/Claude-style entity fragmentation, and
   near-identical backlog rows from one vendor cluster.
9. Preserve current detailed Atlas behavior as Knowledge Audit Explorer. Keep
   raw/canonical memberships, atoms, source quotes/links, stable deep links,
   aliases, merge/split history, evidence inputs, diagnostics, and full tables.
   Audit Explorer is clearly technical and is not subjected to the 1,500-word
   reader Atlas budget.
10. Add compatibility projections for retrieval, Hermes/PI, Obsidian, and
    Brief navigation. Existing knowledge_atlas_thread_navigation.v1,
    atlas_thread items, V1 summaries/paths, and stable refs keep working. V2
    consumers may select only an explicit valid V2 artifact; invalid V2 never
    becomes authoritative through legacy fallback.
11. Apply IRX-11 blocking_v2 evaluation before immutable Atlas V2 publication
    and again in its strict bound loader. A blocked artifact is not published
    or returned. Keep V1 warn-only behavior unchanged and do not apply reader
    Atlas limits to the technical Audit Explorer.
12. Use bounded duplicate-free finite JSON, exact source-byte/checksum parity,
    canonical run paths, no-follow/symlink-safe reads/publication, private
    immutable files, atomic directory publication, deterministic HTML rebuild
    comparison, and escaped HTML/SVG. Reject hostile JSON/path/URL input,
    wrong-run aliases, neighboring packages, source swaps, and partial writes.
13. Keep Atlas V2 and Audit Explorer opt-in and side by side. Do not activate
    frozen manifest stages, change required/fatal/degrading flags, modify
    scheduled document selection, finalize aliases/retention, or claim rollout.

Add the smallest sanitized Atlas V2/Audit Explorer fixture and deterministic
tests for 8/12/13 primary boundaries; stable canonical/as-of identity;
duplicate nodes/content/backlog; false vendor-only relations; typed edges;
12-week ordering and zero-vs-missing history; source/maturity authority;
reaction versus feedback/learning semantics; honest visual states; Russian
copy/word/disclosure/internal-ID limits; deterministic full parity; blocking
generation/loading; preserved Audit Explorer detail/deep links; V1 delivery,
retrieval, PI, Obsidian, and Brief compatibility; hostile, stale, wrong-run,
source-swap, traversal, and symlink rejection.

Do not create or claim IRX-13 browser geometry, desktop/mobile golden
screenshots, or visual-regression baselines. Do not run live/expensive
pipelines, full archive regeneration, database backfills, production
migrations, or the full suite.

Perform a deep adversarial review after the contract/renderer phase and a deep
compatibility/security review after consumer integration. Fix all in-scope
blockers before documentation or commit.

Run the exact task-card matrix:
  PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
    python3 -m unittest tests.test_split_intelligence_reports \
    tests.test_intelligence_retrieval_items tests.test_obsidian_export \
    tests.test_pi_facade tests.test_report_quality

Run the dedicated Atlas/upstream matrix:
  PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
    python3 -m unittest tests.test_knowledge_atlas_report_v2 \
    tests.test_report_visuals tests.test_canonical_idea_threads \
    tests.test_weekly_intelligence_brief_v2 tests.test_weekly_run_manifest \
    tests.test_weekly_intelligence_orchestrator

Also run focused Ruff, py_compile, fixture JSON validation, git diff --check,
git diff --stat, and inspect git status for generated/unrelated artifacts.

Update the IRX registry, implementation journal, roadmap completion receipt,
and CODEX handoff with exact test counts. Commit IRX-7 separately and push the
current branch.

Report files changed, Atlas V2/Audit Explorer contracts, canonical/as-of and
visual semantics, quality-gate behavior, compatibility/security, exact test
results, commit/push, and confirmation that private artifacts, frozen IRX-2
policy, V1 scheduled delivery, IRX-3 reaction semantics, IRX-5 editorial
authority, Radar gates, cross-repo code, IRX-12/13/14, rollout, and dogfood were
unchanged. Stop before IRX-12.
```

## Exact Next Codex Prompt - IRX-12

```text
You are Codex working in /srv/openclaw-you/workspace/telegram-research-agent.
Mode: IMPLEMENTATION for IRX-12 only.

Implement IRX-12, using these binding docs:
  docs/intelligence_report_v2_roadmap.md
  docs/intelligence_report_v2_contract.md
  docs/weekly_run_manifest.md
  docs/reaction_personalization_contract.md
  docs/static_visualization_system.md
  docs/tasks.md

Start from the committed IRX-7 state. Do not implement IRX-13 or IRX-14: no
golden screenshot/evaluation-suite consolidation, production alias/retention
migration, scheduled-delivery switch, rollout, or dogfood start. Do not change
IRX-3 reaction semantics, IRX-5 editorial authority, IRX-7 Atlas/Audit package
semantics, IRX-10 Radar authority, IRX-11 gate meanings, global evidence
scoring, Radar gates, cross-repo code, secrets, generated private artifacts, or
the frozen irx2_orchestration.v1 stage policy.

Before editing run:
  git status
  git branch
  git log --oneline -20
  git diff --stat

Read the feedback/action-status/Strategy Reviewer surfaces, bot intake,
Brief/Atlas V2 sidecars and quality gates, reaction/editorial contracts,
Project/Radar adapters, and focused tests for:
  src/db/ai_report_feedback.py
  src/output/ai_report_feedback_intake.py
  src/output/strategy_reviewer.py
  src/output/action_status.py
  src/output/split_intelligence_reports.py
  src/output/weekly_intelligence_brief_v2.py
  src/output/knowledge_atlas_report_v2.py
  src/output/reader_value_quality.py
  src/bot/handlers.py
  src/bot/callbacks.py
  tests/test_ai_report_feedback.py
  tests/test_strategy_reviewer.py
  tests/test_artifact_feedback.py
  tests/test_split_intelligence_reports.py

Add report-, surface-, section-, and item-targeted feedback/learning events for
Brief, Atlas, Radar, reaction personalization, project actions, and visuals.
Use a controlled classification vocabulary and confirmation gates. No feedback
remains unknown; unconfirmed feedback must not enter editorial context.
Persistent preference/profile/config/code changes remain explicit approval-only.
Completed action/project status can be linked to the originating report item.

Add an auditable application receipt that separates applied, unchanged,
code/config-required, rejected, and pending states. Later reports must state
what confirmed feedback changed, what stayed unchanged, what needs code/config
work, and why anything was not applied. Preserve old target IDs and existing
feedback rows through additive fields/adapters.

Perform deep review after the contract/intake phase and again after report
integration. Fix all in-scope blockers before documentation or commit.

Run:
  PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
    python3 -m unittest tests.test_ai_report_feedback \
    tests.test_strategy_reviewer tests.test_artifact_feedback \
    tests.test_split_intelligence_reports

Also run focused compatibility tests for any touched Brief/Atlas/retrieval/PI
surfaces, focused Ruff, py_compile, fixture JSON validation if fixtures change,
git diff --check, git diff --stat, and inspect git status.

Update the IRX registry, implementation journal, roadmap completion receipt,
and CODEX handoff with exact test counts. Commit IRX-12 separately and push the
current branch. Stop before IRX-13.
```

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
