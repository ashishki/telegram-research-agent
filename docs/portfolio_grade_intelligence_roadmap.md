# Portfolio-Grade Personal Intelligence Roadmap

Version: 1.1
Last updated: 2026-07-15
Status: canonical broader product roadmap; IRX implementation is closed through
IRX-14 and dogfood is controlled by the rollout gate

This is the canonical product, architecture, evaluation, and portfolio-readiness
roadmap for `telegram-research-agent`. Other roadmap documents are component
records, historical implementation logs, or supporting specifications.

## W29 Product Correction

The W29 Brief and Atlas passed the structural PGI checks but failed as
information products. `docs/intelligence_report_v2_roadmap.md` records the
completed IRX-1 through IRX-14 correction sequence. PGI-003 through PGI-006
remain reusable infrastructure records, not proof of Report V2 reader value.
PGI-007 dogfood is held until `report-v2-rollout-gate` returns `eligible` on a
real current private weekly package.

## 1. Executive Target

Build a portfolio-grade Personal AI Decision & Learning Intelligence System:

> Turn Telegram, technical, and market signals into verifiable understanding,
> decisions, experiments, project changes, and demonstrated learning.

Target portfolio bar: 8.5-9/10 evidence for AI Engineer, Applied AI Engineer,
and AI Systems Engineer roles. The target is not "many components"; it is a
coherent system with evidence discipline, temporal knowledge, personalization,
bounded assistant behavior, evaluation, and real dogfood outcomes.

North-star metric:

> Weekly Verified Decision Impact: decisions, experiments, project changes, or
> learning outcomes caused by source-grounded intelligence, achieved within a
> bounded weekly reading budget and without false-confidence incidents.

Guardrails:

- Brief understandable within 5 minutes.
- Top-claim provenance coverage must reach 100% before portfolio claims.
- No build recommendation from context-only evidence.
- No feedback must remain `unknown`, never negative.
- Hermes must not perform hidden mutations.
- Report generation must stay within an explicit cost budget.
- Atlas must remain bounded and navigable.
- Operator friction must not exceed demonstrated value.

Thresholds are provisional until four stable weekly runs establish baselines.

## 2. Current Verified Baseline

Repo audit source: local code/tests/docs/fixtures plus sibling Radar checkout
and recent git history through 2026-07-15.

| Component | Status | Evidence |
|---|---|---|
| Telegram ingestion, scoring, digest, legacy Research Brief | `implemented_and_verified`, `legacy` | `src/main.py`, ingestion/processing/output modules, tests such as `tests/test_generate_digest.py`, `tests/test_report_quality.py` |
| Research Brief receipts, evidence memory, artifact feedback | `implemented_and_verified` | DB helpers in `src/db/*`, CLI paths in `src/main.py`, tests `test_evidence.py`, `test_research_brief_receipt*`, `test_artifact_feedback.py` |
| Knowledge Atom storage and extraction | `implemented_and_verified` | `src/db/knowledge_atoms.py`, `src/output/knowledge_extraction.py`, `knowledge-extract` CLI, `tests/test_knowledge_atoms.py`, `tests/test_knowledge_extraction.py` |
| Idea Thread storage and momentum | `implemented_and_verified` | `src/db/idea_threads.py`, `src/output/idea_threads.py`, `idea-threads` CLI, `tests/test_idea_threads.py` |
| Frontier analysis | `implemented_but_not_dogfooded` | `src/output/frontier_analysis.py`, CLI path; fresh forced regeneration needs LLM credentials |
| AI visual report / workbook contract | `implemented_and_verified`, `legacy surface` | `src/output/ai_visual_report.py`, `src/output/ai_report_contract.py`, `tests/test_ai_report_contract.py`; W28 committed fixture exists but represents old visual snapshot |
| Weekly Intelligence Brief and Knowledge Atlas split | `implemented_and_verified` with V1 compatibility and opt-in V2 previews | `src/output/weekly_intelligence_brief.py`, `src/output/knowledge_atlas_report.py`, `src/output/split_intelligence_reports.py`, `tests/test_split_intelligence_reports.py`, `tests/test_knowledge_atlas_report_v2.py`; V1 artifacts remain inspectable, while Brief V2 and Atlas V2 are manifest-bound opt-in surfaces |
| Report V2 rollout gate | `implemented_and_verified`, dogfood `not_started` | `src/output/report_v2_rollout.py`, `report-v2-rollout-gate`, `tests/test_report_v2_rollout.py`; returns `eligible` only for a real current package with period/Radar/reaction/editorial/project/visual/cost/quality/feedback/fixture evidence |
| Canonical intelligence sidecar contract | `implemented_and_verified` | `tra-intelligence-contract.v1` and additive V2 rollout contract paths; Brief/Atlas sidecars carry canonical SourceObservation/EvidenceItem/Claim plus additive ProjectImplication/LearningObjective projections and tests under `tests/fixtures/intelligence_contract/` |
| Hermes / PI facade and bounded tools | `implemented_but_not_dogfooded` with PGI-003 artifact awareness | `src/assistant/pi_facade.py`, `pi_tools.py`, `pi_chat.py`, `pi_intent.py`, tests `test_pi_*`; read-only tools now expose current/stale/missing Brief, Atlas, and Radar state |
| Feedback intake and action status | `implemented_and_verified` | `src/db/ai_report_feedback.py`, `src/output/action_status.py`, tests `test_ai_report_feedback.py`, `test_action_status.py`; IRX-12 adds report/surface/section/item targeting, confirmation gates, completed-action linkage, and feedback application receipts |
| Strategy Reviewer | `implemented_and_verified` as advisory-only | `src/output/strategy_reviewer.py`, `tests/test_strategy_reviewer.py`; it must not mutate config/code/profile |
| Project Intelligence | `implemented_and_verified`, `needs_dogfood` | `project_intelligence.v2` and `project_action_permissions.v1` expose evidence-bound PR-sized implications while weak/rejected/learning/existing states remain audit-only |
| Learning Intelligence | `implemented_locally`, `needs_dogfood` | `project-learning-projection.v1` distinguishes read, understood, explained, reproduced, implemented, tested, project-applied, measured, stale, and prerequisite_gap without counting passive reading as mastery |
| Market/business lens for Radar | `implemented_and_verified` as `context_only` | `src/output/market_pain_intelligence.py`, `src/output/opportunity_seed_export.py`, `tests/test_opportunity_seed_export.py`, `tests/test_market_context_lens.py` |
| MVP Radar RVE contract | `implemented_and_verified`, `needs_live_validation` | sibling repo has `validation_queries.py`, `validation_evidence.py`, SERP/Reddit/crawler/X adapters and tests; real weekly validation evidence still needs dogfood |
| Evaluation framework | `implemented_locally`, `needs_dogfood` | `weekly-intelligence-scorecard.v1` in `src/output/dogfood_review.py` records correctness, relevance, decisions/actions, learning, UX, Radar, and operations with explicit unknown/not-measured metrics |
| Portfolio evidence | `partial` | code/tests/docs exist; no 4-8 week dogfood series, sanitized demo dataset, evaluation report, or case study |

Open GitHub state: no open PRs and no open issues were returned by the GitHub
connector for `ashishki/telegram-research-agent` or `ashishki/Demand-to-MVP-Radar`.

## 3. Current Scorecard

Evidence-based portfolio score today: **6.8/10**.

Why not higher:

- The system has substantial implementation evidence, but the target Brief /
  Atlas / Hermes workflow still lacks four stable real dogfood weeks.
- Correctness exists as report contract checks, but the canonical domain model
  still conflates atoms, claims, source events, and evidence in places.
- Personalization uses feedback and deterministic ranking, but explicit operator
  context, signal strength, feedback provenance, and "why selected for you" are
  not complete.
- Dogfood evidence is one W28/W29-style slice, not four to eight stable weekly
  outcomes.
- Portfolio presentation is not yet reproducible as a sanitized local demo.

## 4. Product Positioning

The product is a private, single-operator intelligence system. It is not SaaS,
not a generic chatbot, not a public bot, and not a multi-user platform.

Positioning:

- Weekly Brief: decision cockpit for the next week.
- Knowledge Atlas: cumulative map of understanding.
- Hermes: bounded concierge over curated intelligence objects.
- Project Intelligence: projection of signals onto active repos.
- Learning Intelligence: evidence of skill movement from reading to applied
  results.
- MVP Radar: downstream opportunity validation engine, parallel but not central.

## 5. Product Surfaces And Responsibilities

| Surface | Responsibility | Must not do |
|---|---|---|
| Weekly Intelligence Brief | 3-5 minute decision snapshot: what changed, why it matters, what to do, what to ignore, project impact, Radar gate, exact feedback targets | Become Atlas; bury evidence gaps; promote context-only market commentary |
| Knowledge Atlas | Navigate temporal threads, claims, evidence, contradictions, source diversity, maturity, open questions, decisions, experiments, and study backlog | Be a long static report or decorative graph |
| Hermes / PI Assistant | Answer from curated objects, explain provenance, prepare Codex-ready tasks, help record decisions/experiments/outcomes | Mutate code/YAML/profile/scoring; run Codex; use raw Telegram firehose RAG by default |
| Project Intelligence | Show confirmed project leads, watches, rejected overlaps, tiny PR ideas, stale decisions, research debt | Turn broad keyword overlap into project truth |
| Learning Intelligence | Track read -> understood -> explained -> reproduced -> implemented -> tested -> project outcome | Count passive reading as mastery |
| MVP Radar | Validate external product opportunity beyond Telegram | Treat Telegram/market context as demand proof |

## 6. Canonical Intelligence Loop

```text
Source Observation
  -> Evidence Item
  -> Claim
  -> Knowledge Atom
  -> Idea Thread / Question / Contradiction
  -> Project Implication / Learning Objective
  -> Weekly Brief / Atlas / Hermes retrieval / Radar seed
  -> Decision / Experiment
  -> Outcome
  -> Feedback and evaluation
```

LLM-generated prose is never source of truth. It is a derived interpretation
that must reference structured evidence or declare insufficient evidence.

## 7. Target Domain Model

Canonical entities:

- `SourceObservation`: source identity, URL, timestamp, raw excerpt, metadata,
  source type, collection method, ingestion provenance.
- `EvidenceItem`: source observation ref, exact quote or verified excerpt,
  evidence role, evidence tier, independence key, verification status, date
  relevance, scope, expiry/staleness, positive/negative/contradictory role.
- `Claim`: statement, scope, time horizon, supporting and contradicting
  evidence, source independence, confidence band, uncertainty reasons,
  verification state.
- `KnowledgeAtom`: minimal useful knowledge change; answers what changed, why it
  differs from prior state, who it matters to, and how quickly it may stale.
- `IdeaThread`: previous/current state, temporal deltas, forks, contradictions,
  competing approaches, maturity, momentum, evidence growth, status, merge/split
  audit.
- `Question`: explicit unknown or unresolved gap.
- `ProjectImplication`: `confirmed_project_lead`, `project_watch`,
  `learning_only_implication`, or `rejected_overlap`.
- `Decision`: `apply`, `study`, `watch`, `verify_first`, `defer`, `reject`.
- `Experiment`: hypothesis, scope, effort, success criterion, kill condition,
  follow-up date, result.
- `LearningObjective`: skill or concept with prerequisite and evidence state.
- `Outcome`: observed result after decision/action/experiment.
- `FeedbackEvent`: append-only operator signal with provenance and correction
  semantics.
- `OperatorContext`: explicit interests, projects, goals, constraints, learning
  gaps, source trust, saturation, novelty appetite, and anti-priorities.

Derived projections:

- Weekly Brief.
- Knowledge Atlas.
- Hermes retrieval items.
- Project Intelligence.
- Learning Dashboard.
- Obsidian export.
- Strategy Reviewer output.
- Radar seed/context pack.

## 8. Architecture Boundaries

- SQLite and versioned JSON sidecars hold canonical or reproducible structured
  state.
- HTML, Markdown, Telegram messages, and Obsidian notes are projections.
- Hermes reads through `PersonalIntelligenceFacade` and PI tools; no raw DB
  sessions or mutation tools.
- Radar receives versioned seed/context packs and returns a versioned candidate
  dossier. Missing Radar artifacts must not break Brief or Atlas generation.
- Cross-repo schema changes require version bumps, tests in both repos, and
  sidecar/rendered-output consistency checks.
- Expensive LLM passes are bounded and never required for docs-only work.

## 9. Parallel Workstreams

| Workstream | Goal | Current status | Next PGI phase |
|---|---|---|---|
| A - Intelligence Correctness | Verifiable, temporal-aware conclusions | `partial` | Phase 1 |
| B - Personal Relevance | Move from topic boosting to explicit personalization | `partial` | Phase 2/3 |
| C - Decision Interface | Weekly Brief as decision cockpit | `partial` | Phase 4 |
| D - Knowledge Navigation | Atlas as navigable cumulative map | `partial` | Phase 5 |
| E - Hermes / PI Assistant | Useful bounded interface over curated intelligence | `implemented_but_not_dogfooded` | Phase 4 |
| F - Project and Learning Intelligence | Project implications and skill outcomes | `implemented_locally`, `needs_dogfood` | Phase 5 |
| G - Evaluation and Dogfood | Prove user value and reduce false confidence | `scorecard_foundation_implemented`, `dogfood_blocked` | Phase 6 |
| H - MVP Radar Parallel Track | External opportunity validation | `implemented_and_verified`, `needs_live_validation` | Parallel all phases |

## 10. Development Phases

### Phase 0 - Stop, Simplify, Baseline

Status: completed by this docs-first session when the new roadmap/backlog land.

Acceptance:

- One canonical roadmap.
- One active backlog and one next P0 task.
- Historical roadmaps clearly marked.
- Current baseline and scorecard stated.
- Canonical entities/projections and portfolio readiness gate defined.
- W28 committed fixture baseline identified; untracked private manual eval not
  treated as committed evidence.

### Phase 1 - Insight Correctness

Goal: make conclusions trustworthy before deeper personalization.

Tasks:

- Evidence/claim/source observation contract.
- Contradiction and negative evidence model.
- Source independence and quote verification.
- Temporal delta, novelty, staleness, merge/split audit.
- Confidence calibration and unsupported narrative prevention.
- Report-level evidence gates and eval fixtures.

Primary task: `PGI-001`.

Implementation note on 2026-07-10: `PGI-001` is implemented locally. The repo
now writes and validates `tra-intelligence-contract.v1` as an additive sidecar
projection over existing curated atoms, threads, and report cards. The legacy
`weekly-ai-intelligence-v1` workbook contract remains for compatibility. Brief
and Atlas HTML include contract-version meta tags; retrieval can expose
canonical claim/evidence items; Radar-facing seeds carry
`tra-radar-intelligence-contract.v1` without allowing context-only records to
satisfy demand gates. No DB migration or LLM run was required.

### Phase 2 - Feedback And Operator Context

Goal: make the system learn safely.

Tasks:

- Feedback provenance and effect timing.
- Append-only corrections and accidental feedback handling.
- Signal strength model.
- Explicit operator context with stale-context warnings.
- Source trust by domain.
- No-feedback confidence state.

Primary task: `PGI-002`.

Current implementation note: PGI-002 now records feedback provenance,
future-only effect windows, signal strength, and append-only correction/
retraction events. AI report and Weekly Brief sidecars carry
`ranking_factors`/`why_selected` for top action/read/try items, and rendered
HTML copies those data-backed explanations. `read` remains a weak observation;
no-feedback is `unknown`, not negative. Hermes/PI exposes the fields read-only.

### Phase 3 - Explainable Personalized Ranking

Goal: every top item explains why it was selected.

Ranking factors:

- freshness, momentum, evidence strength, source diversity, operator context,
  active projects, research questions, business focus, learning gaps, feedback,
  saturation, novelty appetite, confidence, and staleness.

Acceptance:

- Factors are stored in sidecars.
- HTML explanations are data-backed, not LLM decoration.
- Weak behavioral signals cannot override explicit operator context.

### Phase 4 - Decision Cockpit And Hermes

Goal: weekly use becomes fast and useful.

Tasks:

- Weekly Brief first-screen redesign.
- Split-artifact and stale-artifact Hermes awareness.
- Provenance-aware answers.
- Project action cards and exact feedback refs.
- Decision journal and experiment follow-up.
- MVP Radar Gate Card with graceful missing/stale state.

Primary task: `PGI-003`.

Current implementation note: PGI-003 now adds a sidecar-backed Weekly Brief
decision cockpit, exact feedback target refs, strict Radar gate DTO, missing
Radar graceful degradation, and read-only Hermes artifact freshness awareness.
Radar build/focused decisions remain impossible without matched decision-grade
external evidence; market/business context remains `context_only`.

### Phase 5 - Atlas, Project Intelligence And Learning

Goal: cumulative understanding and AI Systems Engineer growth.

Tasks:

- Atlas v2 temporal lanes and thread detail.
- Evidence/contradiction/source pane.
- Project Intelligence projection.
- Learning Dashboard and study backlog.
- Skill evidence and stale knowledge review.

Current implementation note: PGI-004 now adds Atlas thread navigation with
sidecar-backed thread timelines, current understanding, evidence panes,
contradictions, source diversity, maturity, momentum-vs-evidence, project
connections, decision projections, open questions, study-next items, original
source links, and `atlas_thread` retrieval items.

Current implementation note: PGI-005 now adds additive
`project-learning-projection.v1` DTOs. Brief and Atlas sidecars/rendered HTML
show Project Intelligence and Learning Intelligence projections; retrieval
emits `project_intelligence` and `learning_objective` items. Broad keyword
overlap is rejected rather than confirmed, market/business context remains
`context_only`, and passive reading is not counted as mastery. No DB migration
or LLM run was required.

### Phase 6 - Evaluation And Dogfood

Goal: prove that the system improves decisions and learning.

Current implementation note: PGI-006 adds deterministic
`weekly-intelligence-scorecard.v1` artifacts with JSON/Markdown writers,
schema validation, file-based sanitized fixture loading, explicit
unknown/not-measured metric handling, and false-confidence incident records.
The four-week evidence series remains blocked on operator dogfood inputs.

Minimum evidence:

- Four stable weekly runs; six to eight preferred for portfolio claims.
- Offline evals, weekly scorecard, manual review protocol.
- Hermes answer dataset.
- Radar honesty checks.
- Cost/latency and regression fixtures.

### Phase 7 - Portfolio Hardening

Goal: make the project understandable and convincing to a Staff Engineer or
hiring manager.

Tasks:

- Sanitized demo dataset.
- Reproducible local demo.
- Architecture/domain/sequence diagrams.
- Sample Brief and Atlas.
- Evaluation report and failure cases.
- Cost/latency report, CI status, setup guide, screenshots, 5-minute demo,
  case study, public/private data boundary.

## 11. Task Registry

Canonical active backlog lives in `docs/tasks.md`.

| Existing task | Verified status | New phase | Keep / merge / archive / replace | Reason |
|---|---|---|---|---|
| KIR-Q0..KIR-Q13 | `implemented_and_verified` for plumbing; workbook now legacy surface | Phase 0 baseline | archive as historical implementation record | Do not reimplement workbook plumbing |
| KIR-Q-001..KIR-Q-007 | `implemented_and_verified` structural correctness slices | Phase 1 baseline | merge into PGI-001 inputs | Good foundation, not full canonical entity model |
| KIR-Q-008 | `partial` / `needs_live_validation` | Phase 6 | merge into PGI-006/PGI-007 | Manual eval and forced regeneration are dogfood/eval tasks |
| KIR-Q-009 | `planned` | Phase 1/6 | replace with PGI-001 merge/split/referee scope | Needs dependency-aware correctness design first |
| HPI-0..HPI-14 and HPI-9-lite | `implemented_but_not_dogfooded` | Phase 4 baseline | archive as Hermes foundation record | Facade/tools/chat exist; product assistant still needs awareness/evals |
| HPI-9 vector retrieval | `deferred` | none | keep deferred | Raw/vector RAG is not next |
| HPI-10 post-dogfood review | `blocked` | Phase 6/7 | merge into portfolio readiness review | Requires 4+ dogfood weeks |
| RVE-0..RVE-7 | `implemented_and_verified`, `needs_live_validation` | Parallel Radar track | keep as Radar baseline | Contract and adapters exist; live evidence still needs dogfood |
| RVE-8 | `planned` | Phase 6 / Radar track | merge into `RADAR-PGI-003` | Dogfood validation belongs with weekly scorecard |
| DFX-0..DFX-8 | `planned` | Phases 2-6 | replace with PGI-002..PGI-007 | Good findings, but old queue duplicates new architecture |

New task prefix: `PGI` for Portfolio-Grade Intelligence. Radar-side parallel
tasks use `RADAR-PGI`.

## 12. Dependency Graph

```text
PGI-001 Canonical contract/eval fixtures
  -> PGI-002 Operator context/feedback provenance
  -> PGI-003 Explainable ranking + Brief/Hermes/Radar gate
  -> PGI-004 Atlas v2
  -> PGI-005 Project and Learning Intelligence
  -> PGI-006 Evaluation harness and weekly scorecard
  -> PGI-007 Dogfood evidence series
  -> PGI-008 Portfolio hardening

RADAR-PGI-001 Cross-repo contract version alignment
  -> RADAR-PGI-002 Radar dossier fixture parity
  -> RADAR-PGI-003 Live validation dogfood run
```

`RADAR-PGI-*` can proceed in parallel after `PGI-001` defines the shared
contract version.

## 13. Evaluation Framework

The full specification lives in `docs/intelligence_evaluation_framework.md`.

Minimum weekly scorecard groups:

- Correctness: provenance coverage, verified quotes, unsupported claims,
  single-source overstatement, contradiction visibility, false confidence.
- Relevance: precision@3, precision@5, wrong-priority rate,
  ignored-but-repeated topics, personalization confidence.
- Decisions/actions: time to understand, decisions changed, actions selected
  and completed, experiments, project changes, defer/reject captured.
- Learning: concepts moved from read to implemented, skill gaps closed,
  exercises, stale knowledge review, project-linked learning.
- UX: Brief first-screen task success, Atlas source/thread tasks, Hermes
  satisfaction, feedback friction.
- Radar: matched external evidence, context-only misuse, stale/missing Radar,
  JSON/Markdown/Brief/Hermes contradictions.
- Operations: generation success, missing artifacts, cost, latency, tests,
  health-check failures.

## 14. Dogfood Protocol

Dogfood requires one weekly routine:

1. Generate current Brief and Atlas with bounded settings.
2. Read the Brief first; record time-to-understand.
3. Pick decisions/actions/experiments or explicitly defer/reject.
4. Use Atlas for at least two source/thread navigation tasks.
5. Ask Hermes at least three provenance-bound questions.
6. Record exact feedback events.
7. Record outcomes the following week.
8. Update weekly scorecard.

Private generated artifacts stay out of git unless explicitly sanitized.

## 15. MVP Radar Integration Contract

Full contract: `docs/mvp_radar_integration_contract.md`.

Contract version: `tra-radar-intelligence-contract.v1`.

Rules:

- Market/business Telegram pack is context-only.
- Telegram commentary cannot pass external evidence gates.
- Missing/stale Radar artifacts must be visible but non-blocking for Brief/Atlas.
- Hermes must explain market lens vs matched external evidence.
- Cross-repo changes need owner and tests in the owning repo.

## 16. Learning Roadmap

Full learning plan: `docs/operator_ai_systems_learning_roadmap.md`.

Learning must produce implementation artifacts in this repo. Passive reading is
not counted as mastery.

## 17. Portfolio Evidence Plan

Full plan: `docs/portfolio_evidence_plan.md`.

Portfolio evidence must include product outcomes, correctness evals,
engineering quality, assistant quality, product surfaces, and presentation.

## 18. What Not To Build

Non-goals for the next 3-6 months:

- Public SaaS.
- Multi-user permissions.
- Generic chatbot.
- Multi-agent orchestration for show.
- Graph database without proven need.
- Raw Telegram vector RAG by default.
- Autonomous Codex execution.
- Automatic profile/config/code mutation.
- External memory provider.
- Full-year backfill without bounded use case.
- Decorative knowledge graph.
- Mobile app.
- Large frontend framework without necessity.
- Complex microservices.
- Real-time everything.
- AI-generated visual decoration instead of information architecture.
- Build-ready Radar decisions without external validation.

## 19. First Three Implementation PRs

### PR 1 - Canonical Intelligence Contract And Eval Fixtures

Rationale: stabilize the entity/sidecar contract before personalization.

Dependencies: none after docs baseline.

Likely files:

- `src/output/ai_report_contract.py`
- `src/output/weekly_intelligence_brief.py`
- `src/output/knowledge_atlas_report.py`
- `src/output/intelligence_retrieval_items.py`
- `tests/test_ai_report_contract.py`
- new eval fixtures under `tests/fixtures/intelligence_contract/`

Schema/API impact: version sidecar contract; no DB migration in first slice
unless absolutely required.

Tests/evals:

- unit tests for SourceObservation/EvidenceItem/Claim/Atom projection shape;
- quote/provenance/temporal gate fixtures;
- rendered vs sidecar consistency checks.

Rollback: keep old sidecar readers accepting previous fields while writing the
new version behind a version key.

User outcome: top Brief/Atlas items have explicit evidence/claim/provenance
objects and insufficient-evidence states.

Definition of done:

- New contract version documented and tested.
- W28-style fixture demonstrates unsupported claim failure.
- No runtime LLM call required for tests.

Verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ai_report_contract.py tests/test_split_intelligence_reports.py tests/test_intelligence_retrieval_items.py
```

Portfolio evidence: canonical domain model and regression fixture foundation.

### PR 2 - Operator Context, Feedback Provenance And Explainable Ranking

Rationale: make personalization explicit and auditable.

Dependencies: PR 1.

Likely files:

- `src/db/ai_report_feedback.py`
- `src/output/personalize.py`
- `src/output/ai_intelligence_report.py`
- `src/output/weekly_intelligence_brief.py`
- `src/assistant/pi_facade.py`
- `tests/test_ai_report_feedback.py`
- `tests/test_ai_intelligence_report.py`

Schema/API impact: append-only feedback correction/provenance fields may need a
versioned migration; operator context should start as read-only config/sidecar.

Implemented note: the current slice uses an idempotent SQLite constraint rebuild
for expanded feedback event/target enums and additive sidecar fields; no
production config change is required.

Tests/evals:

- no-feedback stays unknown;
- `verify_first` calibrates trust, not topic promotion;
- ranking factor sidecars match HTML explanations;
- accidental correction appends, never rewrites.

Rollback: disable ranking factor consumption while preserving stored events.

User outcome: each top item says why it was selected and which feedback/context
affected it.

Definition of done:

- Feedback provenance/effect window visible.
- Ranking factors stored per item.
- Weak signals cannot override explicit context.

Verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ai_report_feedback.py tests/test_ai_intelligence_report.py tests/test_pi_facade.py
```

Current verified command set also includes `tests/test_action_status.py`,
`tests/test_split_intelligence_reports.py`, `tests/test_strategy_reviewer.py`,
`tests/test_pi_tools.py`, `tests/test_pi_chat.py`, and
`tests/test_intelligence_retrieval_items.py`.

Portfolio evidence: explainable personalization and feedback safety.

### PR 3 - Weekly Decision Cockpit, Hermes Awareness And Radar Gate

Rationale: make the main weekly workflow usable in under five minutes.

Dependencies: PR 1; best after PR 2.

Likely files:

- `src/output/weekly_intelligence_brief.py`
- `src/output/split_intelligence_reports.py`
- `src/assistant/pi_facade.py`
- `src/assistant/pi_chat.py`
- `src/output/intelligence_retrieval_items.py`
- `tests/test_split_intelligence_reports.py`
- `tests/test_pi_chat.py`
- `tests/test_pi_tools.py`

Schema/API impact: Brief sidecar gets first-screen decision snapshot,
artifact freshness, exact feedback refs, and Radar gate contract version.

Tests/evals:

- Brief first screen has decision snapshot, top 3 changes, trust summary,
  what-to-do, ignore/defer, project impact, Radar gate, feedback targets;
- Hermes names current/stale/missing Brief/Atlas/Radar artifacts correctly;
- market context vs matched external evidence is distinguishable.

Rollback: keep old renderer path and fall back when new sections are missing.

User outcome: one current Weekly Brief plus Hermes can answer the weekly
decision questions without hiding evidence gaps.

Definition of done:

- Brief remains short.
- Hermes is grounded and bounded.
- Missing Radar artifact is graceful.

Verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_split_intelligence_reports.py tests/test_pi_chat.py tests/test_pi_tools.py tests/test_mvp_weekly_pipeline.py
```

Portfolio evidence: decision cockpit and assistant quality slice.

## 20. Final Portfolio Readiness Gate

Gate statuses today:

| Gate | Status | Evidence needed |
|---|---|---|
| Product evidence | `partial` | 4-8 dogfood weeks, decisions/actions changed, rejected/deferred examples, overload reduction, project improvements, learning outcomes |
| Intelligence correctness | `partial` | versioned canonical entities, claim/evidence separation, temporal deltas, contradictions, uncertainty, eval results, regression fixtures |
| Engineering quality | `partial` | deterministic baseline, CI, bounded LLM, reproducibility, idempotency, observability, cost telemetry, graceful degradation |
| Assistant quality | `partial` | grounded answer evals, current/stale artifact awareness, insufficient evidence states, feedback provenance |
| Product surfaces | `partial` | decision-first Brief, navigable Atlas, Project Intelligence, Learning Intelligence, Radar Gate integration |
| Portfolio presentation | `not started` | sanitized demo, diagrams, screenshots, case study, evaluation report, 5-minute demo script |

No gate is `evidenced` until it points to concrete committed artifacts, tests,
or dogfood scorecards.
