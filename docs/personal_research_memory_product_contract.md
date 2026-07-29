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
