# Intelligence Report V2 Roadmap

Status: active product-correction roadmap

Queue: `IRX - Intelligence Report Experience And Editorial Quality`

Created: 2026-07-13

Evidence base: `docs/intelligence_report_v2_audit.md`

Product contracts:

- `docs/intelligence_report_v2_contract.md`;
- `docs/weekly_run_manifest.md`;
- `docs/reaction_personalization_contract.md`;
- `docs/static_visualization_system.md`.

This roadmap turns the failed W29 reader experience into implementation-ready
work. It does not claim that Report V2 is implemented or that the current W29
reports are acceptable. Product code, scoring, prompts, database schemas,
renderers, Radar gates, and generated reports are outside the scope of IRX-0.

## 1. Product Goal

Report V2 must convert the existing machine/audit evidence into two separate
reader-facing products:

1. **Weekly Intelligence Brief V2** is a Russian, decision-first operational
   read that explains the last completed week in five to seven minutes. It
   presents at most three important signals, one primary action, a bounded
   project implication, the same-run Radar decision, and an auditable account
   of how reactions and confirmed feedback affected selection.
2. **Knowledge Atlas V2** is a cumulative visual knowledge map. It presents
   canonical idea-level threads, their 12-week development, evidence maturity,
   source contribution, operator interest, and learning progression without
   expanding the audit database by default.

The current detailed Atlas is retained as **Knowledge Audit Explorer**. It owns
raw atoms, internal IDs, complete evidence panes, raw memberships, ranking
diagnostics, and thread-construction debugging. No audit evidence is deleted.

The outcome test is behavioral. After reading the package, the operator should
be able to state, in Russian reader-facing copy:

> Я понял X. Я проверил Y. Я улучшил проект Z. Я решил не делать W.

Visual polish without those outcomes is not success.

## 2. Target User Experience

The Weekly Brief must answer, without requiring the Atlas:

- What is the main conclusion of the completed week?
- What should I act on, study, watch, ignore, or defer?
- What one thing should I do this week?
- Which reactions or confirmed feedback changed the result?
- Which active project may change, and what PR-sized change is justified?
- What does MVP Radar allow or block, and which evidence is missing?
- How confident is the system, and what would change that confidence?

The Atlas must be interpretable in under two minutes at its overview level and
then support bounded exploration. The Audit Explorer remains available under
`Technical details`, not as the main reading path.

Reader-facing examples, headings, caveats, actions, and empty states are
Russian. Internal JSON keys, code identifiers, product names, source titles,
and exact source quotations may retain their original language.

## 3. Product Boundaries And Non-Goals

Report V2 reuses current data. It does not require new channels, external
research skills, vector RAG, raw Telegram RAG, multi-profile Hermes, unrelated
autonomous agents, React, a web server, public SaaS, multi-user UI, decorative
generated images, direct LLM-authored HTML, broad project keyword matching, or
weaker Radar gates.

The system must not automatically mutate operator profile, configuration,
projects, code, or standing preferences. It must not treat reaction absence as
negative feedback. It must not discard audit evidence.

## 4. Target Architecture

```text
shared completed-period resolver
  -> weekly run manifest and immutable stage identity
  -> knowledge / reaction / confirmed-feedback snapshots
  -> canonical Idea Thread registry and completed-period delta
  -> deterministic evidence selection and permission gates
  -> bounded strong-model editorial synthesis (strict cited JSON)
  -> deterministic schema/evidence/Radar validation
  -> shared static visualization components
  -> deterministic Brief V2 / Atlas V2 / Audit Explorer renderers
  -> reader-value quality gates
  -> delivery, Hermes/PI retrieval, Obsidian projection, feedback intake
```

### Layer Separation

**Machine/audit layer** owns atoms, source evidence, internal IDs, ranking
factors, fallback diagnostics, raw memberships, full source panes, model/prompt
metadata, and curator history.

**Reader intelligence layer** owns what changed, why it matters, what the
operator should do or defer, confidence, project implications, Radar status,
personalization effects, and missing evidence.

The editorial model receives a bounded, deterministic evidence package. It
does not ingest the raw Telegram archive, choose uncited claims, weaken Radar
gates, generate HTML, or mutate persistent state. Renderers consume validated
JSON only.

### Versioned Contracts

- `tra-intelligence-contract.v2`: additive intelligence-sidecar contract;
- `weekly_run_manifest.v1`: same-run identity and stage-state contract;
- `editorial_intelligence.v1`: bounded editorial output;
- `split_ai_report.v2`: Brief/Atlas reader-sidecar family;
- existing V1 contracts: compatibility inputs and Audit Explorer projections
  during rollout.

## 5. Reconciliation With Existing Work

IRX is the canonical active product-correction queue. It does not erase the
implementation history or silently duplicate it.

| Existing work | Verified reusable value | IRX disposition |
|---|---|---|
| `KIR` / `KIR-Q` | atoms, thread membership, temporal evidence primitives, evidence cards, feedback/eval plumbing, Obsidian projection | retain as knowledge/evidence foundation; IRX-4 adds a canonical curation layer and IRX-5 adds editorial synthesis rather than rebuilding extraction |
| `PGI-001` / `PGI-002` | canonical sidecar concepts, feedback provenance, explainable deterministic ranking inputs | retain as input contracts; IRX-3 makes reaction influence traceable and IRX-5 consumes the bounded context |
| `PGI-003` | split Brief cockpit, artifact/Radar awareness, Hermes-facing status | treat as V1 structural renderer foundation, not proof of reader value; IRX-2, IRX-6, and IRX-10 correct period/handoff/editorial behavior |
| `PGI-004` | Atlas thread navigation and retrieval item compatibility | preserve as Knowledge Audit Explorer foundation; IRX-7 creates a distinct reader-facing visual Atlas |
| `PGI-005` | project and learning projection helpers | reuse diagnostics and additive projections; IRX-9 replaces generic visible implications with evidence-bound PR-sized actions |
| `PGI-006` | deterministic weekly scorecard and structural checks | retain as baseline; IRX-11 adds reader-value, personalization, visual, and same-run quality dimensions |
| `PGI-007` / `HPI-10` | planned dogfood and post-dogfood decision work | blocked and subsumed by IRX-14 start gates; do not begin the four-week run with known-bad reports |
| `HPI-0..HPI-14` | Hermes/PI facade, bounded SQLite FTS retrieval, feedback strategist, workflow | preserve; add V2 readers/adapters rather than replace Hermes or introduce vector/raw RAG |
| `RQ-*` | historical decision-first and quality lessons | keep as historical structural baseline; IRX-11 is the current reader-value gate contract |
| `RVE-*` / `RADAR-PGI-*` | conservative dossier, source matching, external-evidence gates, context-only separation | preserve as Radar baseline; IRX-2 and IRX-10 bind the real artifact to the same run and translate it for readers |

`context_only` exclusion from Radar candidate ranking is already implemented
and tested in `Demand-to-MVP-Radar`. IRX-10 verifies and preserves that
behavior; it does not reopen the gate logic.

## 6. IRX Registry

| ID | Task | Status | Priority | Direct dependencies |
|---|---|---|---|---|
| IRX-0 | Report V2 audit, roadmap, and product contract | `implemented_documentation_only` | P0 | none |
| IRX-1 | Completed-week reporting semantics | `implemented_and_verified` | P0 | IRX-0 |
| IRX-2 | Weekly run manifest and required Radar artifact contract | `implemented_and_verified` | P0 | IRX-1 |
| IRX-3 | Reaction-to-ranking personalization and effect receipt | `implemented_and_verified` | P0 | IRX-1, IRX-2 |
| IRX-4 | Canonical Idea Thread curation and merge/split lifecycle | `implemented_and_verified` | P0 | IRX-1, IRX-2, IRX-3 |
| IRX-5 | Editorial Intelligence synthesis contract | `implemented_and_verified` | P0 | IRX-1 through IRX-4 |
| IRX-6 | Weekly Intelligence Brief V2 | `planned` | P1 | IRX-2 through IRX-5, IRX-8 through IRX-10 |
| IRX-7 | Knowledge Atlas V2 and Knowledge Audit Explorer separation | `planned` | P2 | IRX-4, IRX-5, IRX-8, IRX-11 |
| IRX-8 | Static visualization component system | `implemented_and_verified` | P1 | IRX-4, IRX-5 |
| IRX-9 | Project Intelligence V2 | `implemented_and_verified` | P1 | IRX-4, IRX-5, IRX-8 |
| IRX-10 | MVP Radar reader contract and context-only hardening | `implemented_and_verified` | P1 | IRX-2, IRX-5, IRX-8 |
| IRX-11 | Reader-value quality gates | `planned` | P1 | IRX-6, IRX-8 and upstream contracts |
| IRX-12 | Report-specific feedback and learning loop | `planned` | P2 | IRX-2, IRX-3, IRX-5 through IRX-7, IRX-10 |
| IRX-13 | Golden fixtures, evaluation dataset, and visual regression | `planned`; scaffolding begins after IRX-1 | P2 | incremental upstream fixtures; finalizes after IRX-6, IRX-7, IRX-11 |
| IRX-14 | Rollout, backward compatibility, and dogfood restart | `blocked` | P2 | IRX-1 through IRX-13 |

## 7. Priority And Dependency Order

The delivery order is intentionally:

### P0 - Correctness And Intelligence Foundation

1. `IRX-0` Report V2 audit, roadmap, and product contract.
2. `IRX-1` Completed-week reporting semantics.
3. `IRX-2` Weekly run manifest and required Radar artifact contract.
4. `IRX-3` Reaction-to-ranking personalization and effect receipt.
5. `IRX-4` Canonical Idea Thread curation and merge/split lifecycle.
6. `IRX-5` Editorial Intelligence synthesis contract.

### P1 - Reader-Facing Product

7. `IRX-8` Static visualization component system.
8. `IRX-9` Project Intelligence V2.
9. `IRX-10` MVP Radar reader contract and context-only hardening.
10. `IRX-6` Weekly Intelligence Brief V2.
11. `IRX-11` Reader-value quality gates.

### P2 - Cumulative Map And Rollout

12. `IRX-7` Knowledge Atlas V2 and Knowledge Audit Explorer separation.
13. `IRX-12` Report-specific feedback and learning loop.
14. `IRX-13` Golden fixtures, evaluation dataset, and visual regression.
15. `IRX-14` Rollout, backward compatibility, and dogfood restart.

IRX-8 precedes IRX-6 because the Brief must be assembled from tested,
accessible, deterministic information components rather than one-off markup.
IRX-9 and IRX-10 precede the final Brief renderer because its visible project
and Radar blocks require stable data contracts.

IRX-13 is delivered in P2 after the V2 surfaces and quality contracts stabilize,
but **fixture scaffolding starts immediately after IRX-1**. Each preceding task
must add its smallest sanitized regression fixture. IRX-13 consolidates those
fixtures, locks structured expectations, and adds visual regression; it must
not become a late attempt to invent test data after implementation.

The requested IRX-3-before-IRX-4 order creates one deliberate integration
checkpoint: IRX-3 builds the post-to-atom-to-current-thread projection, weak
boost, counterfactual trace, and receipt behind a thread-resolution interface.
It must not call current entity clusters canonical. IRX-4 supplies the durable
canonical registry and closes IRX-3's canonical-thread acceptance before IRX-5
may consume the receipt. This preserves the priority order without duplicating
the curator inside personalization.

```text
IRX-0 -> IRX-1 -> IRX-2 -> IRX-3 -> IRX-4 -> IRX-5
                                      |         |
                                      +-------> IRX-8
                                      +-------> IRX-9
IRX-2 + IRX-5 -------------------------------> IRX-10
IRX-2..IRX-5 + IRX-8..IRX-10 ----------------> IRX-6
IRX-6 + IRX-8 --------------------------------> IRX-11
IRX-4 + IRX-5 + IRX-8 + IRX-11 --------------> IRX-7
IRX-2 + IRX-3 + IRX-5..IRX-7 + IRX-10 -------> IRX-12
all incremental fixtures + IRX-6 + IRX-7 + IRX-11 -> IRX-13
IRX-1..IRX-13 --------------------------------> IRX-14
```

## 8. Task Queue

### IRX-0 - Report V2 Audit, Roadmap, And Product Contract

**Status:** `implemented_documentation_only`. **Priority:** P0.

**Problem:** W29 is technically valid but does not help the operator understand,
decide, act, or learn. Existing queues describe valuable infrastructure yet
their completion labels obscure the reader-product failure.

**User impact:** Establishes one honest baseline and prevents implementation
from optimizing CSS or adding features before correcting period, orchestration,
personalization, thread quality, and editorial synthesis.

**Architecture:** Documentation-only product correction. Audit both W29 HTML
files and JSON sidecars, separate audit and reader layers, reconcile earlier
queues, define versioned contracts, and sequence IRX-1 through IRX-14.

**Data contract:** The deliverables are the audit, roadmap, product contract,
run manifest, reaction contract, and optional visualization contract. Each
records status as planned/ready/documentation-only and makes no implementation
claim.

**Dependencies:** None. It is the prerequisite for every other IRX task.

**Likely files:** `docs/intelligence_report_v2_*.md`,
`docs/weekly_run_manifest.md`, `docs/reaction_personalization_contract.md`,
`docs/static_visualization_system.md`, and the canonical index/workflow/backlog
documents.

**Acceptance criteria:**

- W29 Atlas and Brief metrics and concrete failures are documented.
- Period, reaction, Radar, thread-duplication, visualization, and quality-gate
  root causes are explicit.
- IRX-1 through IRX-14 have priorities, dependencies, contracts, likely files,
  acceptance criteria, tests, failure behavior, stop conditions, and rollout
  implications.
- Existing queues are reconciled rather than silently copied.
- IRX-1 was selected as the first implementation task; IRX-0 changed no code.

**Tests and verification commands:**

```bash
git diff --stat
rg "IRX-0|IRX-1|IRX-14|Weekly Brief V2|Knowledge Atlas V2|Knowledge Audit Explorer" docs
rg "completed week|analysis_period|reaction effect|canonical thread|editorial intelligence" docs
git diff --check
```

**Failure states:** Missing artifact metrics, unverified implementation claims,
contradictory next-task guidance, or a queue that omits dependencies and
acceptance criteria keeps IRX-0 incomplete.

**Stop conditions:** Stop if documentation proposes weaker evidence gates,
deletes the Audit Explorer, starts dogfood, or changes product code/generated
artifacts.

**Rollout implications:** Documentation only. Marked PGI-007 dogfood blocked
and made IRX-1 the next implementation task at IRX-0 completion.

### IRX-1 - Completed-Week Reporting Semantics

**Status:** `implemented_and_verified` on 2026-07-13. **Priority:** P0.

**Problem:** A Monday run derives the current ISO label, so the W29 report
analyzed the almost-empty week that had just started. Generation time, report
identity, evidence window, reactions, and Radar seed period are conflated.
Historical runs can also leak future atom/thread state.

**User impact:** The operator sees real completed-week change on Monday and can
trust dates, deltas, reactions, and downstream candidate provenance.

**Architecture:** Add one shared UTC period resolver and immutable
`ReportingPeriod` value. Default scheduled/manual weekly mode resolves the last
completed ISO week as a half-open interval. Explicit completed weeks remain
supported. Trailing-seven-day and current partial-week modes are separate and
honestly labeled. Thread/atom queries honor the upper boundary.

**Data contract:** Additive fields:
`run_date`, `generated_at`, `analysis_period_start`, `analysis_period_end`,
`reporting_week`, and `period_mode`. Retain `week_label` as a migration alias.
Allowed modes begin with `completed_iso_week`, `explicit_iso_week`,
`trailing_seven_days`, and diagnostic `partial_iso_week`.

**Dependencies:** IRX-0.

**Likely files:** new `src/output/reporting_period.py`;
`src/output/ai_intelligence_report.py`;
`src/output/weekly_intelligence_brief.py`;
`src/output/knowledge_atlas_report.py`;
`src/output/split_intelligence_reports.py`;
`src/output/frontier_analysis.py`; `src/output/opportunity_seed_export.py`;
`src/output/mvp_weekly_pipeline.py`; `src/main.py`; focused report/Frontier/Radar
pipeline tests; new `tests/test_reporting_period.py`.

**Acceptance criteria:**

- A run at `2026-07-13T07:02:52Z` defaults to W28 with
  `[2026-07-06T00:00:00Z, 2026-07-13T00:00:00Z)`.
- Human report title shows `6-12 июля 2026`; generation time is separate.
- Changed-thread and reaction selection use identical boundaries.
- Opportunity/Radar seed period and report period align without implementing a
  run manifest yet.
- Explicit completed historical weeks work and exclude future state.
- Sunday/Monday, ISO year-boundary, explicit-week, rolling, and diagnostic
  partial-period behavior is tested.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_reporting_period \
  tests.test_ai_intelligence_report tests.test_frontier_analysis \
  tests.test_split_intelligence_reports tests.test_mvp_weekly_pipeline
git diff --check
```

**Failure states:** Current-week default, mismatched stage windows, ambiguous
rolling labels, future data in historical reports, local-time boundary drift,
or broken explicit `--week` behavior fails the task.

**Stop conditions:** Do not implement IRX-2 orchestration, change scoring,
reaction weights, prompts, schemas, report design, or Radar gates. Stop if the
only solution requires weakening evidence semantics or making time zones
implicit.

**Rollout implications:** Additive V1 fields first; existing artifact paths and
commands remain. This unblocks all same-run and completed-period work.

**Implementation receipt (2026-07-13):** Added the shared immutable
`ReportingPeriod` resolver and propagated exact half-open UTC boundaries through
Brief, Atlas, split context, Frontier, reaction/marked-post selection,
opportunity/Radar seeds, live/market projections, MVP weekly plumbing, existing
sidecars, and compatible titles. The default is the last fully completed ISO
week; completed explicit history, separately labelled rolling periods, and
diagnostic opt-in partial weeks remain supported. Historical context bounds
atoms/source posts at `analysis_period_end` and derives thread aggregates from
bounded evidence. Existing command names, filename conventions, V1 schemas,
`week_label`, scoring, prompts, feedback semantics, database schema, and Radar
gates remain compatible. Weekly default semantics intentionally changed;
period flags and sidecar fields are additive, and no generated artifact files
were edited. Required focused verification passed 44 tests;
extended affected verification passed 38 tests; the feedback recheck passed 14
tests; `py_compile` and `git diff --check` passed. The full suite and heavy
pipelines were not run. Without versioned atom/thread history, later destructive
mutation of the same record cannot be perfectly reconstructed; that remains
outside IRX-1. IRX-2 manifest/orchestration and same-run Radar binding were
intentionally left open.

### IRX-2 - Weekly Run Manifest And Required Radar Artifact Contract

**Status:** `implemented_and_verified` on 2026-07-13. **Priority:** P0.

**Problem:** Radar and split reports are separate commands that infer identity
from filenames. A valid W28 Radar dossier existed while the W29 Brief reported
it missing and still looked complete.

**User impact:** One command produces a coherent weekly package. Missing,
wrong-period, failed, or intentionally disabled stages are visible instead of
quietly becoming empty reader content.

**Architecture:** One orchestrator creates `weekly_run_manifest.v1`, assigns an
immutable run ID, invokes or binds every stage, validates period/run identity,
records checksums and stage state, and finalizes the package atomically as
complete, partial, or failed.

**Data contract:** Use the full contract in `docs/weekly_run_manifest.md`:
`schema_version`, `run_id`, period fields, stage statuses, knowledge/reaction
snapshots, Frontier reference, market lens, Radar JSON/run/checksum,
Brief/Atlas/Audit paths, feedback snapshot, warnings, failed stages, and
`partial`. Every V2 sidecar repeats run/period/manifest identity.

**Dependencies:** IRX-1.

**Likely files:** `src/output/split_intelligence_reports.py`;
`src/output/mvp_weekly_pipeline.py`;
`src/output/weekly_intelligence_brief.py`; `src/main.py`; systemd/scripts;
new manifest/orchestration module; `tests/test_split_intelligence_reports.py`;
`tests/test_mvp_weekly_pipeline.py`; cross-repository fixture tests.

**Acceptance criteria:**

- One command owns the aligned weekly package and immutable run ID.
- All sidecars expose the same run ID and half-open analysis period.
- The real same-period Radar candidate/status reaches the Brief.
- Expected missing/wrong-run Radar makes the run partial or failed; intentional
  disablement is declared before execution and reader-visible.
- Success, Radar failure, wrong period, intentionally disabled Radar, reaction
  sync failure, generic degraded aggregation, and render failure are tested.
- Manifest writes are atomic and regeneration does not overwrite prior run
  identity.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_split_intelligence_reports \
  tests.test_mvp_weekly_pipeline tests.test_pi_facade
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar && \
  .venv/bin/python -m pytest tests/test_mvp_of_week.py
```

**Failure states:** Filename-only binding, a complete status with a required
failed stage, stale artifact reuse, mutable run IDs, or reader delivery of a
stale previous Brief as current fails the task.

**Stop conditions:** Do not weaken Radar gates, silently make Radar optional,
or break old commands/paths without a compatibility adapter.

**Rollout implications:** Introduces the V2 orchestration path alongside V1
commands. V1 remains inspectable until IRX-14 migration evidence is complete.

**Implementation receipt (2026-07-13):** Added the typed manifest/state-machine
core and explicit `weekly-intelligence-v2` orchestrator. Each invocation creates
an exclusive run-scoped directory, freezes required/disabled policy, propagates
one IRX-1 period, atomically persists validated stage transitions, and finalizes
only quiescent stages. Brief, Atlas, Frontier, opportunity seeds, optional
run-scoped live intelligence, market lens, raw Radar JSON, and
`radar_run_binding.v1` are tied to the same manifest by structured identity,
declared paths, and SHA-256 checksums. Feedback snapshot, readers, and Frontier
share the exclusive period-end cutoff; Frontier cache identity includes that
cutoff and a content fingerprint prevents binding a concurrently replaced week
row. Required Radar
failure, malformed/wrong-period identity, missing/tampered bytes, reaction
failure, render failure, and intentional predeclared Radar disablement remain
explicit and cannot reuse a stale candidate. Hermes/PI treats the newest
manifest candidate as authority and exposes it only after validation; an
invalid newest manifest blocks older-run and V1 fallback.
The focused local manifest/orchestrator/report/PI suites and unchanged sibling
Radar focused suite passed; live/heavy pipelines and the full suite were not
run.

The public CLI intentionally has no same-ID resume option. Terminal retries
create a new run and may set `supersedes_run_id`; only the core transition model
can increment an attempt inside an unfinalized manifest. Existing V1 commands,
week-named compatibility paths, scoring, prompts, feedback semantics, database
schema, and Radar evidence/context-only gates are unchanged. No generated
report artifact or sibling Radar code was edited. At the IRX-2 boundary,
curation, reaction ranking, editorial synthesis, V2 reader redesign, Audit
Explorer separation, and reader-value gates remained owned by later tasks. The
IRX-3 reaction-ranking handoff is closed below, and the IRX-4 completion record
closes canonical curation without entering IRX-5.

### IRX-3 - Reaction-To-Ranking Personalization And Effect Receipt

**Status:** `implemented_and_verified` on 2026-07-13. **Priority:** P0.

**Problem:** Reactions are ingested with useful semantics but marked posts are
loaded separately from report ranking. Neither HTML nor JSON proves whether a
reaction resolved to evidence or affected selection.

**User impact:** The operator can see that marked material mattered, understand
why it did not matter, and trust that temporary curiosity did not become a
permanent preference.

**Architecture:** Build a deterministic projection:
reaction -> source post -> atom -> thread-resolution interface ->
weak selection boost -> selected item -> effect receipt. Preserve confirmed
report feedback as stronger than reaction interest and evidence quality as the
primary gate. Emit consumed and unconsumed paths.

**Data contract:** `reaction_personalization.v1` includes counts for detected reactions,
resolved posts, linked atoms, linked threads, boosted threads, and selected
signals; per-item reason/effect; and unconsumed records with enumerated reasons
such as post missing, outside period, atom absent, canonical link absent, weak
or stale evidence, duplicate signal, or report limit.

**Dependencies:** IRX-1 and IRX-2. IRX-4 later maps compatibility thread IDs to
stable canonical IDs without changing reaction semantics.

**Implemented files:** `src/ingestion/reaction_sync.py`;
`src/output/reaction_personalization.py`;
`src/output/ai_intelligence_report.py`;
`src/output/weekly_intelligence_brief.py`;
`src/output/knowledge_atlas_report.py`; manifest/orchestrator, split, retrieval,
Obsidian, Strategy Reviewer, PI, CLI adapters; and focused tests for those
surfaces.

**Acceptance criteria:**

- Any visible personal reaction is positive implicit interest; raw emoji is
  metadata and no reaction remains unknown.
- A linked reaction wins only an otherwise equal selection; it cannot override
  evidence gates or confirmed explicit feedback.
- Monday completed-week fixtures consume eligible previous-week reactions.
- HTML and JSON expose funnel counts, per-card influence where relevant, and
  bounded unconsumed reasons.
- IRX-3 does not label raw/entity-cluster IDs as canonical. Its acceptance is
  reopened under IRX-4 to prove post -> atom -> stable canonical thread mapping
  before the receipt enters editorial synthesis.
- Repeated patterns can create a Strategy Reviewer proposal only; standing
  profile/config changes require explicit approval.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_reaction_personalization \
  tests.test_reaction_sync tests.test_ai_intelligence_report \
  tests.test_ai_report_feedback tests.test_strategy_reviewer \
  tests.test_split_intelligence_reports \
  tests.test_intelligence_retrieval_items tests.test_pi_facade
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_weekly_run_manifest \
  tests.test_weekly_intelligence_orchestrator
```

**Failure states:** Absence penalty, emoji sentiment scoring, unexplained boost,
reaction dominance over stronger evidence, double consumption, permanent
preference mutation, or receipt/report count mismatch fails the task.

**Stop conditions:** Stop before any automatic standing preference/config
change or any interpretation of no reaction as dislike.

**Implementation receipt (2026-07-13):** A complete, current, checksum- and
identity-validated same-run reaction snapshot is required for any fresh boost.
Every personal emoji has equal positive provenance, is deduplicated to one weak
post-level interest signal, and aggregate/absent reactions do not change
ranking. Stored Telegram -> raw post -> normalized post -> bounded atom ->
current compatibility-thread identity is the only attribution path. Brief and
Atlas classify the same bounded order against their exact four-action and
twelve-thread selectors and emit strict surface receipts whose common identity,
pre-selection funnel, non-selection attribution, snapshot lineage, and policy
must agree. Each receipt's JSON totals must match its own rendered surface;
selector-dependent status, selected counts, counterfactuals, and unconsumed
results may differ. Evidence, safety, freshness, deduplication, and confirmed
explicit feedback remain stronger; the marker can perform at most one adjacent
promotion among otherwise equal eligible items. Repeated interest creates only
an unapproved Strategy Reviewer proposal after three completed weeks and four
distinct posts; no profile/config/prompt/project/source/code mutation is
automatic.

Focused verification passed: 145 tests in the core
reaction/report/feedback/Strategy/split/retrieval/PI matrix and 45 tests in the
manifest/orchestrator matrix. `git diff --check` passed. Live/heavy pipelines
and the full suite were intentionally not run. Existing standalone/V1
commands and sidecars, legacy sync return values and aliases, Hermes/PI,
retrieval, Obsidian, IRX-1/IRX-2 identity, feedback semantics, global scoring,
database schema, prompts, and Radar gates remain compatible through additive
fields/adapters. Legacy count-only IRX-2 reaction output remains explicitly
unbound/unavailable, creates no boost, and does not require a rich reader
receipt. Generated artifacts and sibling Radar code were unchanged.

**Historical IRX-4 handoff:** Current compatibility-thread refs were not
canonical. IRX-4 had to add the durable registry, aliases, merge/split
lifecycle, and historical period-end as-of thread lineage while preserving
IRX-3 post/atom provenance and reaction semantics. The implementation receipt
below closes that handoff.

### IRX-4 - Canonical Idea Thread Curation And Merge/Split Lifecycle

**Status:** `implemented_and_verified` on 2026-07-13. **Priority:** P0.

**Problem:** Existing threads are often normalized entity combinations such as
Fable/Anthropic and Claude/model-version variants rather than stable ideas.
They clutter the Atlas and make reaction/project mappings unstable.

**User impact:** The operator sees a small set of durable theses that can grow,
weaken, merge, split, or become stale while source provenance remains intact.

**Architecture:** Deterministic grouping candidates feed a bounded strong-model
merge/split proposal. Deterministic validation enforces provenance, semantic
separation, lifecycle rules, and stable slugs before writing an incremental
canonical registry. Curator decisions and operator corrections are auditable.

**Data contract:** A canonical record includes `canonical_thread_id`,
`stable_slug`, `title_ru`, `title_en`, `thesis`, `status`, first/last seen,
`merged_from`, `split_from`, atom IDs, evidence maturity, operator interest,
aliases/entities, and `curator_version`. A decision record stores proposal,
evidence, validation result, model/version, and reason.

**Dependencies:** IRX-1, IRX-2, and IRX-3. Consume the reaction projection
through compatibility thread IDs and add canonical aliases without changing
reaction semantics.

**Implemented files:** new `src/db/canonical_idea_threads.py`; new
`src/output/idea_thread_curator.py`; additive DB schema/migration; existing
Frontier/report/retrieval/Obsidian context loaders; and focused canonical,
curator, report, retrieval, Obsidian, and reaction compatibility tests. Raw
`src/db/idea_threads.py` and `src/output/idea_threads.py` semantics remain
unchanged.

**Acceptance criteria:**

- Fable/Claude-style fragmentation fixtures are merged or explicitly justified.
- Default Atlas input contains at most 8-12 primary canonical threads.
- Same-vendor presence alone does not merge; model-version difference alone
  does not split.
- Atom/source provenance and old references survive merge/split.
- Stable slugs, alias lookup, incremental curation, duplicate-title, and
  duplicate-membership checks are tested.
- Operator correction is representable without destructive history rewrite.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_idea_threads \
  tests.test_ai_intelligence_report tests.test_intelligence_retrieval_items \
  tests.test_obsidian_export
```

**Failure states:** Entity-only merge, vendor fragmentation retained without
reason, atom loss, unstable slug churn, cycles in merge/split history, expensive
full regeneration as the only update path, or ambiguous canonical ownership
fails the task.

**Stop conditions:** Do not let the model persist unvalidated lifecycle changes,
erase raw threads, or merge solely on shared entity tokens.

**Rollout implications:** Run canonical curation beside raw threads, publish a
compatibility map, and keep raw memberships in Audit Explorer until retrieval
and Obsidian consumers prove parity.

**Implementation receipt:** The additive registry stores stable identity,
versioned lifecycle state, alias/atom history, source provenance, lineage, and
curator decisions. Deterministic atomic validation supports incremental
create/update/merge/split/stale/operator-correction transitions and rejects
atom loss, ambiguous ownership, active duplicates, alias collisions, cycles,
and slug churn. Candidate freshness/semantic validation and the write share one
writer transaction; merge/update participants must be the candidate's exact
current owners and nested overrides fail closed. Historical reads resolve the
state and memberships recorded as of the exclusive `analysis_period_end`; typed
alias history makes the stored IRX-3 resolver independent of future raw-thread
atoms without changing ranking or receipt semantics. Existing contexts
receive bounded canonical sidecars beside unchanged raw audit projections, with
at most 12 primary Atlas threads. The required 83-test matrix, 28 canonical
persistence/curator tests, and 109 extended affected-surface tests passed;
focused compilation and `git diff --check` passed. Generated artifacts, Radar
gates, cross-repository code, and IRX-5+ work were unchanged.

### IRX-5 - Editorial Intelligence Synthesis Contract

**Status:** `implemented_and_verified` on 2026-07-13. **Priority:** P0.

**Problem:** Deterministic selection exposes database records and repeats
generic fallback actions. There is no bounded editorial layer that turns
evidence into a weekly thesis and explicit act/study/watch/ignore decisions.

**User impact:** The operator receives a concise Russian explanation of no more
than three signals, a concrete action, uncertainty, project/Radar meaning, and
what not to do.

**Architecture:** After deterministic eligibility and ranking, construct a
bounded evidence package and run one strong-model editorial pass. Validate its
strict JSON schema, evidence references, item limits, Radar permissions, and
language before any deterministic rendering. Record prompt/model/version and
provide a visibly partial deterministic fallback.

**Data contract:** `editorial_intelligence.v1` contains run/period identity,
weekly thesis, `act|study|watch|ignore` decision matrix, up to three signals,
evidence refs, confidence, reaction and confirmed-feedback effects, project implications, next action,
`do_not_do`, project actions, MVP summary, visual specs, and feedback targets.

**Dependencies:** IRX-1 through IRX-4.

**Likely files:** new `src/output/editorial_intelligence.py`; new schema/prompt
module; `src/llm/router.py`; `src/llm/client.py`;
`src/output/split_intelligence_reports.py`; focused editorial schema and prompt
tests; `tests/test_ai_report_contract.py`.

**Acceptance criteria:**

- Strict output validates and contains at most three main signals.
- Every source-grounded statement has an eligible evidence reference.
- Reader text is Russian, complex topics have plain explanations, and every
  report includes a bounded `what not to do` decision.
- No generic repeated action survives validation.
- Low evidence forces cautious language; deterministic permission remains
  authoritative for Radar/project actions.
- Model/prompt/schema/version/cost metadata is audit-visible, not reader noise.
- Confirmed feedback that was considered is classified as applied, unchanged,
  or requiring separate code/config work; merely loading it is not called an
  effect.
- Failure fallback is visibly partial and cannot masquerade as full editorial
  intelligence.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_ai_report_contract \
  tests.test_ai_intelligence_report tests.test_split_intelligence_reports
```

**Failure states:** Uncited claim, invented evidence, more than three signals,
direct HTML, invalid enum, permission escalation, English reader narrative,
generic action duplication, or complete status after fallback fails the task.

**Stop conditions:** Stop if the model needs raw archive access, owns evidence
selection/gates, emits HTML, mutates persistent state, or can weaken Radar.

**Rollout implications:** Persist validated editorial JSON as a new artifact.
Run shadow comparison before V2 renderers consume it; V1 renderers remain.

**Implementation receipt:** IRX-5 adds a run-scoped, immutable
`editorial-intelligence.v1.json` shadow artifact and a deterministic bounded
input package over the existing IRX-1 period, IRX-4 canonical projection,
eligible evidence, IRX-3 reaction receipt, confirmed feedback, explicit project
permissions, and same-run Radar permission. The host performs at most one
strong-model call, with an 80,000-character input cap, 6,000-token output cap,
three-signal and two-project-action limits, and a planned cost ceiling recorded
as metadata rather than used to weaken validation. The model emits only the
strict narrative payload; the host validates Russian/plain copy, exact evidence
closure, confidence ceilings, reaction/feedback/Radar text, generic or duplicate
actions, markup absence, and every deterministic permission before attaching
the final generation envelope.

Production generation reloads the persisted weekly manifest, bound reaction
snapshot, feedback cutoff/count, and Radar binding/artifact bytes with exact
run/period identity, containment, schema, and checksum checks. Missing, stale,
partial, mismatched, or tampered authority fails closed to an exact visibly
partial deterministic artifact without a model call. A valid completed period
with no changed eligible candidate instead uses the exact deterministic
zero-change thesis and empty decision matrix. Complete artifacts are reusable
only for the same model and input hash; paths are exclusively created and a
partial or mismatched artifact requires a new `run_id`.

The opt-in split-report integration runs only after both unchanged V1 artifacts
have rendered. Shadow input, model, validation, import, and persistence failures
are recorded by class in `editorial_intelligence_error` and cannot block Brief
or Atlas. No renderer consumes editorial JSON yet, the frozen
`irx2_orchestration.v1` editorial stage remains disabled/non-required, and no
rollout or dogfood was started. The 67-test focused editorial matrix, the exact
49-test required acceptance command, and 149 extended affected-surface tests
passed; focused compilation, Ruff, and `git diff --check` also passed. No live
LLM call, generated report mutation, cross-repository change, or Radar gate
change was made.

### IRX-8 - Static Visualization Component System

**Status:** `implemented_and_verified`. **Priority:** P1.

**Problem:** Current reports contain cards, tables, and CSS bars but no
meaningful graph, heatmap, funnel, decision matrix, evidence distribution, or
Radar gate visualization. One-off renderer markup would drift and be hard to
test.

**User impact:** The operator can scan decisions, evidence maturity, reaction
flow, project impact, and thread change without confusing decoration with
proof.

**Architecture:** Create deterministic standalone HTML components using inline
SVG, semantic HTML, CSS grid/table, and minimal embedded JavaScript only when
necessary. Components accept structured data, render offline, expose accessible
labels/data notes, support empty states and mobile layouts, and are shared by
Brief and Atlas.

**Data contract:** Versioned input/output specs for decision matrix, reaction
funnel, Radar gate progress, project impact table, knowledge graph, thread
timeline/sparkline, source-thread heatmap, evidence maturity distribution,
learning progression, and evidence/confidence badges. Each output declares
component kind/version and source note.

**Dependencies:** IRX-4 and IRX-5.

**Likely files:** new `src/output/report_visuals.py`; optional
`src/output/report_ui.py`; report renderers; new visualization tests; static
HTML fixtures. Existing Archify/fallback patterns in
`src/output/ai_visual_report.py` may be reused selectively.

**Acceptance criteria:**

- Brief and Atlas reuse shared components rather than duplicate markup.
- Components are deterministic, standalone, offline, accessible, and render
  normal and empty states at 1440px and 375px.
- A machine-readable marker lets quality gates count meaningful component kinds.
- Visuals distinguish explanatory structure from evidence and include source
  notes where applicable.
- No React, server, network dependency, decorative image, or layout overlap.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_ai_visual_report \
  tests.test_split_intelligence_reports tests.test_report_quality
# Run the documented Playwright desktop/mobile snapshot command added by IRX-13.
```

**Failure states:** Nondeterministic layout, inaccessible SVG, text overlap,
network dependency, decorative component counted as evidence, blank canvas,
missing empty state, or separate incompatible Brief/Atlas implementations fails
the task.

**Stop conditions:** Do not add React, a server, generated decoration, or a
visual that implies stronger proof than its underlying evidence.

**Rollout implications:** Land component fixtures before reader renderers.
Components are additive and do not alter V1 output until explicitly selected.

**IRX-8 completion receipt (2026-07-14):** Added the stdlib-only shared
`src/output/report_visuals.py` library with strict versioned envelopes and all
ten component schemas, explicit data/render/source/role markers, accessible
semantic HTML and inline SVG, offline CSP, responsive/print styles, safe
source-reference and numeric boundaries, exact completed-week/run identity,
and honest normal/empty/unavailable/stale/failed behavior. Added the sanitized
`visual_components.v1.json` fixture pack and byte-exact standalone HTML gallery
plus 23 focused tests. The combined visualization and unchanged V1
compatibility matrix passed 54 tests; Ruff format/check, focused compilation,
and `git diff --check` passed. V1 renderers are intentionally not wired to the
library, project/Radar computation is unchanged, and browser geometry/snapshot
evidence is not claimed before IRX-13.

### IRX-9 - Project Intelligence V2

**Status:** `implemented_and_verified`. **Priority:** P1.

**Problem:** Current Project Impact copies generic learning actions, names no
repository, and omits affected files, effort, evidence, and acceptance criteria.

**User impact:** The operator gets at most two evidence-backed, PR-sized project
suggestions or an honest statement that no confirmed implication exists.

**Architecture:** Reuse active project descriptors and deterministic project
diagnostics. Apply evidence/thread fit and rejection reasons before the
editorial model may phrase a concrete action. Broad keyword matches remain
weak/rejected context, never confirmed implications.

**Data contract:** Each action contains `project_name`, signal/thread,
`why_this_project`, affected component, suggested change, likely files, effort,
acceptance criteria, risk, confidence, evidence refs, and status
`confirmed|watch|rejected_overlap|learning_only|existing_project_context|no_confirmed_implication`.
Reader copy collapses non-actionable states; audit data preserves their
distinct reasons.

**Dependencies:** IRX-4, IRX-5, and IRX-8.

**Likely files:** `src/config/projects.yaml`;
`src/output/project_signal_diagnostics.py`;
`src/output/project_relevance.py`; `src/output/ai_visual_report.py`;
`src/output/weekly_intelligence_brief.py`;
`tests/test_project_signal_diagnostics.py`;
`tests/test_project_relevance.py`;
`tests/test_project_insights_knowledge.py`.

**Acceptance criteria:**

- Every confirmed action names a configured project, component/change, likely
  files, effort, acceptance criteria, risk, confidence, and evidence refs.
- Weak overlap cannot be promoted; zero implications is valid and explicit.
- No Brief contains more than two project actions.
- Fixtures cover concrete, weak, rejected, learning-only, existing-context,
  and empty results.
- Output is concrete enough to become a bounded Codex task without inventing
  evidence.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_project_signal_diagnostics \
  tests.test_project_relevance tests.test_project_insights_knowledge \
  tests.test_ai_visual_report
```

**Failure states:** Nameless project, missing acceptance criteria/evidence,
keyword-only confirmation, generic copied action, more than two actions, or
fabricated likely files fails the task.

**Stop conditions:** Stop before broad keyword matching, automatic project/code
changes, or an action unsupported by deterministic project permission.

**Rollout implications:** Shadow the V2 projection against current diagnostics;
preserve current projection keys for retrieval compatibility.

**IRX-9 completion receipt (2026-07-14):** Added the separate opt-in
`project_intelligence.v2` immutable run artifact and
`project_action_permissions.v1` host descriptor boundary. A confirmed action
requires an exact configured project permission, exact canonical-thread fit,
the same bounded IRX-5 signal, and decision-grade non-context evidence owned by
that signal; lexical overlap alone cannot grant authority. Output contains no
more than two distinct permission/signal actions with repository, component,
change, configured normalized relative files, effort, Russian acceptance
criteria, risk, confidence, evidence, stable refs, and exact audit/editorial
closure. Weak,
rejected, learning-only, and existing-context states stay audit-only, while an
explicit Russian zero state is valid. Split generation may shadow the artifact
after unchanged V1 readers and pass only revalidated permissions into IRX-5;
project-only execution makes no model call and shadow failures do not block V1
or editorial output. Sanitized pure and split fixtures cover all required
states, unsafe inputs, empty authority, deterministic bounds/cache, and default
integration. The required 41-test matrix and a 140-test extended affected
V1/editorial/retrieval compatibility matrix passed; mutation review exercised
2,650 malformed variants without an uncaught exception. Ruff, focused
compilation, JSON validation, and diff checks passed. Current PGI-005
projection/retrieval keys, V1 renderers, reaction/feedback semantics, Radar
gates, generated artifacts, and cross-repository code were not changed. Reader
activation remains IRX-6.

### IRX-10 - MVP Radar Reader Contract And Context-Only Hardening

**Status:** `implemented_and_verified` on 2026-07-14.
**Priority:** P1.

**Problem:** Radar correctly produced a W28 investigate dossier, but the Brief
looked for W29 by filename and said the artifact was missing. Raw enums and
evidence categories are not translated into a coherent reader decision.

**User impact:** The operator sees the actual candidate, why investigate/reject/
build was chosen, what evidence is missing, what would change the decision, and
what would kill it.

**Architecture:** Preserve Radar's verified candidate/context split and the
immutable IRX-2 JSON binding. Normalize that bound artifact into a bounded
reader projection without changing gates. Deterministic validation compares
run/week, matched evidence, context-only records, and final recommendation.

**Data contract:** Preserve `radar_role`, `context_only`, and
`build_ready_evidence`. Reader projection contains candidate ID/title, dossier
status, matched KIR provenance, matched external evidence, unmatched context,
missing evidence, decision reason, change condition, next validation query,
kill criteria, Radar run ID, and artifact reference.

**Dependencies:** IRX-2, IRX-5, and IRX-8.

**Likely files:** `src/output/mvp_weekly_pipeline.py`;
`src/output/weekly_intelligence_brief.py`;
`src/output/opportunity_seed_export.py`;
`src/output/market_pain_intelligence.py`;
`tests/test_mvp_weekly_pipeline.py`;
`tests/test_opportunity_seed_export.py`; sibling
`demand_mvp_radar/mvp_weekly.py` and `tests/test_mvp_of_week.py` only if
verification exposes a regression.

**Acceptance criteria:**

- Existing tests prove context-only records cannot enter candidate ranking or
  count as external proof; any regression is fixed without weakening gates.
- Same-run Radar JSON is required and actual candidate/status reaches Brief.
- Reader can distinguish matched external proof, KIR provenance, and unmatched
  context.
- Missing/wrong-run Radar produces explicit partial state, not `No candidate`
  fiction.
- Investigate/reject/build explanation, missing evidence, next validation, and
  kill criteria remain consistent with source JSON.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_opportunity_seed_export \
  tests.test_mvp_weekly_pipeline tests.test_split_intelligence_reports
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar && \
  .venv/bin/python -m pytest tests/test_mvp_of_week.py
```

**Failure states:** Context increases candidate score as proof, market lens
satisfies an external gate, wrong-run artifact binds, raw enum contradicts the
reader text, or missing Radar looks complete fails the task.

**Stop conditions:** Stop before weakening Radar gates, reclassifying context
as build-ready evidence, adding new source acquisition, or changing sibling
code without evidence of a regression.

**Rollout implications:** Add V2 reader projection around the stable Radar
contract. Keep V1 Radar artifact readable through an adapter during migration.

**Implementation receipt:** Added strict `mvp_radar_reader.v1` normalization of
the exact manifest-bound seed/raw/binding package. It preserves producer
candidate identity, status, source mix, KIR provenance, matched external proof,
unmatched context, evidence gaps, reason, next validation, change condition,
experiment, and kill criteria while recomputing only authority/parity—not Radar
ranking. `available` and `no_candidate` require exact run/week/period/schema/
artifact identity; missing, invalid, disabled, wrong-run, and legacy inputs are
explicit fail-closed states. KIR freshness mirrors the producer's any-fresh
semantics, and context-only, market, Telegram, X, negative, unsupported, or
unbound records cannot enter gate proof. Brief, canonical exchange, visual,
retrieval, editorial, and Hermes/PI consumers were hardened against replay and
diagnostic recommendation leakage. The required local 47-test matrix and exact
sibling 16-test matrix passed; extended focused matrices, Ruff, compilation,
and diff checks passed. Malformed-input review covered 4,172 loader and 5,824
projection variants. Sibling changes were limited to additive reader fields,
schema identity, and explicit no-evidence nulls; scoring/gates did not change.
No live/dogfood result is claimed.

Final authority review additionally made the succeeded current manifest a
public-validator requirement, removed trust in self-declared strict markers
from canonical, retrieval, and PI paths, and centralized bounded hostile-JSON
handling. The final reader/authority, consumer, and orchestrator overlap
matrices passed 80, 108, and 66 tests respectively.

### IRX-6 - Weekly Intelligence Brief V2

**Status:** `planned`. **Priority:** P1.

**Problem:** The W29 Brief has no weekly thesis, zero changed threads due to the
wrong period, nine copies of one generic action, no concrete project, no Radar
artifact, no reaction receipt, internal IDs/enums, and no meaningful visuals.

**User impact:** A five-to-seven-minute Russian Brief becomes the single weekly
decision surface: understand, act, study, watch, defer, and provide precise
feedback.

**Architecture:** A deterministic renderer consumes only validated manifest,
editorial, reaction, project, Radar, and visual-component contracts. It does not
perform ranking or call the LLM. Technical details are collapsed and linked to
the Audit Explorer.

**Data contract:** `split_ai_report.v2` Brief sidecar contains run/period/status,
one thesis, four-way decision matrix, up to three signals, one primary and up
to two secondary actions, up to two project actions, reaction receipt, one
confirmed-feedback receipt, one Radar decision, visual specs, evidence refs,
and targeted feedback prompts.

**Dependencies:** IRX-2 through IRX-5 and IRX-8 through IRX-10.

**Likely files:** `src/output/weekly_intelligence_brief.py`;
`src/output/split_intelligence_reports.py`; shared UI/visual modules;
`src/output/intelligence_retrieval_items.py`;
`tests/test_split_intelligence_reports.py`;
`tests/test_intelligence_retrieval_items.py`;
`tests/test_pi_facade.py`; report-quality tests.

**Acceptance criteria:**

- Russian reader copy targets 700-900 visible words and is understandable
  without Atlas.
- Header separates completed period, generation time, and complete/partial
  state; technical links are secondary.
- One thesis, four-way decision matrix, at most three signals, reaction funnel,
  confirmed-feedback effect, concrete-or-empty project matrix, same-run Radar
  gate, and targeted feedback are present.
- There is one primary action, at most two secondary actions, and at least one
  clear `не делать / отложить` decision.
- At least three meaningful visual component kinds render when data permits.
- No raw IDs/enums/ranking traces/fallback diagnostics, repeated generic action,
  empty table cells, or unexplained English internal labels are reader-visible.
- First-screen, 1440px, and 375px screenshots pass human review.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_split_intelligence_reports \
  tests.test_intelligence_retrieval_items tests.test_pi_facade \
  tests.test_report_quality
# Run the IRX-13 documented desktop/mobile screenshot assertions.
```

**Failure states:** Wrong period, missing same-run Radar without partial banner,
more than three signals, generic actions, no reaction receipt when reactions
exist, non-Russian narrative, internal IDs, long report, blank first screen, or
renderer-side ranking fails the task.

**Stop conditions:** Do not let the renderer call the model, generate direct LLM
HTML, hide evidence gaps, or trade information value for decoration.

**Rollout implications:** Write explicit V2 paths while retaining V1 Brief
artifacts and retrieval adapters. Do not switch scheduled delivery until IRX-11
passes on golden fixtures.

### IRX-11 - Reader-Value Quality Gates

**Status:** `planned`. **Priority:** P1.

**Problem:** Current gates validate HTML structure and evidence mechanics but
allow a wrong-period, repetitive, English, nonvisual, nonpersonalized report to
pass with no findings.

**User impact:** A delivered report must demonstrate usefulness and honesty,
not merely contain valid markup.

**Architecture:** Extend deterministic quality evaluation into independent
dimensions: structural validity, evidence validity, editorial quality,
personalization quality, visual quality, project usefulness, and Radar
completeness. Gates inspect structured sidecars first and rendered HTML parity
second. Critical defects block delivery or force partial state.

**Data contract:** `report_quality.v2` returns per-dimension status, severity,
machine-readable code, affected item, evidence, reader impact, repair hint, and
overall delivery decision. Visual counts use semantic component markers, not
arbitrary SVG counts.

**Dependencies:** IRX-6 and IRX-8; uses contracts from IRX-1 through IRX-5,
IRX-9, and IRX-10.

**Likely files:** `src/output/report_quality.py`; report renderers;
`tests/test_report_quality.py`; split report tests; new sanitized W29/V2 quality
fixtures.

**Acceptance criteria:**

- Current W29 failure pattern fails or raises critical actionable findings.
- Brief gates cover period, thesis, Radar, reaction receipt, generic/repeated
  actions, named projects, internal IDs, Russian narrative, meaningful visuals,
  blank metrics, `what not to do`, and visible length.
- Atlas gates cover canonical use, duplicate titles/content, primary thread and
  expanded-detail limits, graph/timeline/source/evidence visuals, maturity
  overstatement, and visible length.
- Decorative SVG cannot satisfy visual quality.
- Redesigned fixtures pass and every failure reports a concrete repair target.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_report_quality \
  tests.test_split_intelligence_reports tests.test_ai_report_contract
```

**Failure states:** One aggregate score hides a critical dimension, gates are
based only on tag counts, easy decorative gaming, warnings lack repair context,
or a wrong-period/missing-Radar report passes as complete fails the task.

**Stop conditions:** Do not weaken evidence gates, reward decorative visuals,
or turn subjective editorial preference into an unexplained hard failure.

**Rollout implications:** Run in warn-only mode on V1, blocking mode on V2
golden fixtures, then gate scheduled V2 delivery after threshold review.

### IRX-7 - Knowledge Atlas V2 And Knowledge Audit Explorer Separation

**Status:** `planned`. **Priority:** P2.

**Problem:** The current Atlas is a 5,000-plus-word evidence dump with entity
clusters, repeated claims, internal identifiers, fully expanded evidence, and
no knowledge graph, comparative timeline, heatmap, or maturity view.

**User impact:** The operator gets a fast visual map of durable knowledge and a
separate technical route for atom/evidence inspection.

**Architecture:** Create a new reader renderer over canonical threads and shared
visual components. Preserve/version the existing detailed renderer as
Knowledge Audit Explorer. Atlas uses progressive disclosure; Audit Explorer
owns full raw detail and stable deep links. Retrieval and Obsidian consume an
additive compatibility projection.

**Data contract:** Atlas V2 sidecar contains run/as-of identity, 8-12 primary
canonical threads, typed relations, 12-week series, source-thread contribution,
evidence maturity, operator interest, learning stages, study backlog, and audit
deep links. Audit Explorer retains raw thread/atom memberships, IDs, evidence,
diagnostics, and curator history.

**Dependencies:** IRX-4, IRX-5, IRX-8, and IRX-11.

**Likely files:** `src/output/knowledge_atlas_report.py`; new
`src/output/knowledge_audit_explorer.py` or versioned legacy renderer;
shared visual/UI modules; `src/output/intelligence_retrieval_items.py`;
`src/output/obsidian_export.py`; split orchestration; Atlas/retrieval/Obsidian
tests.

**Acceptance criteria:**

- Overview is interpretable in under two minutes with no more than 1,500
  visible words before expansion and 8-12 primary canonical threads.
- Knowledge graph, 12-week timeline, source-thread heatmap, and evidence
  maturity render when data permits; learning progression and bounded study
  backlog are present.
- Full claims/quotes/atoms/links are collapsed or delegated to Audit Explorer.
- Fable/Claude-style duplicate clutter and repeated visible claims are absent.
- Existing raw audit inspection, stable deep links, Hermes/PI retrieval, and
  Obsidian projection remain available through compatibility adapters.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_split_intelligence_reports \
  tests.test_intelligence_retrieval_items tests.test_obsidian_export \
  tests.test_pi_facade tests.test_report_quality
# Run the IRX-13 Atlas/Audit Explorer desktop/mobile snapshots.
```

**Failure states:** Audit details deleted, raw Telegram mirror remains primary,
more than 12 expanded thread details, duplicate canonical nodes, missing visual
empty states, broken deep links/retrieval, or visible text above the limit fails
the task.

**Stop conditions:** Stop before deleting the current detailed renderer,
breaking retrieval/Obsidian without migration, or turning Atlas into another
interactive database dump.

**Rollout implications:** Generate Atlas V2 and Audit Explorer side by side;
keep V1 path/aliases until consumers and operator links are migrated and tested.

### IRX-12 - Report-Specific Feedback And Learning Loop

**Status:** `planned`. **Priority:** P2.

**Problem:** Feedback is not reliably targetable to Brief, Atlas, Radar,
reaction personalization, project action, or visualization, and the next report
does not clearly say what confirmed feedback changed.

**User impact:** The operator can correct the exact weak surface, report a
completed action/project change, and see a concise receipt next week without
silent preference mutation.

**Architecture:** Extend current voice/text intake and Strategy Reviewer with
surface/section/item targets and a controlled classification vocabulary.
Confirmation gates remain. Editorial input receives confirmed changes; the
reader receipt separates applied, unchanged, code/config-required, and rejected
feedback.

**Data contract:** Additive feedback event fields include report run/period,
surface, section, target ID, classification (`useful`, `wrong_priority`,
`too_shallow`, `too_long`, `confusing_visual`, `missing_visual`,
`duplicate_content`, `action_completed`, `applied_to_project`,
`radar_decision_useful`, `reaction_effect_missing`, `source_trust_correction`,
`desired_report_change`), confirmation,
application status, and reason.

**Dependencies:** IRX-2, IRX-3, IRX-5, IRX-6, IRX-7, and IRX-10.

**Likely files:** `src/db/ai_report_feedback.py`;
`src/output/ai_report_feedback_intake.py`;
`src/output/strategy_reviewer.py`; `src/output/action_status.py`;
`src/bot/handlers.py`; `src/bot/callbacks.py`; assistant feedback prompts;
feedback/strategy/action tests.

**Acceptance criteria:**

- Voice/text feedback targets Brief/Atlas/Radar/reaction/project/visual section.
- Confirmed feedback affects later editorial context and emits an auditable
  application receipt.
- Next report states what changed, remained unchanged, needs code/config work,
  or was not applied and why.
- No feedback remains unknown; persistent changes remain explicitly approved.
- Completed action/project status can be linked to the originating report item.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_ai_report_feedback \
  tests.test_strategy_reviewer tests.test_artifact_feedback \
  tests.test_split_intelligence_reports
```

**Failure states:** Untargeted feedback silently changes ranking, unconfirmed
feedback enters editorial context, no-feedback becomes negative, application
receipt contradicts state, or code/config changes become automatic fails the
task.

**Stop conditions:** Stop before bypassing confirmation or automatically
changing profile, configuration, code, or standing preferences.

**Rollout implications:** Add fields and adapters to existing feedback rows;
preserve old target IDs. Start receipt-only before enabling new editorial use.

### IRX-13 - Golden Fixtures, Evaluation Dataset, And Visual Regression

**Status:** `planned`, with incremental fixture scaffolding required from
IRX-1 onward. **Priority:** P2.

**Problem:** Current tests prove structural behavior but do not reproduce the
W28/W29 product failures or protect period correctness, editorial usefulness,
personalization, canonicalization, Radar consistency, and responsive visuals.

**User impact:** Regressions become observable before a misleading weekly
package reaches the operator.

**Architecture:** Consolidate sanitized minimal fixtures contributed by each
IRX task. Evaluate structured contracts deterministically, add HTML semantic
assertions, and capture stable desktop/mobile screenshots. Keep private raw
Telegram content out of committed fixtures.

**Data contract:** Fixture manifest records scenario, synthetic/sanitized input,
expected period/run, canonical threads, reactions, project/Radar outcome,
quality findings, output schema versions, redaction provenance, and approved
snapshot hashes. Evaluation dimensions match IRX-11.

**Dependencies:** Incrementally every task after IRX-1; final consolidation
depends on IRX-6, IRX-7, and IRX-11.

**Likely files:** new `tests/fixtures/intelligence_report_v2/`; focused unit and
integration tests; screenshot harness/config; fixture README; quality tests.

**Acceptance criteria:**

- Fixtures cover new-week Monday, Sunday/year boundary, previous-week
  reactions, Fable/Claude duplication, missing and real investigate Radar,
  context-only market lens, concrete/no project implication, generic fallback,
  weak evidence, partial/empty period, and desktop/mobile output.
- Current W29 failure pattern is reproducible without private raw content.
- V2 expectations are locked primarily by structured assertions, with bounded
  semantic HTML and visual snapshots.
- Screenshot update procedure, viewport/browser/font stability, redaction, and
  review policy are documented.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_reporting_period tests.test_report_quality \
  tests.test_split_intelligence_reports tests.test_idea_threads \
  tests.test_reaction_sync tests.test_project_signal_diagnostics
# Run the repository-documented Playwright snapshot command at 1440px and 375px.
```

**Failure states:** Private data committed, brittle full-HTML golden files as
the only assertion, snapshots without structured checks, silent baseline
updates, nondeterministic rendering, or missing empty/partial fixtures fails the
task.

**Stop conditions:** Stop before committing full private reports or accepting a
snapshot update that hides an evidence/editorial regression.

**Rollout implications:** Fixtures accumulate from P0; final IRX-13 gate freezes
the release candidate before dogfood begins.

### IRX-14 - Rollout, Backward Compatibility, And Dogfood Restart

**Status:** `blocked` until IRX-1 through IRX-13 acceptance passes.
**Priority:** P2.

**Problem:** The documented four-week dogfood would collect misleading evidence
if it starts with wrong-period, missing-Radar, generic, nonpersonalized reports.
V2 schema/path changes also risk Hermes/PI retrieval and Obsidian projections.

**User impact:** The operator begins dogfood only with a coherent weekly package
and can still inspect all V1 evidence during migration.

**Architecture:** Parallel-generate V1 and V2, compare manifest/sidecar/reader
quality, migrate retrieval and Obsidian through adapters, then switch the one
documented operator command and scheduled delivery. Preserve immutable V1
artifacts and explicit rollback paths.

**Data contract:** Publish final versions and paths for
`tra-intelligence-contract.v2`, `split_ai_report.v2`,
`editorial_intelligence.v1`, and `weekly_run_manifest.v1`; maintain documented
V1 compatibility aliases/adapters and a migration status receipt.

**Dependencies:** IRX-1 through IRX-13.

**Likely files:** `src/main.py`; orchestration/systemd scripts; report output and
retrieval/Obsidian adapters; operator workflow, dogfood plan, README, task queue,
and focused compatibility/health-check tests.

**Acceptance criteria:**

- V1 artifacts remain inspectable; V2 output paths and one operator command are
  explicit.
- Hermes/PI reads V1 and V2 during migration and identifies freshness/run
  status; Obsidian projection has parity or a documented adapter.
- Parallel-run comparison passes period, Radar, reaction, editorial, project,
  visual, cost, and quality gates.
- Voice feedback end-to-end flow is verified.
- Dogfood week 1 starts only when the checklist below passes.
- During dogfood, new feature work stops except blockers and friction fixes.

**Tests and verification commands:**

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_split_intelligence_reports \
  tests.test_intelligence_retrieval_items tests.test_pi_facade \
  tests.test_obsidian_export tests.test_report_quality \
  tests.test_ai_report_feedback
# Run one bounded, explicitly approved parallel weekly package only after P0/P1 gates.
```

**Failure states:** V1 evidence overwritten, retrieval/Obsidian breakage,
ambiguous scheduled command, partial package delivered as complete, excessive
cost/latency, rollback unavailable, or dogfood started before gates fails the
task.

**Stop conditions:** Do not delete old artifacts, break consumers without a
migration, start dogfood before P0 correction, or add non-blocking features
during the four-week run.

**Rollout implications:** This task owns the actual delivery switch and dogfood
restart. Earlier tasks may produce V2 artifacts but may not declare the product
rolled out.

## 9. Rollout Phases

### Phase 1 - Correctness And Editorial Input

Complete IRX-1 through IRX-5: completed-period identity, run manifest/Radar
handoff, reaction receipt, canonical threads, and validated editorial JSON.
Produce shadow artifacts only.

### Phase 2 - Weekly Brief Release Candidate

Complete IRX-8, IRX-9, IRX-10, IRX-6, and IRX-11: shared visuals, project and
Radar projections, Brief V2, and reader-value gates. Keep V1 delivery active
until golden fixtures pass.

### Phase 3 - Atlas, Learning, Evaluation, Migration

Complete IRX-7, IRX-12, IRX-13, and IRX-14: visual Atlas, Audit Explorer split,
targeted feedback, evaluation suite, compatibility migration, and dogfood
restart.

### Dogfood Week 1 Gate

Dogfood does not start until all are true:

- correct completed-week period is visible;
- actual same-run Radar result is included;
- reaction effect receipt is visible;
- Brief has a real weekly thesis;
- actions are non-generic;
- at least one useful visualization is present;
- duplicate primary threads do not dominate Atlas;
- reader-value quality gates pass;
- voice feedback flow is verified.

## 10. Backward Compatibility Strategy

- Never rewrite or delete generated V1 artifacts. V2 uses explicit paths and
  immutable run IDs.
- Preserve current split-report commands during migration; add one manifest
  orchestrator rather than silently changing every call site at once.
- Keep `week_label` as an additive alias while consumers adopt explicit period
  fields.
- Preserve V1 thread IDs/slugs through canonical aliases and merge/split history.
- Retain current detailed Atlas behavior as Knowledge Audit Explorer and keep
  existing `atlas_thread` deep-link/retrieval semantics through an adapter.
- Make Hermes/PI retrieval parse V1 and V2 sidecars and report schema/run status.
- Keep Obsidian projection on a compatibility view until V2 parity is tested.
- Accept the current Radar V1 dossier through a strict adapter; manifest
  identity and the reader projection are additive.
- Use additive database migrations if persistence is necessary; do not rename
  or drop current tables/columns in the first V2 rollout.
- Record schema, prompt, model, curator, renderer, and component versions in
  audit data so regenerated runs remain explainable.

## 11. Risks And Guardrails

| Risk | Guardrail |
|---|---|
| Strong model creates elegant but unsupported narrative | deterministic evidence eligibility; strict schema; evidence refs on every grounded statement; post-generation verifier; partial failure on mismatch |
| Curator merges separate ideas | candidate proposal only; semantic/evidence validation; operator correction; immutable merge/split history |
| Curator preserves vendor fragmentation | Fable/Claude regression fixtures; title/membership duplication gates; bounded primary-thread count; curator justification |
| Reaction boost overwhelms evidence quality | weak bounded boost after evidence gates; confirmed feedback stronger; receipt exposes exact effect |
| Reactions overfit temporary curiosity | no permanent preference from one reaction; decay/period scope; multi-week pattern only creates approval-gated Strategy Reviewer proposal |
| Visual polish hides weak evidence | evidence maturity and source notes; visuals cannot raise confidence; semantic visual-quality gates |
| Brief becomes long again | 700-900 word target, three-signal/action limits, visible-word gate, progressive technical detail |
| Atlas becomes an interactive database dump again | 8-12 primary threads, 1,500-word limit before details, Audit Explorer owns raw data, reader task tests |
| Renderer and editorial schema drift | versioned schema, generated/central validators, renderer contract tests, unknown-field/version failure behavior |
| Radar references wrong run/week | manifest run/period/checksum binding; mismatch forces partial; no filename-only lookup |
| Partial pipeline looks complete | required-stage state machine, visible partial banner, delivery gate, stale-prior-artifact prohibition |
| Project suggestions become generic keyword matching | project descriptors plus deterministic diagnostics; evidence refs and acceptance criteria required; weak/rejected states retained |
| Quality gates are easy to game | independent dimensions, structured-data checks plus HTML parity, semantic component markers, human fixture review |
| Report generation cost grows excessively | one bounded editorial pass; token/input caps; cache by immutable input hash; cost/latency receipt and rollout budget |
| Hermes/PI cannot read V2 sidecars | additive version adapters, dual-version fixtures, explicit unsupported-version response |
| Obsidian projection breaks | compatibility projection, V1/V2 parity test, dual generation until migration approval |

## 12. Global Stop Conditions

Stop and ask the operator before any proposal or implementation that:

- weakens evidence or Radar gates;
- treats reaction absence as negative;
- turns reactions into automatic permanent preferences;
- lets an LLM generate uncited claims or HTML directly;
- makes Radar context-only evidence build-ready;
- makes project implication broad keyword matching;
- deletes the current detailed Atlas/Audit Explorer;
- breaks Hermes/PI retrieval or Obsidian without a migration plan;
- introduces vector/raw RAG, new source skills, React, or a public/multi-user UI;
- starts dogfood before P0 failures and the stated start gate are corrected;
- adds visual decoration without information value;
- automatically changes profile, configuration, projects, or code.

## 13. Unresolved Questions And Default Assumptions

These questions are assigned to their owning tasks and do not reopen completed
IRX-1 through IRX-5 semantics:

1. **V2 path naming:** use explicit versioned directories plus V1 aliases; IRX-14
   freezes exact paths after parallel-run evidence.
2. **Reader display time zone:** store all boundaries in UTC and render
   generated time in the configured operator zone (`Europe/Berlin` today);
   analysis boundaries remain explicit UTC.
3. **Reaction eligibility:** source-post time must be inside the half-open
   analysis period and current personal visibility must be attested by the
   same-run snapshot. Monday may therefore apply a Sunday post from the completed
   week. IRX-3 has frozen these semantics.
4. **Canonical registry and as-of lineage:** IRX-4 froze additive tables and
   compatibility projections, incremental merge/split history, and historical
   period-end membership without destroying raw thread history.
5. **Graph relation vocabulary:** derive only validated relations such as
   supports, contradicts, prerequisite, and related-by-evidence; do not infer
   decorative edges merely to fill the graph.
6. **Editorial model/cost budget:** IRX-5 freezes the existing strong-model
   route, one bounded call, and audit-visible token/cost caps and receipt.
7. **V1 Audit Explorer path:** preserve current links initially; IRX-7/IRX-14
   choose whether the old Atlas path becomes an alias or a separately named
   artifact after consumer inventory.

## 14. Executed Codex Prompt - IRX-4

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

## 15. Suggested Following Task

IRX-1 through IRX-5 and IRX-8 through IRX-10 are implemented and verified.
IRX-6 is the next planned implementation scope. Reader-value gates, Atlas V2,
rollout, and dogfood remain unimplemented and gated by their later tasks.
