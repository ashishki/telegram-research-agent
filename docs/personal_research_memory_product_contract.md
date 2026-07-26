# Personal Research Memory Product Contract

Status: proposed

Last updated: 2026-07-26

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

## Non-Goals

- generic memory platform;
- full archive LLM backfill;
- vector database before measured FTS failure;
- automatic writes or permanent preferences;
- public SaaS;
- assistant-owned code/config/project mutation.
