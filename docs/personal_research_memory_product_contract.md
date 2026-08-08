# Personal Research Memory Product Contract

Status: proposed

Last updated: 2026-07-29

## North Star

Personal Telegram Research Memory + Grounded Assistant.

The operator asks a natural-language question and receives:

1. direct concise answer;
2. relevant context from the full retained Telegram archive;
3. concrete Telegram source links;
4. grouped cases, tools, claims, approaches, and contradictions where relevant;
5. freshness/date boundary;
6. distinction between archive evidence and model background;
7. `insufficient_evidence` when support is weak;
8. optional external verification path for unstable/high-stakes questions;
9. optional confirmation-gated save/watch/project/decision/experiment proposal.

## Product Principle

```text
Search everything.
Enrich what matters.
Save what proves useful.
Generate reports only as a secondary projection.
```

## Required Workflows

| Workflow | Required behavior |
| --- | --- |
| Exact search | Retrieve a retained post by phrase, price, tool name, source, date, or message identity. |
| Concept search | Retrieve multiple relevant posts over a time window even when wording differs. |
| Case search | Group source-backed cases and show positive/negative tradeoffs. |
| Comparison | Compare approaches with citations and contradictions. |
| Project application | Connect archive evidence to active projects with direct, weak, learning, or no-match labels. |
| News and timeline | Show what changed in a bounded period and name freshness cutoff. |
| Reaction recall | Show reacted posts and why they may matter; no atom requirement. |
| Life/career context | Answer career-market questions with Telegram as discovery context, not final truth. |
| No-answer | Return `insufficient_evidence` when the archive is weak. |
| External verification | Separate Telegram archive, external verification, and unknowns. |

## Research Session Assistant Target

The polished assistant target is implemented only as a fixture-first local
slice, not a current dogfood claim. For full research sessions, the assistant
must search the large Telegram archive, inspect approved linked sources,
compare approaches, infer project context, explain the result clearly, and
recommend where to look next. The current PRM-23 `memory research` path uses
bounded local archive/curated/project context, PRM-22 linked-source cache/fake
fetcher evidence, deterministic synthesis, and confirmation-gated drafts; it
does not approve live web research, provider egress, service start, production
writes, dogfood, release claims, or vector/backend adoption.

Example target question:

```text
покажи свежие практики по RAG и что из этого применимо к моему проекту
```

The answer should include:

- a direct, concise answer;
- what the local Telegram archive says;
- which linked sources were read and what they add;
- approach comparisons, tradeoffs, and contradictions;
- likely project context and confidence;
- what to apply, watch, ignore, or study next;
- a short deeper-reading path with source links;
- unknowns and freshness limits;
- a privacy/cost receipt.

RAG is necessary for this workflow, but it is only one layer. It retrieves
relevant Telegram posts, preserves exact Telegram links, supports metadata
filters, finds conceptually related posts, dedupes repeats, and assembles
bounded citation-safe context. RAG alone does not read linked sources, compare
approaches across archive and web evidence, recognize active project context,
decide what is current versus stale, produce a polished answer, or measure
usefulness.

PRM-25 context-pack contract: the local answer path assembles a bounded
`rag_context_pack.v1` before rendering. Every included item has a stable
citation reference, evidence class, bounded excerpt, retrieval-query variant,
freshness status, and project label. Candidates with raw-corpus fields, no
citation, duplicate citation, missing excerpt, or over-budget source count are
excluded with a reason. An empty pack requires no-answer handling. Synthetic
semantic candidates are fixture-only inputs; they do not run embeddings or
authorize a vector backend.

Required research-session capability stack:

1. Archive retrieval over all retained local Telegram posts, curated memory,
   reactions, watch topics, and project descriptors.
2. Selective enrichment for reacted posts, repeated search hits, cited answers,
   watch topics, project matches, repeated signals, and manual saves.
3. Linked-source research that extracts URLs from selected posts, classifies
   source type, fetches or parses sources only after explicit approval, caches
   privacy-safe text/metadata, and keeps linked evidence separate.
4. Project context routing with `direct_implication`, `weak_watch`,
   `learning_relevance`, `no_match`, and `ambiguous_project` labels.
5. Bounded planning with deterministic limits for tool calls, retries, source
   count, prompt size, cost, and timeout.
6. Grounded synthesis over bounded cited snippets and approved linked-source
   excerpts.
7. Confirmation-gated Knowledge Note, Watch Topic, project link, decision,
   action, or experiment proposals.
8. Evaluation through human-approved gold retrieval labels, citation precision,
   unsupported-claim checks, freshness/no-answer checks, useful-answer labels,
   cost per useful answer, and friction score.

Research-session answers must separate evidence classes:

| Evidence class | Meaning | Response handling |
| --- | --- | --- |
| `telegram_archive` | Local retained Telegram post evidence | Cite Telegram URL, date, channel, bounded snippet |
| `curated_memory` | Confirmed notes, topics, decisions, project links | Cite memory ID or local artifact |
| `linked_source` | Approved fetched source linked from a post | Cite URL and retrieval timestamp |
| `model_background` | Model knowledge not grounded in retrieved sources | Label clearly; do not use as proof |
| `unknown` | Missing, stale, conflicting, or unverified evidence | State the gap and next verification step |

SQLite FTS remains the baseline. Vector or hybrid retrieval remains conditional
through PRM-8 and must not be adopted before human-approved evidence shows that
the FTS baseline fails important retrieval scenarios.

## Project Application

PRM-14 implementation contract:

- project context answers use active project descriptors from bounded local
  descriptor files;
- the assistant combines descriptor fields, bounded Telegram archive retrieval,
  and curated knowledge evidence;
- answers label relevance as `direct_implication`, `weak_watch`,
  `learning_relevance`, or `no_match`;
- direct implications must cite archive/source evidence and name descriptor
  fields used;
- weak keyword-only matches and learning-only relevance do not produce project
  action recommendations;
- no assistant tool may approve MVP builds, mutate code, or mutate project
  descriptors.

## Answer Contract

Every grounded answer must include:

- Direct answer.
- What the archive supports.
- Relevant Telegram source links.
- Contradictions or uncertainty.
- Freshness/date boundary.
- Model background, if used.
- What requires external verification.
- Optional next action.

## Reaction Fast Lane

Any visible personal reaction is positive implicit interest.

Required path:

```text
reaction detected
  -> confirm source post exists in canonical archive
  -> make post searchable immediately
  -> enqueue high-priority enrichment
  -> attempt atom/case/tool/entity extraction independently
  -> link to existing or provisional topic
  -> expose in assistant search
  -> record receipt for every stage
```

Receipt fields:

- reactions detected;
- unique posts;
- archive documents indexed;
- enrichment attempts;
- enrichment successes and failures;
- topic links;
- search availability;
- ranking effects;
- reasons for incomplete processing.

`7 reactions -> 0 searchable knowledge items` is never a successful state.

## Knowledge Library

Primary saved-knowledge surfaces:

- Topics;
- Research Notes;
- Cases;
- Tools;
- Practices;
- Watch Topics;
- Projects;
- Decisions;
- Experiments.

The old detailed Atlas is renamed product-wise to Knowledge Audit Explorer and
is an internal/debug surface.

PRM-13 implementation contract:

- topic pages may be created from a user query or confirmed Watch Topic;
- the page DTO includes current understanding, 30-day changes, 90-day changes,
  claims, cases, tools, practices, contradictions, project links, saved notes,
  decisions, experiments, open questions, and original sources;
- source references remain explicit and bounded to caller-supplied archive or
  confirmed memory evidence;
- the renderer emits static self-contained HTML with no script, external CSS,
  remote assets, live retrieval, provider calls, or database writes;
- Knowledge Audit Explorer remains available only as an internal/debug view and
  is not the primary saved-knowledge product surface.

## Weekly Brief V3

Weekly Brief is secondary. It is derived from watch-topic changes, reactions,
questions asked, saved notes, projects, repeated signals, experiments, and
explicit feedback.

Target shape:

- one main change;
- one ACT item;
- one STUDY item;
- one WATCH or IGNORE item;
- one reaction processing summary;
- one concrete project connection or honest zero;
- optional Radar card;
- one feedback request.

Radar failure degrades only the Radar card.

PRM-16 implementation contract:

- `output.weekly_brief_v3.build_weekly_brief_v3` derives the V3 DTO from
  bounded caller-supplied context only;
- the DTO contains `main_change`, `act_item`, `study_item`,
  `watch_ignore_item`, `reaction_summary`, `project_connection`, optional
  `radar_card`, `feedback_request`, source refs, dependency status, privacy
  boundary flags, and legacy-surface demotion metadata;
- generic fallback action phrasing is rejected by deterministic validation;
- Radar failure is localized to `radar_card` and `dependency_status.radar` and
  does not invalidate archive search, assistant answers, Knowledge Library, or
  non-Radar sections;
- the renderer emits static self-contained HTML with no script, remote assets,
  live retrieval, provider calls, Radar run, report generation, or database
  writes.

## Learning State

PRM-15 implementation contract:

- canonical learning states are `indexed`, `surfaced`, `opened`, `read`,
  `understood`, `explained`, `tried`, `applied`, `measured`, `rejected`, and
  `stale`;
- legacy source URL or Knowledge Atom presence maps only to `indexed` or
  `surfaced`;
- `opened`, `read`, `understood`, `explained`, `tried`, `applied`, and
  `measured` require explicit feedback, progress receipt, outcome evidence, or
  measured/test evidence;
- no feedback is shown as `unknown`;
- report and assistant projections must not infer mastery, application, or
  measured outcome from passive exposure.

## Non-Goals

- generic memory platform;
- full archive LLM backfill;
- vector database before measured FTS failure;
- automatic writes or permanent preferences;
- public SaaS;
- assistant-owned code/config/project mutation.
