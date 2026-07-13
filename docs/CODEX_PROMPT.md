# CODEX_PROMPT - Compact Session Handoff

Version: 5.1
Date: 2026-07-13
State: IRX-1 implemented and focused-test verified; IRX-2 is the next
implementation task; dogfood is blocked until IRX-14

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
IRX-2 - Weekly Run Manifest And Required Radar Artifact Contract
```

## W29 Product Correction

The W29 Brief and Atlas are structurally valid but failed as reader products.
The default run analyzed the newly started W29, missed the valid W28 Radar
artifact, did not expose reaction influence, repeated generic actions, rendered
entity-fragmented threads, and provided no meaningful visual map. The current
detailed Atlas becomes the Knowledge Audit Explorer foundation. IRX-1 now fixes
the shared completed-period semantics; the manifest, editorial, and reader V2
surfaces remain planned, and dogfood has not started.

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
- IRX-2 persisted manifest/orchestration and same-run Radar binding were
  intentionally left open and are now the only active implementation scope.

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

## Exact Next Codex Prompt - IRX-2

Use the following prompt unchanged for the next implementation task:

```text
You are Codex working in /srv/openclaw-you/workspace/telegram-research-agent.
Mode: IMPLEMENTATION for IRX-2 only.
Implement IRX-2, using these binding docs:
  docs/intelligence_report_v2_roadmap.md
  docs/intelligence_report_v2_contract.md
  docs/weekly_run_manifest.md
  docs/mvp_radar_integration_contract.md
Do not implement IRX-3 or later work: no reaction boost, canonical curator, editorial LLM, V2 schema/render redesign, reader-value gates, report-specific feedback redesign, or Radar gate changes.
Before editing run:
  git status
  git branch
  git log --oneline -20
  git diff --stat
Preserve pre-existing dirty changes. Do not edit or commit generated reports.
Read the current period/run/Radar flow and focused tests for:
  src/output/split_intelligence_reports.py, weekly_intelligence_brief.py,
  knowledge_atlas_report.py, ai_intelligence_report.py,
  mvp_weekly_pipeline.py, opportunity_seed_export.py, ai_report_contract.py,
  pi_facade.py, and src/main.py.
Add an additive weekly_run_manifest.v1 module and one explicit orchestration command alongside existing V1 commands. Reuse the IRX-1 ReportingPeriod unchanged.
Required behavior:
1. One command creates an immutable run_id and atomically maintained weekly_run_manifest.v1 for one ReportingPeriod.
2. The manifest records period identity, declared stage policy, stage statuses, warnings/failed stages, snapshot/reference fields, artifact paths, checksums, run_status, and partial exactly as the binding contract requires.
3. Every artifact produced or bound by the orchestrated path repeats the same run_id, period, and manifest identity additively; old commands and paths remain compatible.
4. Bind the real same-period Radar JSON by structured payload identity and checksum, never filename adjacency. The real candidate/status reaches the Brief sidecar/context.
5. Required Radar missing, failed, malformed, or wrong-period makes the package partial or failed. Intentional disablement must be declared before execution and reader-visible; it must never masquerade as success.
6. Stage transitions and final run status are deterministic. Atomic writes never expose invalid JSON, and regeneration never overwrites a prior run identity.
7. Reaction sync failure, Radar failure/wrong period/disablement, render failure, and supported fallback states are explicit in the manifest and tested without weakening existing evidence gates.
8. Delivery must not present a stale prior Brief as the current successful package.
Add deterministic tests for manifest validation, immutable identity, atomic persistence, success, partial/failure aggregation, wrong-run/period Radar rejection, intentional Radar disablement, reaction failure, render failure, sidecar identity propagation, stale-artifact exclusion, and legacy command compatibility.
Do not change scoring, prompts, DB schema, information architecture, visual design, feedback semantics, IRX-1 period behavior, cross-repo evidence logic, or Radar gates. Do not run live/expensive pipelines or the full suite.
Run:
  PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
    python3 -m unittest tests.test_weekly_run_manifest \
    tests.test_split_intelligence_reports tests.test_mvp_weekly_pipeline \
    tests.test_pi_facade
  cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar && \
    .venv/bin/python -m pytest tests/test_mvp_of_week.py
  git diff --check
  git diff --stat
Report files changed, manifest/run-state semantics, same-run Radar binding, compatibility behavior, exact test results, the IRX-3 handoff intentionally left open, and confirmation that generated artifacts and Radar gates were unchanged.
```

Suggested following task after review: `IRX-3 - Reaction-To-Ranking
Personalization And Effect Receipt`.

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
