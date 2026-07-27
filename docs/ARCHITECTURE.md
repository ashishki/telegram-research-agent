# Architecture

Version: 1.0

Last updated: 2026-07-26

Status: proposed canonical architecture for the Personal Research Memory pivot.

Legacy reference: `docs/architecture.md` remains preserved as the report-era
architecture history until PBR-7 completes the doc migration.

## System Overview

`telegram-research-agent` is a private, local-first Telegram research memory
for one operator. Its primary product surface is a grounded assistant that can
search every retained Telegram text post, cite exact Telegram links, distinguish
source evidence from model background, and save useful results only after human
confirmation.

Weekly reports become secondary projections over usage, watch topics,
reactions, saved notes, projects, and experiments.

## Target Flow

```text
Telegram channels
  -> Canonical Archive: every retained post
     -> Archive Search: FTS + metadata, optional future hybrid retrieval
     -> Selective Enrichment: reactions, repeated search hits, watch topics,
        active projects, saved posts
  -> Assistant Router
     -> Archive search
     -> Curated topics
     -> Project context
     -> Saved memory
     -> Web verify
  -> Grounded answer with source links
     -> optional confirmation-gated save/watch/project/action/experiment
  -> secondary Weekly Brief and Knowledge Library projections
```

## Problem Fit And Adoption Reality

| Question | Answer |
| --- | --- |
| Concrete operational pain | W29 reports produced a large report package while all 7 detected personal reactions had 0 linked atoms, 0 linked topics, and 0 ranking effect. |
| Current workaround | Manual Telegram/repo/report inspection to recover posts and verify claims. |
| Why existing process is insufficient | Curated-only retrieval and weekly artifacts hide archive posts that lack Knowledge Atoms. |
| First operator | Private repository owner. |
| v1 adoption failure | The assistant cannot retrieve retained posts with citations, including reacted posts, without atom/topic enrichment. |
| First proof of value | Human-approved retrieval queries return exact Telegram source links from canonical archive FTS. |

## Solution Shape

| Decision | Selection | Justification |
| --- | --- | --- |
| Primary shape | Hybrid deterministic workflow plus bounded tool-use assistant | SQLite archive and FTS are deterministic; synthesis and tool routing need bounded LLM use. |
| Governance level | Standard | Private but recurring, user-facing, RAG/tool-use, scheduled workflows, privacy and cost exposure. |
| Runtime tier | T1 | Bounded local workers/scripts and bot process; no privileged persistent agent runtime needed. |

Rejected lower-complexity option: weekly reports only. W29 showed that report
generation can be structurally complete while failing the operator's actual
search and recall need.

Rejected higher-complexity option: T3 Hermes Agent runtime. Official Hermes
Agent sources checked on 2026-07-26 describe a broad persistent gateway,
skills, and learning-loop runtime. This project only needs pattern reuse:
bounded tools, confirmation gates, messaging interface, and separation of
session history from canonical memory.

Hermes reuse decision: `pattern_only`.

## Two Knowledge Layers

### Layer A - Archive Memory

Canonical source: current SQLite `raw_posts` and `posts` tables where possible.

Rules:

- all retained Telegram text posts are searchable;
- search must not require a Knowledge Atom;
- do not duplicate full post text into a second store unless an ADR and
  measurement justify it;
- preserve channel, message ID, date, URL, language, content hash, and
  duplicate/repost identity;
- normal Telegram posts remain coherent; chunking is for genuinely long posts;
- exact post-level Telegram links survive chunking.

Existing storage fact verified during retrofit: `raw_posts`, `posts`, and
`posts_fts` each contained 3,477 rows in read-only SQLite inspection.

### Layer B - Curated Knowledge

Curated objects:

- Knowledge Atoms;
- cases;
- tools;
- practices;
- claims;
- warnings;
- entities;
- canonical topics;
- Knowledge Notes;
- Watch Topics;
- project links;
- decisions and experiments.

Curated enrichment is selective and may fail independently of archive search.
Priority inputs are reactions, repeated search hits, cited assistant answers,
watch topics, active projects, repeated signals, and manually saved posts.

## Assistant Contract

There is one conversational entrypoint. The user does not choose between
Hermes, PI, Atlas, Radar, or separate search systems.

Minimum read-only tools:

- `get_current_week_label`
- `get_weekly_summary`
- `get_artifact_status`
- `get_workbook_sections`
- `get_action_statuses`
- `search_intelligence_items`
- `search_telegram_archive`
- `search_idea_threads`
- `get_idea_thread`
- `get_project_actions`
- `get_mvp_radar_status`
- `get_feedback_summary`
- `list_marked_posts`
- `get_strategy_reviewer_notes`
- `request_external_verification`

Confirmation-gated proposal tools:

- `propose_knowledge_note`
- `propose_watch_topic`
- `propose_project_link`
- `propose_decision`
- `propose_action`
- `propose_experiment`
- `propose_feedback`

Confirmation-gated write tool:

- `confirm_save_proposal`

Forbidden automatic mutation:

- code edits;
- profile/config/project edits;
- permanent preference changes;
- database mutation outside confirmed save flows;
- external purchase, outreach, or product-build approval.

PI chat suppresses content-free `llm_usage` database writes during read-only
assistant turns. Confirmed memory writes require the canonical
`personal_memory_events` schema to already exist through migrations; the tool
handler does not create production tables lazily.

## RAG Strategy

Implementation order:

1. inventory existing FTS/schema/search behavior;
2. create candidate and human-approved gold queries;
3. establish persistent full-archive FTS baseline;
4. measure retrieval failures;
5. compare embedding/hybrid alternatives only after measured failures;
6. select vector backend through ADR and eval result;
7. implement hybrid retrieval only when approved metrics improve.

Candidate hybrid shape, if later justified:

- metadata filters first;
- FTS/BM25 candidates;
- embedding candidates;
- duplicate/repost collapse;
- freshness handling;
- source diversity;
- small reaction boost;
- project/watch-topic boost;
- bounded reranking;
- citation-safe context assembly.

## Capability Profiles

| Profile | Status | Artifact | Justification |
| --- | --- | --- | --- |
| RAG | ON | `docs/retrieval_eval.md` | The primary product depends on retrieval over the Telegram archive and curated knowledge. |
| Tool-Use | ON | `docs/tool_eval.md` | The assistant uses bounded tools and confirmation-gated proposals. |
| Agentic | ON | `docs/agent_eval.md` | Current PI chat can plan up to 4 read-only tool calls; target router may use a bounded iterative loop. |
| Planning | OFF | not applicable | Persisted plans are not a primary product deliverable. |
| Compliance | OFF | not applicable | No named regulatory framework is selected; privacy/security controls still apply. |

## Deterministic vs LLM-Owned Boundaries

| Subproblem | Owner |
| --- | --- |
| Archive identity, indexing, filters, source URLs, dedupe, receipts, cost limits, confirmation gates | deterministic code |
| Query interpretation, synthesis, contradiction phrasing, selective extraction proposals | bounded LLM use |
| External verification trigger policy for unstable/high-stakes questions | deterministic policy plus optional LLM summarization over bounded sources |
| Vector backend selection | human-approved ADR after evaluation |

## Privacy And Data Boundary

- Local SQLite remains canonical.
- No raw corpus dump is sent to an LLM.
- Retrieval supplies bounded context only.
- No raw post text in ordinary logs.
- Chat transcript is not durable memory automatically.
- External embeddings require explicit data-egress approval.
- External skills are disabled until trust records pass.

## Operations Boundary

Scheduled jobs are ingestion, FTS/index freshness, selective enrichment queue,
reaction fast lane, and secondary weekly projection. Jobs must be idempotent,
receipt-producing, and rollback-aware. Radar failure degrades only the Radar
projection.
