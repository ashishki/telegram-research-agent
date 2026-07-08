# AI Intelligence Workbook Roadmap

Status: active planning roadmap
Created: 2026-07-07
Owner: private single-user operator workflow

## Why This Exists

The system is no longer a Telegram digest bot.

The current implemented path already supports durable Telegram ingestion,
Knowledge Atoms, Idea Threads, frontier analysis, AI Intelligence HTML,
AI Decision Intelligence visual HTML, Obsidian export, AI report feedback,
artifact feedback, reaction sync, MVP Radar bridge, and downstream knowledge
consumers.

The next product step is not more digest polish. The weekly artifact should
become a personal AI intelligence workbook:

```text
Telegram posts
  -> durable archive
  -> cheap Knowledge Atoms
  -> temporal Idea Threads
  -> frontier-model weekly synthesis
  -> rich Weekly AI Intelligence Workbook HTML
  -> generated Obsidian projection
  -> read / try / build / feedback loop
  -> Strategy Reviewer suggests system improvements
  -> human applies accepted changes through Codex
```

The operator reads many AI, LLM, and engineering Telegram channels. The weekly
artifact must show what really changed, explain complex ideas plainly, connect
signals to active projects, propose concrete read/try/build actions, expose
evidence strength and caveats, accept feedback, and suggest implementation
tasks. It must not silently rewrite code, config, profile, projects, prompts,
or Radar gates.

## What The Workbook Is

A Weekly AI Intelligence Workbook is a standalone HTML artifact that the
operator can study during the week. It is decision-first on the first screen and
deep where the evidence deserves depth.

Required top-level sections:

1. Decision Brief
2. Strong Signals
3. Deep Explanation Cards
4. Concept Diagrams
5. Project Implementation
6. MVP Radar Section
7. Read / Try / Build Plan
8. Feedback Section
9. Appendix / Audit

The first screen must stay concise. Deep sections should use progressive
disclosure: cards, collapsible details, anchors, summary first, appendix last.
The goal is a rich weekly workbook, not an unreadable wall of text.

## What It Is Not

The workbook is not a digest.

A digest answers "what was posted?". The workbook answers:

- what changed;
- why it matters;
- what is weak or speculative;
- what to read;
- what to try;
- what to build or defer;
- which claims need verification;
- how this affects active projects;
- what feedback should shape next week.

The workbook is also not MVP Radar.

MVP Radar remains a conservative opportunity scout. Its job is only:

```text
Is there a real MVP opportunity here, validated beyond Telegram?
```

AI Intelligence/KIR owns study, weekly AI narrative, project implementation
ideas, skills, cultural interest, and the read/try/build learning loop. Radar
may consume Knowledge Thread-backed seeds, but it must keep its external
evidence gates.

## Post-KIR HPI Layer

After KIR-Q0..KIR-Q13, the next roadmap layer is HPI: Hermes / Personal
Intelligence Assistant / Dogfood.

The Workbook remains the main weekly artifact. Hermes does not replace it.
Hermes is the Telegram-facing concierge that helps the operator open the
workbook, see the short weekly summary, choose one to three actions, route
questions to PI Assistant, collect feedback, show Strategy Reviewer notes, and
prepare Codex-ready prompts for manual approval.

PI Assistant is the interactive Q&A layer over curated intelligence memory:
workbook sections, claim cards, Knowledge Atoms, Idea Threads, project actions,
feedback events, MVP Radar dossiers, and Strategy Reviewer notes. It must cite
source refs or say insufficient evidence. It must not run default raw RAG over
all Telegram posts.

Strategy Reviewer remains advisory. It can suggest memory-only updates,
approval-required config changes, and Codex tasks, but it must not edit code,
prompts, `profile.yaml`, `projects.yaml`, or Radar gates.

The four-week dogfood protocol validates usefulness before more complexity is
added. Success means the operator can name decisions/actions changed by the
system. Passing tests or generating richer HTML is not enough.

Detailed HPI docs:

- `docs/hermes_pi_assistant_roadmap.md`
- `docs/dogfood_4_week_plan.md`

## Workbook Structure

### 1. Decision Brief

Purpose: one-screen orientation.

Fields:

- what changed;
- what matters;
- what to do;
- what to defer;
- evidence confidence;
- top caveat;
- feedback confidence.

Acceptance:

- the first viewport gives an operator decision without scrolling through
  source lists;
- weak weeks say "do not build" or "study only" plainly;
- no single-source claim is phrased as an established trend.

### 2. Strong Signals

For the strongest 3-5 signals, each card should show:

- source post / atom / thread reference;
- what happened;
- why it matters;
- simple explanation;
- evidence strength;
- caveats;
- what to study;
- what to try;
- project implications;
- source links.

### 3. Deep Explanation Cards

Selected complex topics should answer:

- What is this?
- Why now?
- How it works in plain language.
- Where is the hype?
- What should I do with this?
- What should I not do?

These cards are for comprehension, not for unsupported persuasion. Every strong
claim still needs atom/source provenance and caveats.

### 4. Concept Diagrams

Use deterministic local diagrams first. Prefer Archify-style dataflow or
concept diagrams generated from local structured IR.

P0 rules:

- diagrams explain concepts or flow;
- diagrams are not evidence;
- no uncontrolled internet image scraping;
- generated images are optional future layer, not P0.

### 5. Project Implementation

For existing repos, show:

- project name;
- related signal/thread;
- why it matters;
- concrete tiny PR or backlog item;
- acceptance criteria;
- effort estimate;
- risk/caveat;
- source atom links.

Project implication logic must remain conservative. Broad matches like `AI`,
`workflow`, `evidence`, and `tool` must not become project decisions.

### 6. MVP Radar Section

This section is not a sales pitch. It should show:

- selected candidate;
- status: `build`, `focused_experiment`, `investigate`, or `reject`;
- why not build yet if evidence is weak;
- source mix;
- KIR evidence present or missing;
- missing external evidence;
- next validation step;
- kill criteria.

Weak candidates must clearly say "do not build".

### 7. Read / Try / Build Plan

Weekly target:

- 5 read targets;
- 2 try targets;
- 1 experiment;
- 1 skill gap;
- 1 reflection question.

Each item should have a stable target reference for feedback.

### 8. Feedback Section

The end of the workbook should say what to react to and what to say in voice
feedback.

Russian voice prompt example:

```text
Что было полезно? Что было мимо? Что попробовал? Что применил к проекту? Что нужно изменить в следующем отчете?
```

### 9. Appendix / Audit

Appendix belongs last:

- source map;
- atoms;
- thread timeline;
- Archify knowledge-flow;
- JSON sidecar path;
- quote verification status;
- claim cards;
- raw provenance references.

## Reaction Feedback Rule

The operator should not need to remember emoji semantics.

Product rule:

- any visible operator reaction on a Telegram source post means
  `operator_marked_interesting`;
- raw emoji is stored for audit;
- absence of reaction means unknown, not negative;
- negative reaction can be used only if explicit and visible, but it is not a
  P0 dependency.

Before changing ranking behavior, validate whether Telethon can actually see
the operator's own reactions across selected channels. If only aggregate
reaction counts are visible, those counts must not be treated as personal
feedback.

P0 validation command:

```bash
python3 src/main.py sync-reactions --days 14 --limit 300
python3 src/main.py ops-validate reaction-sync --days 14
```

Validation plan:

- pick 5 configured channels;
- add multiple reactions from the operator account;
- run sync;
- verify stored state contains personal reactions only;
- verify unknown/no reaction does not create negative feedback;
- add a report section "Posts you marked this week."

## Voice Feedback Intake

Desired flow:

```text
Telegram voice message
  -> transcription
  -> LLM feedback parser
  -> structured summary
  -> bot asks for confirmation
  -> after confirmation, write feedback events
  -> next report uses feedback
  -> Strategy Reviewer suggests system improvements
```

Only confirmed feedback should affect memory.

Parser fields:

- `useful_items`
- `not_interested_items`
- `wrong_priority_items`
- `too_shallow_items`
- `tried_items`
- `applied_to_project_items`
- `missed_important_posts`
- `project_corrections`
- `source_trust_up`
- `source_trust_down`
- `preference_suggestions`
- `config_suggestions`
- `codex_task_suggestions`

Confirmation message shape:

```text
I understood your feedback as:
Useful:
...
Wrong priority:
...
Project corrections:
...
Suggested memory updates:
...
Requires Codex:
...
Confirm?
```

Allowed after confirmation:

- write `ai_report_feedback_events`;
- write artifact feedback;
- write weekly editorial memory;
- record decision journal entries;
- mark action as tried/applied/deferred/rejected;
- downrank a specific thread/atom/action in the next report;
- create task suggestions.

Requires explicit human approval:

- edit `profile.yaml`;
- edit `projects.yaml`;
- edit scoring thresholds;
- edit reaction mapping;
- edit prompt contracts;
- run Codex;
- modify source code;
- commit changes.

## Strategy Reviewer

Strategy Reviewer runs after weekly feedback or on demand. It is advisory-only.

Jobs:

- summarize what the operator liked and disliked;
- detect recurring wrong priorities;
- detect project/profile descriptor gaps;
- propose report-generation improvements;
- propose config changes;
- propose Codex-ready tasks;
- separate memory-only changes from code/config changes;
- never modify code or config itself.

Output sections:

1. What I learned about your taste this week.
2. What to keep.
3. What to demote.
4. What to test next week.
5. Suggested memory updates.
6. Suggested config changes requiring approval.
7. Suggested Codex tasks.
8. Risks / do not change.

Codex task suggestions should include:

- title;
- why;
- files likely touched;
- acceptance criteria;
- verification commands.

## Claim Evidence Discipline

P0/P1 report quality work should keep these rules:

- `evidence_quote` must be checked against cited post content;
- if exact match fails, mark `verification_status=needs_review`;
- unverified quote cannot be used as strong evidence;
- single-source or weak evidence should use cautious wording.

Evidence tiers:

- `primary_source`
- `author_commentary`
- `user_anecdote`
- `benchmark_claim`
- `vendor_claim`
- `tutorial`
- `case_study`
- `rumor/speculation`

Claim cards should show:

- claim;
- atom IDs;
- source URLs;
- quote verification;
- source count;
- evidence tier;
- caveat;
- expiry/staleness;
- next verification step.

Wording guardrails:

- use "signal suggests", "worth watching", and "needs verification";
- avoid "proves", "dominates", and "market has shifted" unless evidence
  thresholds pass.

## Obsidian Projection

Obsidian remains a generated projection, not source of truth.

Do not create one note per Telegram post.

Workbook-loop note types:

- weekly workbook note;
- idea thread note;
- strong signal note if promoted;
- read queue note;
- experiment note;
- project watch note;
- strategy reviewer note;
- feedback summary note.

Noise to avoid:

- one note per source post;
- channel note explosion;
- tool/model note for every extracted term;
- copying the whole HTML into Markdown.

## KIR-backed Radar Contract

Telegram Research Agent exports Knowledge Thread-backed opportunity seeds with
provenance fields:

- `source_kind`
- `source_urls`
- `knowledge_thread_slug`
- `knowledge_thread_title`
- `knowledge_thread_status`
- `knowledge_atom_types`
- `source_atom_ids`

Demand-to-MVP Radar must preserve these fields on import and expose KIR-aware
source mix state:

- `kir_source_kind`
- `kir_thread_slug`
- `kir_thread_status`
- `kir_source_atom_count`
- `kir_has_fresh_thread`
- `kir_gate_status`

In Telegram-seeded weekly mode, `build` or `focused_experiment` should require:

- fresh Knowledge Thread evidence;
- `source_atom_ids`;
- source URLs;
- decision-grade external evidence;
- operator fit;
- no blocking risk/profile mismatch.

Telegram-only remains `investigate` or `reject`. Live source intelligence is
context-only and does not satisfy external evidence gates. Existing-project
context should render as `investigate/apply-to-existing`, not a new standalone
MVP.

## Roadmap

### P0 - Contract And Safety Gates

Goal: make the next implementation work small, testable, and evidence-safe.

Tasks:

- KIR-Q0 documentation and task planning.
- KIR-Q1 preserve KIR provenance in Radar import.
- KIR-Q2 add KIR-backed Radar gate.
- KIR-Q3 simplify reaction feedback.
- KIR-Q4 voice feedback intake.

Acceptance:

- roadmap exists and task queue is explicit;
- Radar import preserves Knowledge Thread provenance;
- Telegram-seeded build/focused_experiment cannot pass without KIR provenance
  plus external corroboration;
- any visible operator reaction can become positive implicit feedback only
  after live personal-reaction validation;
- voice feedback writes no memory until operator confirmation.

### P1 - Workbook Generation And Feedback Effects

Tasks:

- KIR-Q5 feedback affects next report;
- KIR-Q6 Weekly Intelligence Workbook HTML;
- KIR-Q7 Deep Explanation Cards;
- KIR-Q8 concept diagrams with Archify/local renderer;
- KIR-Q9 Project Implementation section;
- KIR-Q10 MVP Radar section embedded into workbook.

Acceptance:

- workbook has the required sections and concise first screen;
- strongest signals have simple explanations, caveats, and source links;
- read/try/build plan has stable feedback targets;
- project PR/backlog suggestions include acceptance criteria and caveats;
- MVP Radar section explains do-not-build states clearly.

### P2 - Reviewer, Evidence Hardening, Projection Refinement

Tasks:

- KIR-Q11 Strategy Reviewer agent;
- KIR-Q12 quote verification / evidence tiers / claim cards;
- KIR-Q13 Obsidian workbook projection refinements.

Acceptance:

- Strategy Reviewer creates advisory memory/config/code task suggestions
  without applying them;
- claim cards expose verification and evidence tier;
- Obsidian projection supports workbook/read/try/build without note explosion.

## Files Likely Touched

Telegram Research Agent:

- `src/ingestion/reaction_sync.py`
- `src/db/ai_report_feedback.py`
- bot voice/text handlers
- new feedback parser module
- `src/output/frontier_analysis.py`
- `src/output/ai_visual_report.py`
- optional new `src/output/ai_workbook_report.py`
- `src/output/mvp_weekly_pipeline.py`
- `src/output/obsidian_export.py`
- `src/output/opportunity_seed_export.py`
- `tests/test_reaction_sync.py`
- `tests/test_ai_report_feedback.py`
- `tests/test_ai_visual_report.py`
- `tests/test_mvp_weekly_pipeline.py`
- `tests/test_obsidian_export.py`

Demand-to-MVP Radar:

- `demand_mvp_radar/sources/telegram_research_agent.py`
- `demand_mvp_radar/mvp_weekly.py`
- `tests/test_mvp_of_week.py`
- `tests/test_mvp_report_quality.py`

## Test Commands

Planning/docs check:

```bash
git diff --stat
rg "KIR-Q0|KIR-Q1|KIR-Q13|Weekly AI Intelligence Workbook|KIR-backed Radar Contract" docs
```

Telegram Research Agent focused tests when code changes:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_opportunity_seed_export tests.test_mvp_weekly_pipeline
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_reaction_sync tests.test_ai_report_feedback tests.test_ai_visual_report tests.test_obsidian_export
```

Radar focused tests for KIR-Q1/KIR-Q2:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py tests/test_mvp_report_quality.py
```

## Risks And Open Questions

### Evidence Risk

The workbook can make a weak Telegram idea feel stronger than it is if the
explanation is clearer than the evidence. Deep Explanation cards must not make
weak claims sound proven.

Rules:

- every strong claim needs evidence tier, source links, quote verification
  status, caveat, and "what would change my mind";
- weak/single-source evidence should use cautious wording;
- explanation depth does not upgrade evidence strength.

### Feedback Risk

The system may fail to learn from the operator if feedback is too hard to give,
or it may overfit to one mood/week if feedback is applied too broadly.

Rules:

- reactions and voice feedback are scoped memory first;
- standing profile/project/config changes require explicit operator approval;
- no-feedback weeks must state low personalization confidence.

### Action Risk

The operator can read a beautiful workbook and still change nothing.

Rules:

- every action needs a target ref and an expected outcome;
- the workbook should ask for outcome feedback: tried, useful,
  wrong_priority, applied_to_project, not_interested, or deferred;
- success is judged by completed reads, experiments, and project/backlog
  changes, not by report length or visual quality.

### KIR/Radar Gate Risk

Demand-to-MVP Radar currently imports only a limited metadata whitelist. If it
drops `source_kind`, `knowledge_thread_slug`, `knowledge_thread_status`,
`knowledge_atom_types`, `source_atom_ids`, or `source_urls`, then a reliable
KIR-backed Radar gate cannot be implemented.

Rules:

- KIR-Q1 must preserve Knowledge Thread provenance before KIR-Q2 adds gates;
- external-first Radar runs should still work without KIR evidence;
- Telegram-seeded weekly recommendations need fresh Knowledge Thread
  provenance plus source atom evidence before `build` or `focused_experiment`
  is allowed.

### Reaction Semantics Risk

Different emoji meanings are too much cognitive load for the operator.

Rules:

- any visible personal operator reaction means "interesting";
- no reaction means unknown, not negative;
- reason classification can be inferred later and confirmed through feedback.

### Voice Feedback UX Risk

If feedback requires forms, labels, or many buttons, the operator will stop
using it.

Rules:

- voice feedback is free-form;
- the system summarizes it into structured fields;
- memory writes happen only after confirmation.

### Strategy Reviewer Self-Modification Risk

Strategy Reviewer may suggest code/config changes, but must not apply them.

Rules:

- it can generate Codex-ready tasks;
- the operator decides what to run;
- code, prompts, scoring thresholds, `profile.yaml`, and `projects.yaml` are
  approval-only.

### Diagram Trust Risk

Archify/concept diagrams explain mechanisms. They do not prove that a claim is
true.

Rules:

- diagrams must be labeled explanatory;
- evidence comes from source atoms, verified quotes, and external
  corroboration;
- visual polish must not hide a thin evidence base.

### Generated Obsidian Noise Risk

Workbook projection can create too many notes.

Rules:

- prefer weekly workbook, idea thread, strong signal when promoted, read queue,
  experiment, project watch, strategy reviewer, and feedback summary notes;
- do not create one note per Telegram post;
- do not copy the whole HTML into Markdown.

### Evaluation Gap

Passing unit tests does not prove the system is useful. After several weeks,
human outcomes matter more than structure.

Measure:

- read items completed;
- experiments tried;
- project/backlog changes made;
- wrong-priority items reduced;
- missed-important-post feedback decreasing.

Operator shorthand:

1. Evidence risk - красиво объяснили слабую идею.
2. Feedback risk - система не учится от тебя.
3. Action risk - отчет прочитан, но ничего не изменилось.

## Stop Conditions

Stop and ask for operator review if:

- a task would weaken evidence gates to make reports look more useful;
- a task would treat no reaction as negative feedback;
- a task would let LLM feedback modify code, prompts, scoring, `profile.yaml`,
  or `projects.yaml` without explicit confirmation;
- a task would make MVP Radar produce `build` or `focused_experiment` from
  Telegram-only evidence;
- a task would turn the private operator workflow into public SaaS or
  multi-user UI;
- a task would add visual polish before claim evidence, feedback loop, and
  action usefulness are measurable;
- a task would create note explosion in Obsidian;
- a task would commit generated private reports or unrelated dirty worktree
  changes.

## Four-Week Success Criteria

After four weekly Workbook runs, the system is better only if:

- the operator completed at least 8-12 feedback actions total;
- at least 50% of shown actions have an outcome: `tried`, `useful`,
  `wrong_priority`, `applied_to_project`, `not_interested`, or `deferred`;
- at least 4 experiments or project/backlog items were created from the
  workbook;
- the report can explain what prior feedback changed in the current week;
- strong claims include source links, evidence tier, caveat, and verification
  status;
- MVP Radar did not produce `build` or `focused_experiment` without external
  corroboration;
- the operator can name at least 2 decisions the system changed: what to study,
  what to try, what to build, what to ignore, or what not to build.

## Non-Goals

Do not:

- build a public SaaS;
- add multi-user UI;
- make Telegram the main reading surface;
- make Obsidian runtime source of truth;
- auto-edit code/config from LLM feedback;
- weaken Radar evidence gates;
- make project implications broad keyword matching again;
- treat no reaction as negative;
- treat live source intelligence as decision-grade external evidence;
- add uncontrolled image scraping in P0;
- feed thousands of raw posts directly to a frontier model;
- add a generic global memory/vector store before scoped evidence retrieval is
  proven insufficient.
