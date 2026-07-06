# AI Knowledge Intelligence Roadmap

Status: active roadmap
Created: 2026-07-06

## Why This Exists

The current Telegram Research Agent no longer matches the operator need.

Observed on 2026-07-06:

- Telegram ingestion works: the weekly ingest collected, normalized, clustered,
  topic-detected, and scored hundreds of recent posts.
- MVP weekly still runs as a separate downstream artifact.
- The weekly digest timer was inactive after 2026-06-22, so Research Brief and
  Implementation Ideas did not run for two weeks until manually restarted.
- When the digest was run manually for 2026-W28, it generated artifacts, but
  report-quality logs still showed reader-facing internal traces such as
  `Matches: ...`, a Study Plan contradiction, and Project Insights saying no
  insights while the Research Brief contained project-like sections.
- Scoring produced `0 strong` while the operator manually found many useful
  posts in AI Telegram groups. This means the current strong/watch/noise scoring
  does not model the operator's actual taste or learning goal.

The product should shift from a project/MVP recommender with a weekly digest into
a personal AI intelligence desk:

```text
all Telegram posts
  -> durable knowledge archive
  -> cheap structured extraction
  -> temporal idea graph
  -> frontier-model weekly analysis
  -> human-readable HTML report
  -> personal read/try/build loop
```

MVP Radar and project implementation ideas remain useful, but they should become
downstream consumers of the knowledge base, not the primary weekly product.

## Product Goal

Build a personal AI Knowledge Intelligence system that reads AI-focused
Telegram channels over time and explains:

- what changed this week;
- which ideas, tools, practices, claims, and risks are evolving;
- what is stale, superseded, hype-only, or becoming production practice;
- which posts are worth reading;
- what the operator should try to develop AI systems engineering skill;
- how current signals compare with the last 30/90 days of channel history.

The main weekly artifact is a designed HTML report. Telegram should deliver a
short notification with a link, not be the primary reading surface.

## Non-Goals

- Do not make MVP Radar the center of the new system.
- Do not use `project_state.md` as the main cross-project memory mechanism.
- Do not rely on `strong/watch/noise` as the only filter for knowledge capture.
- Do not feed thousands of raw posts directly to an expensive frontier model.
- Do not delete old knowledge just because it is stale; mark it as stale,
  superseded, resolved, or hype-only.

## Target Architecture

### 1. Raw Archive

Keep all posts from each configured channel as source material.

Required post-level facts:

- channel;
- message id and Telegram URL;
- posted_at;
- raw text and normalized text;
- links and referenced domains;
- media metadata when available;
- views/reactions when available;
- language;
- ingestion batch id;
- source reliability metadata.

Raw archive is not a report. It is the durable evidence layer.

### 2. Knowledge Atoms

A cheap model processes posts in bounded batches and extracts structured JSON.
It should not write prose reports.

Atom types:

- `tool_release`
- `model_update`
- `workflow_pattern`
- `engineering_practice`
- `benchmark_claim`
- `market_signal`
- `risk_warning`
- `case_study`
- `tutorial_resource`
- `opinion_shift`
- `research_claim`
- `pricing_or_limit_change`
- `regulatory_or_access_change`

Each atom should include:

- source post ids;
- short claim;
- normalized entities;
- evidence quote/excerpt;
- confidence;
- novelty estimate;
- practical utility estimate;
- expiry/staleness hints;
- why it matters for an AI systems engineer.

### 3. Idea Threads

Knowledge atoms are grouped into evolving ideas.

Examples:

- Claude Code / Codex / Cursor workflows;
- eval-driven AI engineering;
- MCP and tool ecosystems;
- agentic coding;
- local-first knowledge bases;
- voice agents;
- AI cost/ROI;
- browser automation;
- open-source model deployment;
- AI implementation barriers in business;
- source-grounded research workflows.

Each thread stores:

- first_seen_at;
- last_seen_at;
- active channels;
- key claims;
- related tools/models;
- related practices;
- contradictions;
- status: `active`, `stale`, `superseded`, `resolved`, `hype_only`,
  `production_pattern`;
- 7/30/90 day momentum.

### 4. Temporal Evolution Layer

The system must explain idea development, not just cluster current posts.

For each high-signal idea:

- how it appeared;
- what early claims were;
- what tools or model releases accelerated it;
- what practical patterns emerged;
- what broke or was contradicted;
- what became production practice;
- what is still only hype.

### 5. Frontier Weekly Analysis

Use the expensive/frontier model only after cheap extraction and thread
aggregation.

The frontier model receives:

- this week's new/changed atoms;
- thread histories for the last 30/90 days;
- strongest sources;
- contradictions;
- stale/superseded candidates;
- operator feedback and reading history.

The frontier model outputs:

- a weekly executive brief;
- what changed compared with last week;
- idea evolution narratives;
- read/try/build recommendations;
- source confidence and caveats.

### 6. HTML Intelligence Report

The primary weekly report is a multi-section HTML artifact.

Required sections:

1. Executive Brief
2. What Changed This Week
3. Idea Evolution Timelines
4. Tools, Models, and Practices
5. Contradictions and Unresolved Claims
6. Read Queue
7. Try This Week
8. Source Map
9. Appendix: grouped source posts

Design requirements:

- human-readable first screen;
- no internal traces such as `Matches: ...`;
- source links visible but not dominant;
- clear typography and section navigation;
- works as a standalone HTML file;
- Telegram notification contains only a short summary and link.

### 7. Personal Learning Loop

The report must actively develop the operator as an AI systems engineer.

Weekly output should include:

- five posts to read;
- two tools/workflows to try;
- one small experiment to run;
- one skill gap to close;
- one reflection question to answer.

Feedback to capture:

- read;
- useful;
- tried;
- applied to a project;
- too shallow;
- missed important post;
- wrong priority;
- not interested.

## Data Model Proposal

Add migrations for these tables or equivalent structures.

### `knowledge_extraction_batches`

- `id`
- `started_at`
- `completed_at`
- `week_label`
- `channel_username`
- `post_count`
- `model`
- `prompt_version`
- `status`
- `error`

### `knowledge_atoms`

- `id`
- `atom_type`
- `claim`
- `summary`
- `source_post_ids_json`
- `source_urls_json`
- `entities_json`
- `tools_json`
- `models_json`
- `practices_json`
- `confidence`
- `novelty_score`
- `practical_utility_score`
- `frontier_relevance_score`
- `operator_relevance_score`
- `staleness_status`
- `first_seen_at`
- `last_seen_at`
- `created_at`
- `updated_at`

### `idea_threads`

- `id`
- `title`
- `slug`
- `summary`
- `status`
- `first_seen_at`
- `last_seen_at`
- `momentum_7d`
- `momentum_30d`
- `momentum_90d`
- `key_entities_json`
- `current_claims_json`
- `superseded_claims_json`
- `contradictions_json`
- `updated_at`

### `idea_thread_atoms`

- `thread_id`
- `atom_id`
- `relation`
- `created_at`

### `operator_learning_actions`

- `id`
- `week_label`
- `action_type`
- `title`
- `source_urls_json`
- `status`
- `feedback`
- `created_at`
- `completed_at`

## Implementation Phases

### Phase 0: Stabilize Weekly Delivery

Purpose: make sure the system reliably runs before product changes continue.

Required work:

- keep `telegram-digest.timer` active;
- add a health check that fails if current-week digest is missing after the
  scheduled run window;
- add a guard against root-owned files under `data/output`;
- log/report if digest timer is inactive;
- make `llm_usage` recording non-blocking and low-contention.

Acceptance:

- `health-check` reports weekly delivery status;
- root-owned output files are detected before scheduled jobs fail;
- current week digest absence is visible without reading journal logs.

### Phase 1: Knowledge Atom Extraction MVP

Purpose: create a cheap structured knowledge layer from Telegram posts.

Required work:

- add schema for extraction batches and knowledge atoms;
- implement CLI command, for example:

  ```bash
  python3 src/main.py knowledge-extract --weeks 4 --model cheap
  ```

- process posts in bounded batches;
- store JSON atoms with source links;
- add deterministic validation for atom shape;
- add inspection command:

  ```bash
  python3 src/main.py memory inspect-knowledge-atoms --week 2026-W28
  ```

Acceptance:

- extraction can backfill at least four weeks;
- every atom cites source post ids/URLs;
- extraction is resumable and idempotent;
- no report prose is generated in this phase.

### Phase 2: Idea Thread Builder

Purpose: group atoms into evolving ideas.

Required work:

- add `idea_threads` and `idea_thread_atoms`;
- implement deterministic first-pass grouping using normalized entities,
  atom type, semantic keywords, and source-channel overlap;
- use cheap LLM only for ambiguous merges;
- compute 7/30/90 day momentum;
- mark stale/superseded candidates.

Acceptance:

- inspection command shows top active threads;
- thread timeline includes source atoms;
- stale status does not delete evidence;
- repeated claims across channels are visible.

### Phase 3: Weekly AI Intelligence HTML Report

Purpose: replace the current Research Brief as the primary user-facing report.

Required work:

- create `output/ai_intelligence_report.py`;
- generate standalone HTML with the required sections;
- use frontier model only over compressed thread context;
- include read/try/build learning actions;
- publish to Telegraph or store local HTML with Telegram notification;
- add report-quality gates that block internal traces.

Acceptance:

- report is readable without Telegram context;
- no `Matches: ...` or internal matching traces;
- report includes source map and appendix;
- report includes personal learning actions;
- Telegram notification links to the full report.

### Phase 4: Feedback and Evaluation Loop

Purpose: make the system learn from the operator.

Required work:

- add feedback buttons or commands for read/useful/tried/missed/noise;
- store feedback against atoms, threads, and report sections;
- add weekly evaluation summary;
- use feedback to update operator relevance scoring.

Acceptance:

- at least five feedback events can be recorded from a report;
- next report can cite prior feedback as personalization context;
- missed-post feedback can be converted into eval examples.

### Phase 5: Downstream MVP and Project Consumers

Purpose: keep MVP Radar and project recommendations, but feed them from the
knowledge base.

Required work:

- MVP Radar reads market-signal and workaround threads;
- Implementation Ideas read engineering-practice and workflow-pattern threads;
- project matching stops depending only on keyword matches;
- downstream artifacts cite knowledge threads and source atoms.

Acceptance:

- MVP weekly can explain which knowledge threads informed candidates;
- implementation ideas do not run when knowledge/project context is stale;
- project insights no longer say "no insights" when the report contains
  project-relevant thread sections.

## First Tasks for Next AI Development Session

Start from `docs/tasks.md`. The first open task is operational because the
project recently failed silently when the digest timer became inactive.

After Phase 0 is complete, proceed to the Knowledge Atom schema and extraction
pipeline. Do not start with prompt tuning or HTML polish; those are downstream
from the knowledge layer.

## Suggested New Session Prompt

```text
Work in /srv/openclaw-you/workspace/telegram-research-agent on master.
Read docs/CODEX_PROMPT.md, docs/tasks.md, and
docs/ai_knowledge_intelligence_roadmap.md.

Start with the first open task in docs/tasks.md. The strategic direction is to
turn the project into an AI Knowledge Intelligence Desk: all Telegram posts ->
knowledge atoms -> temporal idea threads -> weekly HTML intelligence report ->
personal read/try/build loop. MVP Radar and project recommendations are
downstream consumers, not the main product.

Implement end-to-end, add focused tests, update docs only if needed, run
verification, commit and push. Do not add runtime artifacts from data/output.
```
