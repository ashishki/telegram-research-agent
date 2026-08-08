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

Runtime state note: as of 2026-07-29 the legacy Telegram bot and Report V2
weekly timer are stopped and disabled. See `docs/PRODUCT_OPERATING_MODEL.md`
for the active operating model and consolidation plan.

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

## Research Session Target

The desired polished assistant is a project-aware research session, specified
in `docs/personal_research_memory_product_contract.md` and scheduled in
`docs/tasks.md` as PRM-21 through PRM-23. PRM-22 provides the fixture-first
linked-source resolver/cache layer. PRM-23 provides the bounded fixture-first
`memory research` planner/CLI above the current `memory ask` preview:

```text
Question
  -> project/context interpretation
  -> Telegram archive retrieval with deterministic SQLite FTS query variants
  -> approved linked-source fetch/cache
  -> approach comparison and contradiction check
  -> grounded synthesis with deeper-reading path
  -> optional confirmation-gated memory proposal
```

This requires RAG, but RAG is not enough by itself. The system also needs
linked-source research, project-context routing, bounded planning, synthesis,
and evals. SQLite FTS remains the baseline retrieval backend; vector or hybrid
retrieval is still a PRM-8 conditional decision that requires measured FTS
failure and human-approved backend adoption.

The current PRM-23 planner uses deterministic synthesis and fake/fixture linked
source paths only. The archive layer performs bounded query decomposition and
acceptance filtering over the existing SQLite FTS backend; it is not approval
for live web research, provider egress, service start, production DB writes,
durable linked-source cache writes over private production inputs, dogfood, or
vector/backend adoption.

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
- `analyze_project_context`
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

Full product RAG is required before operator dogfood. The required path is
formalized as PRM-24 through PRM-28: gold eval set, citation-safe context pack,
hybrid/vector ADR and privacy budget, approved retrieval implementation, and
product chat acceptance gate. This does not by itself approve embeddings,
provider egress, production migrations, or a vector backend; those remain gated
by the ADR, eval result, and explicit human approval.

Implementation order:

1. inventory existing FTS/schema/search behavior;
2. create candidate and human-approved gold queries;
3. establish persistent full-archive FTS baseline;
4. measure retrieval failures;
5. build a citation-safe context pack over archive, curated, linked-source,
   project, freshness, and unknown evidence;
6. compare embedding/hybrid alternatives only after measured failures;
7. select vector backend through ADR and eval result;
8. implement hybrid retrieval only when approved metrics improve;
9. gate local and LLM-backed chat on recall, citation precision, no-answer
   accuracy, latency, and privacy receipts.

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

Those jobs are target workflows, not active dogfood runtime. A future runtime
activation must use the PRM-17 workflow registry and explicit human approval.
MVP Radar remains a secondary decision-evidence projection: it must not approve
build/release decisions from Telegram-only evidence and must not drive the
primary product workflow.
