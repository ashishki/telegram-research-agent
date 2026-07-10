# Current Backlog

Version: 2.0
Last updated: 2026-07-10
State: canonical active backlog

Canonical roadmap: `docs/portfolio_grade_intelligence_roadmap.md`.

This file is intentionally compact. Historical KIR/HPI/RVE/DFX detail remains
in component roadmaps and git history; active implementation starts from the PGI
task graph below.

## Operating Rules

- One active queue: Portfolio-Grade Intelligence (`PGI`).
- One parallel Radar track: `RADAR-PGI`.
- One next P0 task after the local PGI-001 implementation:
  `PGI-002 - Operator Context, Feedback Provenance And Explainable Ranking`.
- `PGI-001` is implemented locally with focused verification; start PGI-002 only
  as a separate PR-sized slice after reviewing the contract diff.
- Do not run expensive LLM jobs, full archive backfills, migrations, or
  production config changes from backlog grooming.
- Market/business context remains `context_only`.
- No feedback means `unknown`, never negative.
- Hermes is not source of truth and has no hidden mutation tools.

## Current Verified Baseline

| Component | Status |
|---|---|
| Knowledge Atom storage/extraction | `implemented_and_verified` |
| Idea Thread storage/momentum | `implemented_and_verified` |
| Weekly AI visual report/workbook contract | `implemented_and_verified`, `legacy_surface` |
| Weekly Brief + Knowledge Atlas split | `partial` |
| Hermes/PI facade/tools/chat | `implemented_but_not_dogfooded` |
| Feedback intake/action status | `partial` |
| Strategy Reviewer | `implemented_and_verified` advisory-only |
| Market/business Radar context | `implemented_and_verified` as `context_only` |
| Radar RVE contract/adapters in sibling repo | `implemented_and_verified`, `needs_live_validation` |
| Portfolio dogfood evidence | `partial` |

## Next P0 Task

`PGI-002 - Operator Context, Feedback Provenance And Explainable Ranking`

Start here after the PGI-001 contract changes are reviewed. Do not reopen
KIR/HPI/RVE implementation unless the new contract discovers a regression.

## Dependency Graph

```text
PGI-001
  -> PGI-002
  -> PGI-003
  -> PGI-004
  -> PGI-005
  -> PGI-006
  -> PGI-007
  -> PGI-008

RADAR-PGI-001
  -> RADAR-PGI-002
  -> RADAR-PGI-003
```

`RADAR-PGI-*` can run in parallel after `PGI-001` freezes the shared contract
version. `PGI-003` consumes Radar output but must degrade gracefully when Radar
is missing/stale.

## Active Task Cards

### PGI-001 - Canonical Intelligence Contract And Eval Fixtures

- Status: `completed_local`
- Priority: P0
- Owner: `telegram-research-agent`
- Problem: report contracts exist, but Source Observation, Evidence Item,
  Claim, Atom, Thread, Decision, Experiment, Outcome, and projection boundaries
  are not yet one canonical tested contract.
- User outcome: top Brief/Atlas/Hermes items can prove what source/evidence/
  claim they rely on and can declare insufficient evidence.
- Why now: correctness must precede deeper personalization.
- Dependencies: docs baseline in `docs/portfolio_grade_intelligence_roadmap.md`.
- Blocked by: none.
- Files likely touched: `src/output/ai_report_contract.py`,
  `src/output/weekly_intelligence_brief.py`,
  `src/output/knowledge_atlas_report.py`,
  `src/output/intelligence_retrieval_items.py`,
  `tests/test_ai_report_contract.py`,
  `tests/test_split_intelligence_reports.py`, new fixtures under
  `tests/fixtures/intelligence_contract/`.
- Schema impact: sidecar contract version bump or compatibility field; avoid DB
  migrations in first slice unless the code proves they are unavoidable.
- API/contract impact: define `tra-intelligence-contract.v1` and carry
  `tra-radar-intelligence-contract.v1` where Radar exchange is present.
- Migration impact: expected none.
- Test plan: unit tests for contract shape, rendered/sidecar parity,
  quote/provenance gates, temporal delta fixtures, insufficient-evidence cases.
- Eval plan: layers 1-12 and 24 from
  `docs/intelligence_evaluation_framework.md`.
- Acceptance criteria:
  - SourceObservation/EvidenceItem/Claim projections are explicit in JSON
    sidecars or documented compatibility objects.
  - Top claims cannot render as decision-grade without source refs and
    verification state.
  - Contradictory/negative/context-only evidence can be represented without
    being hidden.
  - Temporal delta fixtures distinguish momentum from evidence growth.
  - Brief/Atlas/Hermes retrieval items can read the new contract or gracefully
    handle older fixtures.
  - Radar context-only records remain unable to satisfy demand evidence gates.
- Verification commands:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ai_report_contract.py tests/test_split_intelligence_reports.py tests/test_intelligence_retrieval_items.py tests/test_opportunity_seed_export.py
```

- Metrics: top-claim provenance coverage, verified quote coverage, unsupported
  claim rate, contradiction visibility, sidecar/rendered parity.
- Risks: over-designing classes before fixture pressure; breaking old W28
  fixture readers; adding DB migration too early.
- Stop conditions: any top claim can render without provenance; context-only
  market data changes a recommendation; tests require live LLM calls.
- Estimated size: L.
- Portfolio evidence produced: domain model contract, correctness fixtures,
  first eval baseline.
- Radar impact: `producer`.
- Completion notes:
  - Added `tra-intelligence-contract.v1` as a canonical sidecar projection with
    SourceObservation, EvidenceItem, Claim, KnowledgeAtom, IdeaThread, Decision,
    Experiment, Outcome, and projection-boundary fields.
  - Kept `weekly-ai-intelligence-v1` as the workbook compatibility contract.
  - Weekly Brief and Knowledge Atlas sidecars now include
    `contract_version`, `intelligence_contract`, and HTML meta tags for
    sidecar/rendered parity.
  - Brief Radar exchange and opportunity seeds carry
    `tra-radar-intelligence-contract.v1`; market/business context remains
    `context_only` and cannot satisfy Radar demand gates.
  - Hermes/retrieval can read canonical claim/evidence items while older
    fixtures continue through legacy workbook readers.
  - Added sanitized fixtures under
    `tests/fixtures/intelligence_contract/` for valid, unsupported, and
    context-only Radar gate cases.
  - Verification passed:
    `PYTHONPATH=src python3 -m pytest tests/test_ai_report_contract.py tests/test_split_intelligence_reports.py tests/test_intelligence_retrieval_items.py tests/test_opportunity_seed_export.py`.
  - Additional touched-surface verification passed:
    `PYTHONPATH=src python3 -m pytest tests/test_ai_visual_report.py tests/test_pi_facade.py tests/test_pi_tools.py`.
  - No DB migration, production config change, LLM run, or full archive backfill.

### PGI-002 - Operator Context, Feedback Provenance And Explainable Ranking

- Status: `next_p0`
- Priority: P0
- Owner: `telegram-research-agent`
- Problem: feedback exists, but signal strength, provenance, effect timing,
  corrections, and explicit operator context are incomplete.
- User outcome: each top item explains why it was selected and which feedback
  or context affected it.
- Why now: personalization without provenance creates fragile trust.
- Dependencies: `PGI-001`.
- Blocked by: none after PGI-001 is reviewed; recommended as a separate
  PR-sized slice because it can touch feedback provenance, ranking, sidecars,
  and Hermes summaries.
- Files likely touched: `src/db/ai_report_feedback.py`,
  `src/output/personalize.py`, `src/output/ai_intelligence_report.py`,
  `src/output/weekly_intelligence_brief.py`, `src/assistant/pi_facade.py`,
  `tests/test_ai_report_feedback.py`, `tests/test_ai_intelligence_report.py`,
  `tests/test_pi_facade.py`.
- Schema impact: possible append-only feedback correction/provenance migration;
  versioned operator context sidecar preferred for first slice.
- API/contract impact: ranking factor fields in Brief/Atlas sidecars.
- Migration impact: allowed only with tests and rollback note.
- Test plan: no-feedback unknown, `verify_first` as calibration, correction
  append-only, weak signals below explicit context, factor parity in HTML.
- Eval plan: layers 14, 15, 22, 23.
- Acceptance criteria:
  - Feedback event has source/provenance/effect window.
  - Confirmed feedback is distinguishable from pending drafts.
  - Correction/retraction appends and does not rewrite prior events.
  - Ranking factors are available per top item.
  - HTML "why selected" copy is backed by sidecar data.
- Verification commands:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ai_report_feedback.py tests/test_ai_intelligence_report.py tests/test_pi_facade.py tests/test_action_status.py
```

- Metrics: personalization confidence, wrong-priority rate, feedback effect
  trace completeness, correction count.
- Risks: behavioral signals overpower explicit context; feedback timing is
  misreported for already-generated artifacts.
- Stop conditions: no-feedback downranks a topic; `read` is treated as strong
  preference; Hermes can mutate context.
- Estimated size: L.
- Portfolio evidence produced: explainable personalization audit.
- Radar impact: none.

### PGI-003 - Weekly Decision Cockpit, Hermes Awareness And Radar Gate

- Status: `planned`
- Priority: P0
- Owner: `telegram-research-agent`
- Problem: Brief/Atlas split exists, but the Brief is not yet a complete
  first-screen decision cockpit and Hermes can still be weak around current,
  stale, or split artifacts.
- User outcome: the operator can understand the week, Radar state, and next
  actions in 3-5 minutes, then ask Hermes grounded follow-ups.
- Why now: this is the main product surface and portfolio demo slice.
- Dependencies: `PGI-001`; best after `PGI-002`.
- Blocked by: missing contract/factor sidecar fields.
- Files likely touched: `src/output/weekly_intelligence_brief.py`,
  `src/output/split_intelligence_reports.py`,
  `src/output/intelligence_retrieval_items.py`, `src/assistant/pi_facade.py`,
  `src/assistant/pi_chat.py`, `src/assistant/pi_tools.py`,
  `tests/test_split_intelligence_reports.py`, `tests/test_pi_chat.py`,
  `tests/test_pi_tools.py`.
- Schema impact: Brief sidecar first-screen decision snapshot, artifact
  freshness state, feedback refs, Radar gate contract version.
- API/contract impact: Hermes answer provenance contract and Radar stale/missing
  semantics.
- Migration impact: none expected.
- Test plan: Brief section ordering, bounded length, Radar Gate Card states,
  Hermes current/stale/missing artifact answers, no raw Telegram RAG.
- Eval plan: layers 16, 20, 21, 24, 25.
- Acceptance criteria:
  - First viewport contains decision snapshot, top 3 personal changes,
    evidence/trust summary, what to do, ignore/defer, project impact, MVP Radar
    gate, exact feedback targets.
  - Brief remains short and does not become Atlas.
  - Hermes names current Brief/Atlas artifacts and warns on stale/missing Radar.
  - Hermes distinguishes facts, interpretation, model background, market
    context, and matched external evidence.
  - Missing Radar artifact does not break Brief/Atlas.
- Verification commands:

```bash
PYTHONPATH=src python3 -m pytest tests/test_split_intelligence_reports.py tests/test_pi_chat.py tests/test_pi_tools.py tests/test_mvp_weekly_pipeline.py
```

- Metrics: time to understand, Brief first-screen task success, Hermes grounded
  answer rate, Radar stale/missing incidents.
- Risks: Brief grows too long; Hermes overstates evidence; Radar context looks
  like proof in copy.
- Stop conditions: market context treated as demand evidence; Hermes runs or
  prepares hidden mutations; Brief hides evidence gaps.
- Estimated size: L.
- Portfolio evidence produced: decision cockpit and assistant quality slice.
- Radar impact: `consumer`.

### PGI-004 - Knowledge Atlas V2 Thread Navigation

- Status: `planned`
- Priority: P1
- Owner: `telegram-research-agent`
- Problem: Atlas is a split artifact, but not yet a strong navigable cumulative
  map of understanding.
- User outcome: the operator can find a thread, see temporal evolution,
  evidence, contradictions, source diversity, project links, decisions, and
  open questions.
- Why now: after the Brief is useful, Atlas must support deeper weekly review.
- Dependencies: `PGI-001`, `PGI-003`.
- Blocked by: missing canonical thread/evidence/delta contract.
- Files likely touched: `src/output/knowledge_atlas_report.py`,
  `src/output/split_intelligence_reports.py`,
  `src/output/intelligence_retrieval_items.py`,
  `tests/test_split_intelligence_reports.py`.
- Schema impact: Atlas sidecar thread detail, evidence pane, contradiction view,
  maturity, momentum vs evidence growth.
- API/contract impact: Hermes retrieval items gain Atlas drill-down refs.
- Migration impact: none expected.
- Test plan: Atlas source-find/thread-understanding fixtures, bounded graph
  rendering if any, no unbounded post mirror.
- Eval plan: layers 7-12 and 26.
- Acceptance criteria:
  - Atlas has topic overview, thread timeline, current understanding, change
    since previous period, claims, evidence, contradictions, source diversity,
    maturity, momentum vs evidence, project connections, decisions, open
    questions, study next, and original source links.
  - Relationship graph is bounded and task-specific if used.
  - Atlas does not become a long static HTML wall.
- Verification commands:

```bash
PYTHONPATH=src python3 -m pytest tests/test_split_intelligence_reports.py tests/test_intelligence_retrieval_items.py
```

- Metrics: source-find task success, thread-understanding task success,
  contradiction visibility.
- Risks: decorative UI instead of information architecture; report size grows
  without navigation value.
- Stop conditions: Atlas mirrors raw Telegram firehose; visual graph hides
  evidence rather than revealing it.
- Estimated size: XL.
- Portfolio evidence produced: Atlas v2 screenshot and usability scorecard.
- Radar impact: none.

### PGI-005 - Project And Learning Intelligence Projections

- Status: `planned`
- Priority: P1
- Owner: `telegram-research-agent`
- Problem: project and learning implications exist only as partial sections,
  not durable intelligence projections.
- User outcome: the operator sees which signals affect active repos and which
  skills moved from reading to implementation/tested outcomes.
- Why now: portfolio evidence needs project changes and learning outcomes.
- Dependencies: `PGI-001`, `PGI-002`.
- Blocked by: missing Decision/Experiment/Outcome/LearningObjective contract.
- Files likely touched: `src/output/project_relevance.py`,
  `src/output/weekly_intelligence_brief.py`,
  `src/output/knowledge_atlas_report.py`, `src/output/learning_layer.py`,
  tests for project relevance and split reports.
- Schema impact: ProjectImplication, Decision, Experiment, LearningObjective,
  Outcome projection fields; avoid DB migrations until fixture shape is proven.
- API/contract impact: Hermes read-only tools can expose project/learning state.
- Migration impact: possible future migration, not required in first projection
  slice.
- Test plan: confirmed/watch/learning/rejected tiers, stale decision examples,
  learning stage transitions.
- Eval plan: layers 13, 18, 19.
- Acceptance criteria:
  - Project Intelligence shows external signals, confirmed implications, weak
    watches, rejected overlaps, tiny PR ideas, stale decisions, research debt,
    and repeated themes without action.
  - Learning Intelligence distinguishes read, understood, explained,
    reproduced, implemented, tested, project-applied, measured, stale, and
    prerequisite gap.
  - No broad keyword overlap becomes a confirmed project lead.
- Verification commands:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ai_report_contract.py tests/test_split_intelligence_reports.py tests/test_action_status.py
```

- Metrics: project changes made, learning outcomes, stale decisions reviewed.
- Risks: learning dashboard becomes aspirational text; project cards become
  generic backlog ideas.
- Stop conditions: passive reading counted as mastery; no source refs for
  confirmed project implications.
- Estimated size: XL.
- Portfolio evidence produced: project/learning intelligence sample.
- Radar impact: `consumer` when existing-project overlap is displayed.

### PGI-006 - Evaluation Harness And Weekly Scorecard

- Status: `planned`
- Priority: P1
- Owner: `telegram-research-agent`
- Problem: tests exist, but there is no unified intelligence evaluation harness
  or weekly scorecard tied to product outcomes.
- User outcome: the operator can tell whether the system improved correctness,
  relevance, decisions, learning, UX, Radar honesty, and operations.
- Why now: dogfood claims need measurement before portfolio hardening.
- Dependencies: `PGI-001`; can begin after PR 1.
- Blocked by: no stable contract fixtures.
- Files likely touched: new eval scripts/tests, `docs/intelligence_evaluation_framework.md`,
  possible `src/output/dogfood_review.py` extensions.
- Schema impact: scorecard artifact schema; no DB migration required initially.
- API/contract impact: scorecard JSON/Markdown artifact.
- Migration impact: none.
- Test plan: fixture eval command, scorecard schema validation, no private data
  committed.
- Eval plan: all layers in `docs/intelligence_evaluation_framework.md`.
- Acceptance criteria:
  - Weekly scorecard records correctness, relevance, decisions/actions,
    learning, UX, Radar, and operations.
  - Unknown metrics are explicit, not fabricated.
  - False-confidence incidents can be recorded.
  - Scorecard can run on sanitized fixtures without LLM calls.
- Verification commands:

```bash
PYTHONPATH=src python3 -m pytest tests/test_dogfood_review.py tests/test_ai_report_contract.py
```

- Metrics: scorecard completeness, eval regression count, annotation cost.
- Risks: vanity metrics; false precision before baseline.
- Stop conditions: thresholds invented without data; private reports committed.
- Estimated size: M.
- Portfolio evidence produced: evaluation report foundation.
- Radar impact: `consumer`.

### PGI-007 - Four-Week Dogfood Evidence Series

- Status: `blocked`
- Priority: P1
- Owner: `operator`
- Problem: user value is not proven by code or one artifact.
- User outcome: four stable weeks of evidence that the system improves
  decisions, actions, learning, and information overload.
- Why now: required before portfolio readiness and post-dogfood product claims.
- Dependencies: `PGI-003`, `PGI-006`.
- Blocked by: decision cockpit and scorecard not landed.
- Files likely touched: dogfood scorecard docs/artifacts only; generated private
  raw outputs must remain ignored.
- Schema impact: none unless scorecard schema changes.
- API/contract impact: none.
- Migration impact: none.
- Test plan: scorecard schema and privacy checks.
- Eval plan: weekly scorecard plus manual review.
- Acceptance criteria:
  - Four weekly runs recorded.
  - Decisions/actions/experiments/outcomes captured.
  - At least one rejected/deferred recommendation example.
  - Radar stale/missing/context-only honesty checked.
  - Brief and Atlas timed usability tasks recorded.
- Verification commands:

```bash
rg -n "Weekly Verified Decision Impact|false-confidence|context-only" docs
PYTHONPATH=src python3 -m pytest tests/test_dogfood_review.py
```

- Metrics: Weekly Verified Decision Impact, time to understand, actions
  completed, false-confidence incidents, friction.
- Risks: dogfood artifacts leak private data; weekly run skipped but counted.
- Stop conditions: no current Brief/Atlas; generated private artifact would be
  committed; false-confidence incident unaddressed.
- Estimated size: XL over calendar time.
- Portfolio evidence produced: product evidence gate.
- Radar impact: `consumer`.

### PGI-008 - Portfolio Demo And Case Study Hardening

- Status: `planned`
- Priority: P2
- Owner: `telegram-research-agent`
- Problem: the repo is not yet packaged as a reproducible, sanitized portfolio
  demonstration.
- User outcome: hiring managers can understand architecture, product value,
  evaluation, and failure handling without private data.
- Why now: only after product/eval evidence exists.
- Dependencies: `PGI-006`, `PGI-007`.
- Blocked by: missing dogfood evidence and sanitized fixture dataset.
- Files likely touched: README, docs, sanitized fixtures, screenshots, diagrams.
- Schema impact: none.
- API/contract impact: none.
- Migration impact: none.
- Test plan: no-secret/private-data checks, demo command, link validation.
- Eval plan: portfolio readiness gate in `docs/portfolio_evidence_plan.md`.
- Acceptance criteria:
  - sanitized demo dataset;
  - reproducible local demo;
  - architecture/domain/sequence diagrams;
  - sample Brief and Atlas;
  - evaluation report and failure cases;
  - cost/latency report;
  - 5-minute demo script and case study;
  - public/private data boundary.
- Verification commands:

```bash
git diff --check
rg -n "TELEGRAM_BOT_TOKEN|OPENAI_API_KEY|LLM_API_KEY|private_operator" docs README.md
```

- Metrics: demo setup time, test pass status, portfolio gate status.
- Risks: over-polishing before evidence; private data leakage.
- Stop conditions: no four-week dogfood evidence; sample artifacts not
  sanitized.
- Estimated size: L.
- Portfolio evidence produced: final portfolio package.
- Radar impact: `consumer`.

## Parallel Radar Track

### RADAR-PGI-001 - Cross-Repo Contract Version Alignment

- Status: `planned_parallel`
- Priority: P0 parallel
- Owner: `Demand-to-MVP-Radar`
- Problem: RVE is implemented, but the new portfolio roadmap needs an explicit
  shared contract version and cross-links in both repos.
- User outcome: Telegram Brief/Hermes and Radar Candidate Dossier agree on
  context-only, matched evidence, stale/missing artifact, and decision-change
  semantics.
- Why now: `PGI-001` needs stable producer/consumer fields.
- Dependencies: docs-first contract in `docs/mvp_radar_integration_contract.md`.
- Blocked by: none for docs; runtime fixture changes depend on `PGI-001`.
- Files likely touched: sibling `docs/RADAR_VALIDATION_EVIDENCE.md`,
  sibling `docs/tasks.md`, sibling README/CODEX docs if needed.
- Schema impact: documentation-only unless code already lacks version field.
- API/contract impact: `tra-radar-intelligence-contract.v1`.
- Migration impact: none.
- Test plan: docs contract search and existing Radar tests.
- Eval plan: layer 24 Radar handoff.
- Acceptance criteria:
  - Both repos link to the same contract version.
  - Market/business context is documented as context-only in both repos.
  - Cross-repo ownership is explicit.
- Verification commands:

```bash
rg -n "tra-radar-intelligence-contract.v1|context-only|matched external" docs /srv/openclaw-you/workspace/Demand-to-MVP-Radar/docs
```

- Metrics: contract parity findings.
- Risks: docs imply Radar is product center.
- Stop conditions: any doc says market context can satisfy build gates.
- Estimated size: S.
- Portfolio evidence produced: cross-repo architecture contract.
- Radar impact: `cross-repo`.

### RADAR-PGI-002 - Radar Dossier Fixture Parity

- Status: `planned_parallel`
- Priority: P1 parallel
- Owner: `Demand-to-MVP-Radar`
- Problem: Radar JSON/Markdown/Brief/Hermes parity must stay true as the Brief
  consumes more structured fields.
- User outcome: no contradiction between Radar rendered output and Telegram
  Brief/Hermes summaries.
- Why now: required for `PGI-003`.
- Dependencies: `RADAR-PGI-001`, `PGI-001`.
- Blocked by: shared fixture shape.
- Files likely touched: sibling tests and fixtures, Telegram split report tests.
- Schema impact: only if fixture exposes missing fields.
- API/contract impact: selected candidate repeats key fields.
- Migration impact: none.
- Test plan: cross-repo fixture diff for JSON/Markdown/Brief fields.
- Eval plan: layer 24.
- Acceptance criteria:
  - `dossier_status`, recommendation, confidence, missing evidence, matched
    evidence, adapter status, decision-change action, and context-only markers
    match across JSON/Markdown/Brief fixture.
  - Missing/stale Radar artifact fixture is covered on Telegram side.
- Verification commands:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py tests/test_mvp_report_quality.py tests/test_telegram_research_bridge.py
cd /srv/openclaw-you/workspace/telegram-research-agent
PYTHONPATH=src python3 -m pytest tests/test_split_intelligence_reports.py
```

- Metrics: parity failures, stale/missing incidents.
- Risks: tests require private generated artifacts.
- Stop conditions: fixture contains private source text; rendered output says
  build while JSON says investigate/reject.
- Estimated size: M.
- Portfolio evidence produced: Radar honesty regression.
- Radar impact: `cross-repo`.

### RADAR-PGI-003 - Bounded Radar Validation Dogfood Run

- Status: `blocked`
- Priority: P1 parallel
- Owner: `operator` plus both repos
- Problem: RVE adapters are implemented, but live/cached validation outcomes
  have not yet been proven in a weekly dogfood loop.
- User outcome: Radar can honestly return build/investigate/reject based on
  matched external evidence, or clearly show gaps.
- Why now: required for portfolio claims about product validation.
- Dependencies: `RADAR-PGI-002`, `PGI-006`.
- Blocked by: fresh candidate artifact, credentials or cache fixtures, operator
  time.
- Files likely touched: docs scorecards and sanitized fixture notes only.
- Schema impact: none expected.
- API/contract impact: none expected.
- Migration impact: none.
- Test plan: existing Radar tests plus one bounded weekly review.
- Eval plan: Radar scorecard group.
- Acceptance criteria:
  - At least one weekly candidate has validation query pack reviewed.
  - Matched external evidence, missing evidence, adapter status, and decision
    change action are recorded.
  - No build-ready recommendation arises from context-only evidence.
  - Missing credentials degrade visibly.
- Verification commands:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py tests/test_mvp_report_quality.py
```

- Metrics: matched external evidence count, context-only misuse count,
  decision changes after validation.
- Risks: broad external search becomes idea mining; live credentials leak.
- Stop conditions: no current candidate; run would require committing private
  generated artifacts; external results are unmatched.
- Estimated size: M plus calendar time.
- Portfolio evidence produced: Radar decision honesty example.
- Radar impact: `cross-repo`.

## Historical Task Mapping

| Existing task | Verified status | New phase | Keep / merge / archive / replace | Reason |
|---|---|---|---|---|
| KIR-Q0..KIR-Q13 | `implemented_and_verified` for workbook plumbing | Phase 0 baseline | archive | Workbook is no longer the main product surface |
| KIR-Q-001..KIR-Q-007 | `implemented_and_verified` structural quality work | Phase 1 input | merge into `PGI-001` | Good contract foundation, not full domain model |
| KIR-Q-008 | `partial`, standard loop noted, forced regeneration blocked by missing LLM key | Phase 6 | merge into `PGI-006`/`PGI-007` | Eval/dogfood task, not next code PR |
| KIR-Q-009 | `planned` | Phase 1/6 | replace with `PGI-001` and `PGI-006` | Referee/thread audit needs canonical contract first |
| HPI-0..HPI-14 and HPI-9-lite | `implemented_but_not_dogfooded` | Phase 4 baseline | archive as component record | Hermes/PI foundation exists; awareness/evals remain |
| HPI-9 vector retrieval | `deferred` | none | keep deferred | Raw/vector RAG is not justified yet |
| HPI-10 | `blocked` | Phase 6/7 | merge into `PGI-007`/`PGI-008` | Requires dogfood evidence |
| RVE-0..RVE-7 | `implemented_and_verified`, `needs_live_validation` | Radar parallel | keep as Radar baseline | Code/tests exist in sibling repo |
| RVE-8 | `planned` | Phase 6/Radar | merge into `RADAR-PGI-003` | Dogfood validation run |
| DFX-0 | `planned` | Phase 4 | replace with `PGI-003` | Hermes artifact awareness belongs with cockpit PR |
| DFX-1..DFX-4 | `planned` | Phase 2/3 | replace with `PGI-002` | Feedback/context/ranking consolidated |
| DFX-5 | `planned` | Phase 5 | replace with `PGI-004` | Atlas v2 scope |
| DFX-6 | `planned` | Phase 4 | replace with `PGI-003` | Weekly Brief decision UX |
| DFX-7 | `planned` | Phase 2/4 | merge into `PGI-002`/`PGI-003` | Feedback flow plus Hermes explanation |
| DFX-8 | `planned` | Phase 6 | replace with `PGI-006`/`PGI-007` | Dogfood/eval protocol |

## Definition Of Done For Any PGI Task

- Code changes are limited to the task scope.
- Runtime behavior has tests or reproducible fixture verification.
- Sidecar and rendered output cannot contradict each other.
- Privacy boundary is respected; no generated private artifacts or secrets are
  committed.
- Documentation links are updated.
- Verification commands pass or failures are reported with reason.
- Stop conditions are checked explicitly.

## Current Verification Command Set

Use focused tests; do not run expensive LLM jobs for normal PR verification.

```bash
git diff --check
PYTHONPATH=src python3 -m pytest tests/test_ai_report_contract.py tests/test_split_intelligence_reports.py tests/test_intelligence_retrieval_items.py tests/test_pi_tools.py tests/test_pi_chat.py tests/test_opportunity_seed_export.py tests/test_mvp_weekly_pipeline.py
```

## Backlog Stop Conditions

- A task would weaken evidence gates.
- A task treats market/business context as demand proof.
- A task makes Hermes a memory source or mutation actor.
- A task requires raw Telegram firehose RAG by default.
- A task requires full-year backfill without a bounded use case.
- A task would commit private generated artifacts, raw exports, `.env`, or
  secrets.
