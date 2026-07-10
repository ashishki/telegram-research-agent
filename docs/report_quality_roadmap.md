# Report Quality And Radar Handoff Roadmap

Status: historical implemented AI-development roadmap
Last updated: 2026-07-10

Canonical active roadmap:
`docs/portfolio_grade_intelligence_roadmap.md`.

## Purpose

The weekly pipeline now collects evidence, writes receipts, and delivers
multiple artifacts. The next product problem is reader usefulness: the operator
must understand what was evaluated, why it matters, what changed, and what to
do next without reverse-engineering the pipeline.

This roadmap is the historical handoff for improving:

- Telegram Research Agent weekly Research Brief and supporting artifacts.
- Implementation Ideas feedback loops.
- Demand-to-MVP Radar weekly candidate output.
- Cost/guardrail dogfooding inside this private operator system.

## Triggering Review

The 2026-W24 artifacts showed that the data pipeline improved, but the report
experience did not.

Observed positives:

- Weekly digest processed 179 Telegram posts.
- Watch signals increased from 16 to 56.
- Noise decreased from 157 to 116.
- Average signal score increased from 0.3300 to 0.4146.
- Research Brief delivery succeeded without fallback.
- Core evidence lookup passed for local evidence refs and Telegram links.

Observed reader-facing failures:

- `data/output/digests/2026-W24.md` starts with content, not a decision brief.
- `What Changed` appears late instead of in the first screen.
- Many user-visible takeaways are internal matching traces such as
  `Matches: claude, git`.
- `data/output/study_plans/2026-W24.md` says "No Telegram signals this week"
  while the digest found 56 watch signals.
- `data/output/project_insights/2026-W24.md` says no project insights while
  the digest contains a large `Project Insights` section.
- Radar's
  `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/reports/mvp_of_week/mvp-weekly-2026-W24.md`
  says the focused-experiment gate is satisfied and later says the candidate
  was downgraded. One report cannot present both as final truth.
- June operator feedback is effectively empty: no recent reaction sync rows,
  no weekly usefulness logs, and no artifact feedback rows. The system has
  little direct signal about the operator's taste.

## North Star

Every Monday artifact should answer these questions first:

1. What did the system evaluate?
2. What changed versus last week?
3. What is the decision or recommended action?
4. Why should the operator believe it?
5. What should be done, deferred, or rejected?

The evidence and receipt layer can remain detailed, but the reader-facing layer
must be compact, consistent, and decision-oriented.

## Cross-Repo Context

Primary repo:

```text
/srv/openclaw-you/workspace/telegram-research-agent
```

Demand-to-MVP Radar repo:

```text
/srv/openclaw-you/workspace/Demand-to-MVP-Radar
```

Radar files that matter for the tasks below:

- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/mvp_weekly.py`
  - `run_mvp_of_week`
  - `_synthesize_or_render`
  - `_apply_synthesis_gates`
  - `_append_gate_notes`
  - `_append_report_quality_sections`
  - `_render_report`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/tests/test_mvp_of_week.py`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/config/mvp_weekly_sources.json`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/reports/mvp_of_week/`

Telegram Research Agent files likely involved:

- `src/output/generate_digest.py`
- `src/output/signal_report.py`
- `src/output/render_report.py`
- `src/output/generate_recommendations.py`
- `src/output/generate_study_plan.py`
- `src/output/map_project_insights.py`
- `src/output/mvp_weekly_pipeline.py`
- `src/output/operator_report.py`
- `src/bot/callbacks.py`
- `src/bot/bot.py`
- `src/bot/telegram_delivery.py`
- `src/db/artifact_feedback.py`
- `src/llm/client.py`
- `src/llm/router.py`

## AI Development Rules

- Work on one task at a time in priority order.
- Keep generated `data/output/...` artifacts out of commits unless the task
  explicitly asks for fixture snapshots.
- Use production-like Python for manual CLI checks:

```bash
PYTHONPATH=src /srv/openclaw-you/venv/bin/python3 src/main.py <command>
```

- For local unit tests in this repo:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest ...
```

- For Radar tests:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py
```

- Do not add a public UI. The target is still the private operator loop.
- Do not store model-authored trust as fact. Trust and down-rank reasons must
  be derived from observed evidence or operator feedback.
- Do not make Radar more confident than its source mix supports.

## P0 Tasks

### RQ-1 - Weekly Decision Brief Header

Status: implemented.

Goal: make the Research Brief useful in the first screen.

Implemented in `src/output/signal_report.py`, `src/output/generate_digest.py`,
and `src/output/render_report.py`: reader-mode Research Brief starts with
Decision Brief, Actions This Week, and early What Changed; Telegram
notification includes a compact funnel and action count.

Add a compact decision brief at the top of the delivered Research Brief and in
the Telegram notification.

Required content:

- evaluated window and post count;
- bucket funnel, for example `179 posts -> 56 watch -> 3 actions`;
- change versus previous week for watch, noise, and average score;
- top 1-3 operator actions;
- confidence/evidence status in plain language;
- source mix summary;
- explicit "Read this if..." or "Skip if..." guidance when signal is weak.

Current bad example:

- `data/output/digests/2026-W24.md` starts directly with `## Macro Context`.

Expected shape:

```text
## Decision Brief
- Evaluated: 179 Telegram posts from the last 7 days.
- Signal change: watch 16 -> 56, noise 157 -> 116, avg score 0.33 -> 0.41.
- Decision: apply README-first memory and report-quality gates now; dogfood cost
  guardrails internally; keep Radar candidate as investigate until source gate
  is consistent.
- Evidence: local receipt/evidence lookup passed; confidence medium.

## Actions This Week
1. ...
```

Likely touched files:

- `src/output/signal_report.py`
- `src/output/generate_digest.py`
- `src/output/render_report.py`
- `tests/test_signal_report.py`
- `tests/test_generate_digest.py`
- `tests/test_render_report.py`

Acceptance criteria:

- Research Brief begins with `## Decision Brief`.
- `## What Changed` or equivalent change summary appears before detailed
  project sections.
- Telegram notification includes a compact funnel and top action count.
- Existing receipt and delivery behavior still works.
- Tests cover a normal week and a weak/low-signal week.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_signal_report tests.test_generate_digest tests.test_render_report
```

### RQ-2 - Report Quality Gates Before Delivery

Status: implemented.

Goal: prevent confusing or contradictory artifacts from being delivered as if
they were clean reports.

Implemented via `src/output/report_quality.py`, non-blocking digest delivery
warnings for critical findings, Study Plan and Project Insights quality
logging, and a monthly `operator-report` Report Quality section.

Add deterministic report-quality validation for generated weekly artifacts.

Checks should catch:

- user-visible `Matches: ...` lines used as takeaways;
- missing decision brief;
- `What Changed` buried after detailed sections;
- Study Plan saying no Telegram signals when digest/evidence rows show signals;
- Project Insights saying no insights when the digest contains project insights;
- empty or contradictory source/evidence confidence sections;
- generated artifact word count greatly above the expected scan budget without
  an explicit summary.

Suggested implementation:

- Add `src/output/report_quality.py`.
- Return structured findings with `severity`, `artifact_type`, `message`, and
  optional `line_hint`.
- Store or log findings without blocking delivery at first.
- If a critical contradiction is found, include a short warning in the Telegram
  delivery notification.

Likely touched files:

- `src/output/report_quality.py`
- `src/output/generate_digest.py`
- `src/output/generate_study_plan.py`
- `src/output/map_project_insights.py`
- `src/output/operator_report.py`
- `tests/test_report_quality.py`
- existing tests for digest/study/project insights.

Acceptance criteria:

- A fixture with `Matches: claude, git` as a takeaway returns a warning.
- A fixture where Study Plan says "No Telegram signals" while `watch_count > 0`
  returns a critical finding.
- A fixture where Project Insights is empty while digest has project insights
  returns a critical finding.
- Findings are visible from CLI or operator report.
- Initial implementation does not prevent delivery unless an explicit
  `--strict` mode is added.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_report_quality tests.test_generate_digest tests.test_generate_study_plan
```

### RQ-3 - Artifact Feedback Buttons

Status: implemented.

Goal: make it easy for the operator to teach the system what was useful or
confusing without typing CLI commands.

Implemented through compact artifact callback payloads in `src/bot/callbacks.py`,
delivery markup on Research Brief, Implementation Ideas, MVP weekly, and Study
Plan notifications, `mvp_weekly` support in `artifact_feedback_logs`, and
focused callback/delivery tests. Existing per-idea Implementation Ideas buttons
continue to write to `decision_journal`.

Extend Telegram inline callbacks beyond Implementation Ideas.

Add artifact-level feedback buttons for:

- Research Brief notification;
- Implementation Ideas notification;
- MVP of the Week notification;
- optional Study Plan notification/reminder.

Recommended buttons:

```text
Useful | Unclear | Noise | Apply | Defer
```

Map buttons into existing `artifact_feedback_logs`:

- `Useful` -> `feedback=useful`
- `Unclear` -> `feedback=weak`
- `Noise` -> `feedback=noisy`
- `Apply` -> `feedback=decision_impacting`
- `Defer` -> `feedback=weak` with a note such as `deferred_from_button`

Likely touched files:

- `src/bot/callbacks.py`
- `src/bot/bot.py`
- `src/output/generate_digest.py`
- `src/output/generate_recommendations.py`
- `src/output/mvp_weekly_pipeline.py`
- `src/db/artifact_feedback.py`
- `tests/test_callbacks.py`
- `tests/test_artifact_feedback.py`
- `tests/test_generate_digest.py`
- `tests/test_product_ops.py` if MVP delivery is covered there.

Acceptance criteria:

- Pressing a live or test callback writes one `artifact_feedback_logs` row.
- Callback payloads are compact enough for Telegram.
- Bot answers the callback with a human-readable acknowledgement.
- Existing idea buttons continue to work.
- `operator-report --month` reflects artifact feedback counts.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_callbacks tests.test_artifact_feedback tests.test_operator_report
PYTHONPATH=src /srv/openclaw-you/venv/bin/python3 src/main.py ops-validate callbacks --days 30
```

### RQ-4 - Reader-Facing Evidence And Source Mix Summary

Status: implemented.

Goal: turn proof receipts and source counts into a reader-facing confidence
surface.

Implemented through `summarize_research_brief_evidence(...)`, Research Brief
`Evidence & Source Mix` insertion after receipt creation, Telegram notification
evidence lines, fallback delivery status updates for fallback Markdown, and
focused receipt/digest tests.

The system already has evidence lookup checks, but the operator only sees a
technical audit note or nothing at all. Add a compact evidence section to the
Research Brief and Telegram notification.

Required content:

- local evidence row count;
- Telegram source-link count;
- verification status: `passed`, `needs_review`, or `failed`;
- fallback delivery status;
- source mix top channels;
- one plain-language confidence sentence.

Example:

```text
Evidence: 55 local evidence rows, 28 linked Telegram sources, receipt lookup
passed. Confidence: medium - more watch signals than last week, but no strong
signals yet.
```

Likely touched files:

- `src/proof_receipts.py`
- `src/output/generate_digest.py`
- `src/output/signal_report.py`
- `src/db/research_brief_receipts.py`
- `tests/test_core_research_brief_receipt.py`
- `tests/test_research_brief_receipts.py`
- `tests/test_generate_digest.py`

Acceptance criteria:

- Delivered Research Brief contains a concise evidence/confidence section.
- Section is derived from local rows and receipts, not invented by the model.
- A missing or failed verification is visible to the operator.
- The full JSON receipt remains available through
  `memory inspect-core-receipt --verify-evidence`.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_core_research_brief_receipt tests.test_research_brief_receipts tests.test_generate_digest
```

### RQ-5 - Weekly Artifact Consistency Contract

Status: implemented.

Goal: make Research Brief, Implementation Ideas, Study Plan, Project Insights,
and MVP delivery agree about the same week.

Implemented in `src/output/report_quality.py`, `src/output/mvp_weekly_pipeline.py`,
and `src/output/operator_report.py`: deterministic validation catches Study
Plan vs Research Brief signal contradictions, Project Insights vs Research
Brief project-section contradictions, MVP delivery build-readiness
contradictions, and monthly `operator-report` lists artifact-consistency
warnings.

Build a small contract that shares or validates the weekly run facts:

- week label;
- post count;
- watch/strong/noise counts;
- selected project insights count;
- delivery status;
- MVP status and recommendation;
- report-quality warnings.

This can start as a pure validator rather than a new persistence layer.

Likely touched files:

- `src/output/report_quality.py`
- `src/output/generate_digest.py`
- `src/output/generate_study_plan.py`
- `src/output/map_project_insights.py`
- `src/output/mvp_weekly_pipeline.py`
- `tests/test_report_quality.py`

Acceptance criteria:

- Study Plan cannot claim no Telegram signals if the weekly digest had signal
  evidence.
- Project Insights cannot silently contradict the digest's project section.
- MVP notification cannot claim a build-ready result if Radar result says
  revisit or needs more evidence.
- Operator report can list weekly artifact consistency warnings.

## P1 Tasks

### COST-1 - Internal LLM Cost And Guardrail Sentinel

Status: implemented.

Goal: dogfood the `LLM Cost & Guardrail Budget Sentinel` idea inside this
private system before considering it as a separate product.

Implemented via `src/output/cost_guardrails.py`: existing `llm_usage` rows are
evaluated deterministically for weekly budget thresholds, week-over-week
spikes, highest-cost categories, and suggested downgrade/defer actions.
`cost-stats` and monthly `operator-report` surface the warnings without making
new LLM calls. Configure with `LLM_WEEKLY_COST_BUDGET_USD` and
`LLM_WEEKLY_COST_SPIKE_RATIO`.

Add internal cost guardrails around existing `llm_usage` rows.

Required behavior:

- weekly cost budget threshold, configurable by env;
- per-category cost summary: digest, preference_judge, topic_detection,
  recommendations, study, Radar if available;
- spike detection versus previous week;
- warning in operator report and optionally weekly notification;
- suggested action: reduce candidate count, use cheaper model, or defer Radar
  source expansion.

Likely touched files:

- `src/output/cost_guardrails.py` or existing `src/output/operator_report.py`
- `src/main.py` `cost-stats`
- `src/llm/client.py`
- `src/llm/router.py`
- `tests/test_cost_stats.py`
- `tests/test_operator_report.py`

Acceptance criteria:

- `cost-stats` shows threshold status and highest-cost category.
- `operator-report --month` includes budget/spike warnings.
- No LLM calls are made by the guardrail itself.
- Missing `llm_usage` rows are handled gracefully.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_cost_stats tests.test_operator_report tests.test_llm_client
```

### MEM-1 - Weekly Editorial Memory

Status: implemented.

Goal: preserve what was confusing or useful so future weekly reports can improve
without relying on chat history.

Implemented in `src/output/editorial_memory.py`, `src/main.py`, and
`src/output/operator_report.py`: `memory inspect-editorial-memory --week
YYYY-WNN` writes `data/output/editorial_memory/YYYY-WNN.md`, and monthly
`operator-report` summarizes weeks with editorial memory signals.

Create a small local weekly editorial memory from:

- artifact feedback;
- weekly usefulness logs;
- report-quality findings;
- delivery/receipt warnings;
- source down-rank explanations.

Possible surfaces:

- CLI: `memory inspect-editorial-memory --week YYYY-WNN`
- Markdown sidecar under `data/output/editorial_memory/YYYY-WNN.md`
- operator report section.

Acceptance criteria:

- The memory is operator/system-authored, not a model hallucinated quality log.
- It lists what to keep, change, demote, and test next week.
- It can be read by future report-generation prompts if explicitly wired later.

## Radar Tasks

These tasks must be implemented in:

```text
/srv/openclaw-you/workspace/Demand-to-MVP-Radar
```

### RADAR-1 - Candidate Dossier Output

Status: implemented.

Goal: Radar should produce an honest candidate dossier, not a confident "MVP of
the Week" story when the source mix only supports investigation.

Implemented in `/srv/openclaw-you/workspace/Demand-to-MVP-Radar` and the
Telegram Research Agent bridge: Radar Markdown starts with canonical status,
decision, confidence, and next action; JSON result/selected objects expose the
same `dossier_status`; existing-project context is rendered as apply-to-existing
project; Telegram delivery can display the canonical status.

Change the weekly report shape to:

```text
# Candidate Dossier: <title>

Status: build | focused_experiment | investigate | reject
Decision: <one sentence>
Confidence: high | medium | low | insufficient

## Why This Candidate
## Source Mix
## Evidence
## Missing Evidence
## Next Experiment
## Kill Criteria
## Operator Fit
## Anti-Complexity Guardrail
```

Mapping:

- current `focused_experiment` can remain `focused_experiment`;
- current `revisit_with_evidence_gap` should render as `investigate`;
- current `needs_more_evidence` should render as `investigate` or `reject`
  depending on score and missing evidence;
- `existing_project_context` should clearly say "apply to existing project",
  not "new MVP".

Likely Radar files:

- `demand_mvp_radar/mvp_weekly.py`
- `tests/test_mvp_of_week.py`
- `README.md`
- `docs/CODEX_PROMPT.md`
- `docs/LIVE_SOURCE_PRODUCTION_ROADMAP.md` if task state is tracked there.

Acceptance criteria:

- Markdown report starts with status, decision, confidence, and next action.
- Report JSON exposes the same canonical status/recommendation.
- Existing-project candidates cannot be presented as new standalone MVPs.
- Telegram Research Agent notification can display the canonical status.

Radar verification:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py
```

### RADAR-2 - Single Final Gate And Contradiction Guard

Status: implemented.

Goal: prevent reports that say both "gate passed" and "downgraded".

Implemented in `/srv/openclaw-you/workspace/Demand-to-MVP-Radar` via canonical
LLM synthesis Markdown rewriting: deterministic gates replace contradictory
Decision Gate and Build-Worthy sections, the top recommendation block uses the
gated result, and JSON `result`/`selected` agree with the rendered report.

Current failure:

- W24 report says the focused-experiment gate is satisfied.
- The same report later says the selected candidate was downgraded because it
  lacks two independent non-Telegram evidence sources.

Implement a canonical final gate after LLM synthesis:

- deterministic gates override LLM markdown;
- top report block uses only gated recommendation/status;
- if LLM text contains a contradictory Decision Gate, rewrite or replace that
  section;
- append gate notes under a consistent "Gate Notes" section;
- JSON and Markdown must match.

Likely Radar files:

- `demand_mvp_radar/mvp_weekly.py`
  - `_apply_synthesis_gates`
  - `_append_gate_notes`
  - `_append_report_quality_sections`
  - `_synthesize_or_render`
- `tests/test_mvp_of_week.py`

Acceptance criteria:

- Test fixture with LLM markdown claiming `focused_experiment` but candidate
  failing source mix renders one final status: investigate/revisit.
- Report does not contain contradictory final gate language.
- JSON `recommendation` equals rendered final status/recommendation.
- Gate notes explain the downgrade without fighting the decision block.

### RADAR-3 - Source Mix Truth Surface

Status: implemented.

Goal: make Radar's source mix understandable and operational.

Implemented in `/srv/openclaw-you/workspace/Demand-to-MVP-Radar` and the
Telegram Research Agent bridge: Radar JSON exposes machine-readable
`selected_source_mix` / selected `source_mix`; Markdown includes a compact
Source Mix card near the top; missing credentials remain visible; Reddit API
usage is distinguished from SERP-indexed Reddit pages; GitHub evidence is
labeled as primary or repeated variants; Telegram notifications include the
readiness label.

Required reader-facing fields:

- Telegram seed count;
- selected-candidate external source count;
- selected-candidate external source types;
- run-level external source counts;
- missing credentials/source errors;
- whether Reddit API was actually used or only SERP-indexed Reddit appeared;
- whether GitHub signals are primary evidence or repeated variants only.

Likely Radar files:

- `demand_mvp_radar/mvp_weekly.py`
- `demand_mvp_radar/source_trust.py`
- `tests/test_mvp_of_week.py`
- `tests/test_source_trust.py`

Telegram Research Agent integration files:

- `src/output/mvp_weekly_pipeline.py`
- `tests/test_product_ops.py` or a new focused MVP delivery test.

Acceptance criteria:

- Radar JSON has machine-readable selected-candidate source mix.
- Radar Markdown has a compact source-mix card near the top.
- Telegram notification says whether the result is Telegram-only,
  externally-corroborated, or credential-limited.
- Missing Reddit credentials are visible as missing credentials, not implied
  live Reddit validation.

### RADAR-4 - Radar Report Quality Test Suite

Status: implemented.

Goal: lock the new Radar artifact contract with tests.

Implemented in `/srv/openclaw-you/workspace/Demand-to-MVP-Radar`: focused
report-quality tests lock the Candidate Dossier top block, required sections,
source-mix card, missing evidence, kill criteria, existing-project context, and
no contradictory build-ready claims when source gates fail. LLM Markdown is
sanitized after canonicalization if failed gates leave build-ready claims in
extra sections.

Add tests for:

- candidate dossier heading and canonical status;
- no contradictory focused/downgraded language;
- source mix card present;
- missing evidence and kill criteria present;
- existing-project context rendered as apply-to-existing-project;
- no generated report claims build readiness when source gates fail.

Likely Radar files:

- `tests/test_mvp_of_week.py`
- optional `tests/test_mvp_report_quality.py`
- `demand_mvp_radar/mvp_weekly.py`

Verification:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py tests/test_source_trust.py
```

## Remaining Suggested Execution Order

No active report-quality/Radar/cost/editorial-memory task remains in this
roadmap.

Reasoning:

- Feedback buttons now create the missing taste signal once the operator uses
  live Telegram buttons.
- Reader-facing evidence/source mix is implemented; Radar contradiction fixes
  are implemented.
- Radar handoff work, internal cost guardrails, weekly artifact consistency
  validation, and weekly editorial memory are implemented and locked with
  focused tests.

## Stop Conditions

- Stop if a task starts turning the private operator workflow into a public UI.
- Stop if Radar cannot distinguish source-gated investigation from build-ready
  recommendations.
- Stop if report quality requires a new LLM pass when a deterministic validator
  would work.
- Stop if generated artifacts would be committed as private report data.
