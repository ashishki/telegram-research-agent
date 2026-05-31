# Telegram Channel Intelligence

Status: design, schema migrations, deterministic repeated-claim extraction, source-observation refresh, active-project intelligence links, narrative candidate refresh, inspection CLI, and optional Markdown report surface implemented

## Product Purpose

Telegram Channel Intelligence is a local, project-scoped intelligence layer for
one operator who reads too many curated Telegram channels and needs to know what
is becoming decision-relevant over time.

It solves a different problem than the weekly artifacts:

- `Research Brief`: explains what mattered this week, with evidence and project
  relevance.
- `Implementation Ideas`: turns source-backed weekly signals into small actions
  for active projects.
- `MVP Radar`: uses Telegram as one seed source, then validates an MVP candidate
  against broader demand sources outside this repo.
- `Telegram Channel Intelligence`: tracks cross-week and cross-channel patterns
  behind those artifacts: narratives, repeated claims, source behavior, entity
  links, and project relevance over time.

The layer should answer: "What is taking shape across my channels, who is
repeating it, what evidence backs it, and which active project does it matter
for?" It should not become a generic memory platform, a global knowledge graph,
or a model-authored reputation system.

## Core Concepts

### Narrative

A narrative is an emerging storyline across posts, channels, and weeks. It is
broader than a single topic label and looser than a formal claim.

Examples:

- "Open-source coding agents are moving from demos to local production use."
- "Telegram AI tool channels are shifting from prompt tips toward agent ops."
- "Cheap inference and local models are changing MVP feasibility."

Narratives are derived from scoped evidence. They are not canonical facts. A
narrative must keep links to the posts, claims, channels, topics, and projects
that support it.

### Repeated Claim

A repeated claim is a concrete assertion that appears across multiple sources,
multiple posts, or multiple weeks.

Examples:

- "Claude Code can now handle larger multi-file refactors."
- "A new model is cheaper than the previous frontier model for coding tasks."
- "A specific framework added Telegram integration support."

Repeated claims are only useful when citations are visible. The system should
store claim occurrences separately from the normalized claim text so the operator
can inspect where, when, and how the claim appeared.

### Source Trust Signal

A source trust signal is observed behavior, not model opinion.

Allowed signals:

- a channel repeatedly produces posts that become acted-on, useful, or cited
- a channel often posts uncited claims that never repeat elsewhere
- a channel's posts frequently become low-signal, rejected, or skipped
- a channel's claims are later contradicted by stronger sources or operator
  feedback
- a channel's useful signal rate changes over time

Disallowed signals:

- "this channel is trustworthy" because an LLM says so
- global reputation labels without local observations
- hidden source scores that cannot be traced to rows and counters

### Entity / Topic Graph

The entity/topic graph is a lightweight scoped link layer between:

- entities: tools, companies, projects, people, protocols, repos, models
- topics: existing topic labels and derived narrative themes
- projects: active entries from `src/config/projects.yaml`
- channels and posts
- repeated claims and narratives

This is not a full temporal knowledge graph. It is a retrieval aid for scoped
questions like "show posts where local agents, SQLite, and my telegram project
overlap."

### Project Relevance

Project relevance is the filter that keeps this layer tied to the product. A
claim or narrative is useful only if it can be scoped to:

- an active project from `src/config/projects.yaml`
- a known topic or focus area for that project
- a time window
- cited source posts

Global trend tracking without project relevance should stay outside the default
weekly workflow.

## State Ownership

The design preserves the current SQLite-first memory architecture.

### Canonical SQLite State

The following remain source of truth:

- `raw_posts` and `posts`
- `topics` and `post_topics`
- `post_project_links` and stored project relevance scores
- `signal_evidence_items`
- `signal_feedback` and `user_post_tags`
- `decision_journal`
- `weekly_usefulness_logs`
- generated artifact records such as `digests`, `recommendations`, and
  `study_plans`
- active project definitions from `src/config/projects.yaml`, with SQLite rows
  treated as operational state where the current architecture already does so

Channel Intelligence may reference this state. It must not redefine it.

### Derived / Refreshable State

These surfaces may be stored in SQLite but should be rebuildable:

- candidate narratives
- normalized repeated claims
- claim occurrence clusters
- source observation counters
- entity/topic links
- project intelligence joins
- weekly intelligence rollups

Refresh jobs should be idempotent for a week/time window and should record the
input scope used for the refresh.

### View / Report Only

The following should remain output views, not canonical memory:

- prose trend explanations
- report section summaries
- generated narrative titles when no stable narrative row exists
- "why this matters" text in weekly reports
- operator-facing rankings that only sort derived counters

### Explicit Non-Goal

Do not add a second generic memory engine. No Chroma-wide corpus memory, no
global vector store over every Telegram post, no generic entity platform, and no
model-authored long-term memory outside SQLite. If semantic retrieval is ever
needed, it should index only scoped evidence/intelligence rows and remain a
derived cache.

## Proposed Data Model

INTEL-2 implements the design-reviewed SQLite schema. INTEL-3 implements
deterministic repeated-claim extraction over scoped evidence rows. INTEL-4
implements source-observation refresh from canonical counters only. INTEL-5
implements lightweight entity/topic/project links scoped to active curated
projects. INTEL-6 implements narrative candidate refresh and narrative-claim
links with over-aggregation rejection gates. INTEL-7 implements inspection CLI
for claims, narratives, source observations, and intelligence links. INTEL-8
implements an optional Markdown report renderer that prints citations,
weak-evidence labels, and input row IDs without changing the default weekly
digest.

| Candidate | Purpose | Source of Truth | Refresh Rule | Retrieval Path | Debug Surface |
|---|---|---|---|---|---|
| `channel_narratives` | Stores bounded narrative candidates with stable IDs, title, summary, status, first/last seen week, confidence counters, and optional project scope. | Derived from repeated claims with explicit supporting evidence rows, active project scope, and topic labels. | Implemented by `output.channel_intelligence.refresh_narrative_candidates`; upserts per week/project/topic scope and rejects over-aggregated groups instead of surfacing them as active narratives. | Query by project, topic, week range, source channel, status, and linked claim IDs. | CLI/report row view showing title, scope, supporting post count, channels, first/last seen, linked claims, and evidence links. |
| `channel_repeated_claims` | Stores normalized concrete claims, claim type, first/last seen, occurrence count, channel count, project/topic scope, and evidence strength. | Derived from claim occurrences found in cited posts/evidence; canonical text is refreshable normalization, not fact truth. | Upsert from claim extraction over scoped evidence; merge only when normalized text and entity/topic overlap pass deterministic similarity gates. | Query by project, topic/entity, time window, minimum occurrence count, minimum channel count, and source inclusion/exclusion. | CLI/report view showing normalized claim, all occurrences, source posts, channels, week labels, and whether minimum repetition gates passed. |
| `claim_occurrences` | Stores every observed occurrence of a repeated claim in a post or evidence item. | `raw_posts`/`posts` text plus `signal_evidence_items` excerpts and source metadata. | Append or replace for a refresh window; preserve one row per claim/post/evidence item with extraction version. | Join from claim to posts/evidence by claim ID, project, week, source, and occurrence text. | Inspect command that prints occurrence text, Telegram URL, source channel, posted date, extraction reason, and linked project/topic. |
| `source_observations` | Stores observed source behavior counters by channel/week/window. | Canonical post counts, scoring buckets, evidence selection, feedback, decision outcomes, usefulness logs, and repeated-claim occurrences. | Implemented by `output.channel_intelligence.refresh_source_observations`; rebuilds per channel/week/project/topic scope from canonical rows and never accepts model-authored trust labels. | Query by channel, week range, project/topic, metric name, and direction of change. | Source diagnostics showing useful/acted-on/cited/skipped/rejected counts, low-signal rate, repeated-claim participation, and raw counter inputs in `counters_json`. |
| `intelligence_entity_links` | Links entities/topics to posts, claims, narratives, projects, and channels. | Existing topic and project labels on scoped evidence plus repeated-claim topic/project scope. | Implemented by `output.channel_intelligence.refresh_intelligence_links`; refreshes rows by extractor version and scope, and keeps links lightweight. | Query by entity/topic plus project/time/source; use as a join table, not as a standalone memory pool. | Inspector listing entity label, entity type, linked object type/id, source row, extractor version, and confidence/reason. |
| `project_intelligence_links` | Records why a claim, source observation, or entity link is relevant to an active project. | `src/config/projects.yaml`, `projects.active`, scoped evidence, repeated claims, and source observations. | Implemented by `refresh_intelligence_links`; preserves only links to active curated projects unless historical debug behavior is explicitly added later. | Query by project first, then narrative/claim/topic/time/source. | Project diagnostics showing linked claims/source observations/entity rows, matching reasons, evidence row IDs, and dropped candidates. |
| `narrative_claim_links` | Many-to-many link between narratives and repeated claims. | Derived overlap between active narrative candidates and repeated claims in the same active project/topic scope. | Implemented by `refresh_narrative_candidates`; links are rebuilt for the narrative and require supporting evidence row IDs. Rejected narratives do not receive claim links. | Join from narrative to concrete claims and from claim to broader storyline. | Inspector showing link reason, shared evidence count, shared entities/topics, and confidence counters. |
| `channel_intelligence_weekly_rollups` | Materialized weekly rollup for report generation and fast inspection. | Derived only from the candidate tables above plus canonical evidence and feedback. | Rebuild for a week label after ingestion/scoring/evidence refresh; disposable cache. | Query by week, project, topic, source, and report section. | Report/debug output showing exact input row IDs used for each rollup item. |

Naming should stay close to this table unless an implementation task finds an
existing local convention that is clearer.

## Pipeline And Retrieval Flow

### Feed From Weekly Processing

The layer should run after existing weekly ingestion, normalization, scoring,
project relevance, evidence recording, and feedback sync.

Input sequence:

1. Ingest Telegram posts into `raw_posts` and `posts`.
2. Assign topics and project links.
3. Score posts and write evidence to `signal_evidence_items`.
4. Sync reactions, tags, decision feedback, and weekly usefulness logs.
5. Refresh Channel Intelligence derived rows for the week/project/topic scope.
6. Generate reports from explicit retrieved rows, not from hidden prompt memory.

The refresh should prefer evidence rows and high-signal/project-linked posts. It
should not process the whole Telegram corpus by default.

### Scoped Retrieval Contract

Retrieval must remain scope-first:

1. project
2. topic or entity
3. time window
4. source channel
5. evidence strength / repetition gate
6. decision state
7. broader fallback only when the report explicitly says evidence is sparse

Output generators may use this layer only by requesting concrete row sets with
citations. A prompt may receive narrative or claim summaries only alongside the
supporting evidence rows and source URLs. Missing evidence must be visible as a
report condition, not hidden by prompt wording.

### Evidence Rules For Outputs

- A repeated claim should not be presented as repeated unless it has at least two
  claim occurrences across either distinct posts, distinct weeks, or distinct
  channels.
- A narrative should show supporting posts/channels and linked claims; otherwise
  it is a weak candidate.
- Source trust language must name the observed behavior and counter window.
- Project relevance must cite the project match reason or linked evidence rows.
- Report prose must never imply fact verification unless the stored evidence
  actually supports that status.

## Operator Surfaces

The operator should be able to inspect the layer from CLI and reports before any
automation depends on it.

### CLI / Debug Questions

Expected future inspection commands should answer:

- Which narratives are growing for project `telegram-research-agent` in the last
  four weeks?
- Which claims repeated across at least two channels this month?
- Which claims are repeated by one channel only and should be treated as weak?
- Which channels produced cited or acted-on evidence for a project?
- Which channels generated many low-signal or rejected items?
- Which entities connect a claim to an active project?
- Why was this narrative linked to this project?
- What evidence rows were used in this Channel Intelligence rollup?

### Report Surfaces

Research Brief may show:

- "Emerging narratives" for active projects
- repeated claims with citations and caveats
- source behavior notes when they are counter-backed
- missing-evidence warnings for weak narratives

Implementation Ideas may use:

- repeated claims as supporting context for an action
- project intelligence links to select only scoped ideas
- source observations to avoid overusing noisy channels

MVP Radar may use:

- Telegram repeated claims and narratives as seed context only
- explicit source links and weak-evidence flags when exported

The optional separate Channel Intelligence report may show:

- narrative leaderboard by project and week
- repeated-claim table with occurrences and citations
- source observation table with counters, not reputation prose
- entity/topic graph slices for active projects
- "watch next week" items with explicit missing evidence

Implemented surface:

```bash
python3 src/main.py channel-intelligence-report --week 2026-W22 --project telegram-research-agent
```

This renders Markdown from existing derived rows only. It does not refresh data,
deliver Telegram messages, or alter the default Research Brief.

## Observability And Quality Gates

### Claim Quality

Minimum gates before a claim can be called repeated:

- at least two occurrence rows
- every occurrence has a source channel, posted date, and Telegram URL or
  evidence item reference
- occurrence text is inspectable
- extraction version is recorded
- same-source repetition is labeled differently from cross-source repetition

### Narrative Quality

Minimum gates before a narrative can be surfaced as strong:

- at least two supporting evidence rows or one evidence row plus one repeated
  claim
- source/channel spread is visible
- first/last seen weeks are visible
- project relevance reason is visible when shown inside a project section
- stale narratives are marked stale instead of reworded as current

### Source Trust Boundaries

Source trust signals must be phrased as observations:

- good: "`@channel` produced 4 cited project-scoped evidence items in 2026-W20
  through 2026-W23."
- bad: "`@channel` is trustworthy."

Quality gates:

- every trust signal points to source observation counters
- counters distinguish acted-on, cited, skipped, rejected, and low-signal rows
- no source trust status is written from model-only judgment
- low sample sizes are flagged

### Over-Aggregation Detection

The implementation should fail or warn when:

- one narrative links unrelated entities with no shared evidence
- one repeated claim merges different claims because the wording is similar
- a report item has a narrative/claim ID but no supporting post or evidence row
- broad fallback results are mixed into project-scoped output without a visible
  fallback label
- one noisy source dominates a narrative without cross-source evidence

### Minimum Tests / Fixtures

Before runtime implementation is accepted, add fixtures with:

- two active projects
- three channels
- two weeks of posts
- one cross-channel repeated claim
- one same-channel repeated claim
- one weak single-occurrence claim
- one narrative linked to a project through evidence
- one narrative rejected as over-aggregated
- source observation counters from acted-on, skipped, cited, and rejected rows

Minimum test contracts:

- claim repetition requires citations and occurrence counts
- project-scoped retrieval does not leak rows from another project
- source observations are derived from canonical state only
- source trust output uses counter-backed language
- narrative/claim links expose supporting row IDs
- weekly rollup can be rebuilt idempotently for the same week
- weak evidence appears as weak evidence, not confident prose

## Incremental Implementation Plan

Future implementation should be split into bounded tasks:

1. `INTEL-2`: implemented. Design-reviewed SQLite migrations exist for claim,
   narrative, link, source observation, and rollup tables. Migration tests and
   direct SQLite insertion cover the schema; no report behavior changes.
2. `INTEL-3`: implemented. Deterministic repeated-claim extraction over scoped
   evidence rows classifies cross-channel, same-channel, and weak
   single-occurrence claims separately.
3. `INTEL-4`: implemented. Source observation refresh derives reproducible
   counters from posts, evidence, feedback, tags, decisions, usefulness logs,
   and repeated-claim occurrences; it writes raw input IDs to `counters_json`
   and no model-authored trust labels.
4. `INTEL-5`: implemented. Lightweight entity/topic/project link refresh
   derives links from scoped evidence, repeated claims, and source observations;
   project intelligence rows are limited to active curated projects.
5. `INTEL-6`: implemented. Narrative candidates are derived from repeated
   claims in the same active project/topic scope, active rows include
   supporting evidence IDs and narrative-claim links, and over-aggregated
   groups are stored as `rejected` without links.
6. `INTEL-7`: implemented. `memory inspect-channel-intelligence` prints source
   of truth, refresh rule, retrieval path, debug surface, scoped claims,
   narratives, source observations, entity links, and project links.
7. `INTEL-8`: implemented. `channel-intelligence-report` renders optional
   Markdown from derived rows and includes citations, weak-evidence labels, and
   input row IDs.

Dependencies:

All initial Channel Intelligence implementation tasks are complete. Future work
should come from observed operator usage rather than expanding the layer by
default.

Keep separate unless explicitly needed:

- `ENT-1`: research brief receipt
- `OPS-1`: live Telegram reaction sync validation
- `OPS-2`: deployed inline callback validation
- `QUAL-1`: weekly quality trend reporting

These may provide useful counters or verification surfaces later, but they are
not prerequisites for the first Channel Intelligence schema and extraction work.

## Non-Goals

- No application code changes in this design task.
- No migrations in this design task.
- No new prompt behavior in this design task.
- No changes to scoring, retrieval, delivery, bot callbacks, or report
  generation in this design task.
- No generic memory framework.
- No source trust claims based on model judgment alone.
