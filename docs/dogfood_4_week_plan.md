# Four-Week Dogfood Plan

Status: blocked pending IRX-14 Report V2 start gate
Created: 2026-07-08
Last updated: 2026-07-13
Owner: private single-user operator workflow

Canonical roadmap: `docs/portfolio_grade_intelligence_roadmap.md`.
Canonical active backlog: `docs/tasks.md`.

## W29 Correction

Do not start Week 1 with the current W29 split artifacts. The reports passed
structural checks but failed reader value: wrong default period, missing
same-run Radar, no visible reaction influence, generic repeated actions,
fragmented threads, and no meaningful visual map. The active correction is
`IRX-0..IRX-14` in `docs/intelligence_report_v2_roadmap.md`.

Dogfood Week 1 may start only when all of the following are true:

- the completed-week period and human dates are visible;
- the real same-run Radar result is included;
- a reaction effect receipt is visible;
- the Brief contains a source-backed weekly thesis and non-generic action;
- at least one useful data visualization is present;
- duplicate primary threads do not dominate Atlas;
- reader-value quality gates pass;
- the report-specific voice feedback flow is verified.

Until then, commands below are diagnostic smoke checks, not dogfood evidence.

## Purpose

Validate whether the AI Intelligence OS is convenient and useful in weekly
life. The goal is not to prove that more automation can be built. The goal is
to prove that the system helps the operator read less raw Telegram, understand
important AI/LLM/engineering changes faster, choose better weekly actions, and
avoid weak MVPs.

Main weekly product test:

1. I understood X.
2. I checked Y.
3. I improved project Z.
4. I decided not to do W.

If the system only generates attractive reports and does not change decisions
or actions, it is not successful.

## Readiness Hygiene Status

Infrastructure hygiene completed before the Report V2 correction:

- isolated the market context lens sidecar for temp/custom seed exports so
  stale repo-level market context cannot contaminate tests or one-off Radar
  seed files;
- kept market context as `context_only` Radar input; it remains ranking and
  validation context, not build-ready evidence;
- redacted Telegram bot dispatch logs so raw operator text, prompts, and
  feedback are not written to normal service logs;
- ignored generated `data/output/**` files by default to reduce accidental
  private artifact commits;
- clarified that `/feedback` and voice feedback create pending drafts first,
  while confirmed feedback memory events are written only after
  `/feedback_confirm`;
- retained the former Week 1 commands below as a diagnostic checklist only.

Verification already run:

```text
tests/test_opportunity_seed_export.py tests/test_market_context_lens.py: 7 passed
focused PI/Hermes/feedback/Radar-adjacent safety suite: 85 passed
py_compile for changed Python files: passed
```

Known remaining cleanup:

- historical tracked `data/output` reports still need a separate
  fixture-vs-private-artifact decision before any index cleanup;
- ad-hoc manual review artifacts under `docs/artifacts/` should stay untracked
  unless the operator intentionally promotes them to documentation.

## Weekly Routine

### Legacy Diagnostic Checklist - Not Dogfood Week 1

Set `WEEK=<YYYY-WNN>` for the target ISO week, then run:

```bash
bash scripts/healthcheck.sh
PYTHONPATH=src python3 src/main.py ops-validate
PYTHONPATH=src python3 src/main.py knowledge-extract --weeks 12 --model cheap
PYTHONPATH=src python3 src/main.py idea-threads --weeks 12
PYTHONPATH=src python3 src/main.py frontier-analysis --week "$WEEK" --lookback-weeks 12 --model strong
PYTHONPATH=src python3 src/main.py mvp-weekly --no-deliver
PYTHONPATH=src python3 src/main.py ai-split-report --week "$WEEK" --skip-refresh --threads-limit 24 --atoms-limit 8 --deliver
```

Telegram diagnostic checks after generation:

```text
/weekly
/actions
/mvp
/strategy
```

Then test feedback, voice fallback/transcription, and one live reaction sync
before treating week-1 metrics as valid.

### Step 1 - Generate Workbook

Run the normal AI Knowledge Intelligence path for the target week.

Expected artifact:

- Weekly AI Intelligence Workbook HTML;
- JSON sidecar;
- generated Obsidian projection if useful;
- MVP Radar section or linked Radar dossier;
- Strategy Reviewer note when feedback exists.

Do not run heavy regeneration only for visual polish during dogfood.

### Step 2 - Hermes Weekly Summary

Hermes should send a short summary:

- three main conclusions;
- one to three actions;
- MVP Radar status;
- workbook link/path;
- feedback reminder.

This should be a concierge message, not a second report.

### Step 3 - Operator Reads Minimum Set

Read:

- Decision Brief;
- two Deep Explanation cards;
- Project Actions;
- MVP Radar section.

Optional:

- Source Map;
- Concept Diagrams;
- Obsidian projection;
- full appendix.

### Step 4 - Complete One Real Action

Complete at least one:

- read item;
- try item;
- project PR/backlog item;
- MVP validation step;
- explicit reject/defer decision.

The action can be small. The important part is that the system changed what
the operator did or decided.

### Step 5 - Send Voice Feedback

Use free-form voice feedback. Suggested prompt:

```text
Что было полезно? Что было мимо? Что попробовал? Что применил к проекту? Что нужно изменить в следующем отчете?
```

The system should parse this into a proposal. Nothing is written until the
operator confirms.

### Step 6 - Confirm Parsed Feedback

Hermes should show:

- memory writes that will be recorded;
- suggestions that require manual approval;
- possible Codex tasks;
- items that will not change anything yet.

No confirmed feedback means no confirmed feedback memory events. Pending
feedback drafts may store the submitted text or transcript until the operator
confirms or discards them.

### Step 7 - Strategy Reviewer

Run Strategy Reviewer after confirmed feedback or on demand.

Review:

- what the system learned about taste;
- what to keep;
- what to demote;
- what to test next week;
- memory-only updates;
- config suggestions requiring approval;
- Codex task suggestions;
- risks / do not change.

### Step 8 - Optional Codex Task

Run at most one Codex task per week unless a production bug blocks the system.

Prefer tasks that improve:

- feedback/action usefulness;
- evidence clarity;
- workflow friction;
- dogfood measurement.

Avoid tasks that add broad features before dogfood evidence exists.

## Metrics

Track weekly:

- `time_to_understand_week_minutes`
- `sections_read`
- `read_items_completed`
- `try_items_completed`
- `experiments_completed`
- `project_actions_created`
- `feedback_events_count`
- `wrong_priority_count`
- `not_interested_count`
- `applied_to_project_count`
- `mvp_build_count`
- `mvp_focused_experiment_count`
- `mvp_investigate_count`
- `mvp_reject_count`
- `decisions_changed_by_system`
- `user_value_score_1_to_5`
- `friction_score_1_to_5`

Optional notes:

- best explanation of the week;
- weakest/most annoying section;
- source or thread that should be promoted;
- source or thread that should be demoted;
- one thing to simplify.

Implementation helper:

- `src/output/dogfood_review.py` can normalize the weekly metrics above and
  write compact private JSON/Markdown review artifacts to an explicit output
  directory.
- PGI-006 adds `weekly-intelligence-scorecard.v1` helpers in the same module:
  build from sanitized Brief/Atlas/dogfood/observation fixtures, validate the
  seven scorecard dimensions, keep unknown metrics explicit, and write compact
  private JSON/Markdown scorecards.
- Generated dogfood review artifacts are private operational outputs and should
  not be committed.

## Weekly Checklist

Use once per week:

```text
Week:
Workbook generated: yes/no
Hermes summary sent: yes/no
Decision Brief read: yes/no
Deep Explanation cards read:
Project Actions reviewed: yes/no
MVP Radar reviewed: yes/no
One real action completed:
Voice feedback sent: yes/no
Parsed feedback confirmed: yes/no
Strategy Reviewer reviewed: yes/no
Codex task run: yes/no
Time to understand week:
User value score 1-5:
Friction score 1-5:
Decision changed by system:
What to simplify next week:
```

## Success Criteria After Four Weeks

Success requires:

- at least four workbook runs;
- at least four feedback sessions;
- at least 8-12 confirmed feedback events;
- at least four real actions, experiments, project decisions, or explicit
  reject/defer decisions;
- at least two reports visibly affected by previous feedback;
- operator can name at least two decisions changed by the system;
- MVP Radar does not produce build/focused_experiment from Telegram-only
  evidence;
- system does not feel like a second job.

## Failure Signals

Treat these as product failures, not just implementation gaps:

- operator stops opening the workbook;
- report is too long;
- Hermes messages are too noisy;
- feedback is too cumbersome;
- no real actions are completed;
- too many Codex suggestions;
- Obsidian note explosion;
- Radar suggests building too eagerly;
- system feels like another workload;
- feedback does not affect later reports;
- PI Assistant answers without evidence references.

## What To Simplify Or Remove If Friction Is High

If `friction_score_1_to_5` is 4 or 5 for two weeks:

- reduce Hermes weekly message to three bullets and one action;
- reduce workbook reading target to Decision Brief plus one explanation card;
- limit Codex suggestions to one per week;
- hide low-confidence project actions unless explicitly requested;
- suppress Obsidian projection sections that are not used;
- shorten feedback confirmation to memory writes plus approval-required
  suggestions;
- defer vector retrieval, multi-profile Hermes, and additional gateways.

If `user_value_score_1_to_5` is 1 or 2 for two weeks:

- inspect wrong-priority and not-interested feedback first;
- demote sources/threads only through explicit confirmed suggestions;
- check whether the workbook is overexplaining weak evidence;
- verify that Project Actions are specific enough to active repos;
- verify that MVP Radar is not crowding out study/project decisions.

## Post-Four-Week Review Template

```text
Review date:
Weeks covered:

1. Did I read less raw Telegram?
2. Did I understand important AI/LLM/engineering changes faster?
3. Which two explanations actually helped?
4. Which actions did I complete?
5. Which project changed because of the system?
6. Which MVP/build idea did I reject or defer because evidence was weak?
7. Which previous feedback changed a later report?
8. What felt like a second job?
9. What should be removed?
10. What should be implemented next?

Decision:
- continue HPI as-is
- simplify Hermes/PI
- focus only on workbook/feedback
- pause new features
- add next implementation layer
```

## Dogfood Start Checklist

Before week 1:

- confirm current week label;
- generate or locate the current workbook;
- verify MVP Radar section/dossier is available;
- verify feedback intake works in text mode;
- verify voice feedback transcription path or choose text fallback;
- verify Strategy Reviewer can run on existing feedback;
- create a place to record weekly dogfood metrics;
- choose one active project to watch closely;
- agree that at most one optional Codex task runs per week.

Do not start by adding multi-profile Hermes, vector retrieval, or new gateways.
