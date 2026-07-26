# ADR-001: Product Pivot To Personal Telegram Research Memory

Status: proposed

Date: 2026-07-26

Decision owner: human operator

## Context

The previous implementation contract made weekly decision-support artifacts the
product center and explicitly rejected broad searchable memory. W29 showed that
this product shape does not serve the operator: reports were generated, but the
operator still did not receive useful recall, personalization, or
project-specific decisions.

Verified W29 evidence:

- delivered Brief and Atlas sidecars have `schema_version:
  split_ai_report.v1`;
- the W29 run detected 7 personal reacted posts;
- reaction receipts recorded 0 linked Knowledge Atoms, 0 linked canonical or
  compatibility threads, 0 selected items, and 7 unconsumed reaction events;
- W29 project intelligence had no confirmed implications, no weak watches, and
  no tiny PR ideas;
- learning projection counted 8 `read` items from source refs even though a
  source URL does not prove the operator read the material;
- Radar failed and the whole W29 package became partial even though archive
  search should not depend on Radar.

## Old Decision

Weekly artifact centered, curated evidence only:

- reports were the primary product;
- memory existed to improve report continuity;
- raw Telegram RAG and broad/global memory were out of scope.

## New Proposed Decision

Full Telegram archive is searchable product memory. Curated knowledge is a
selective enrichment layer. Assistant search is the primary surface. Reports
are secondary projections.

Core principle:

```text
Search everything.
Enrich what matters.
Save what proves useful.
Generate reports only as a secondary projection.
```

## Why The Old Decision No Longer Serves The Operator

The old design can pass structural report gates while still hiding the exact
posts the operator cared about. Knowledge Atoms became a visibility gate:
reacted posts without atoms were acknowledged in receipts but not useful in
answers or rankings. The operator needs natural-language recall and source
links across the corpus, not a larger weekly artifact.

## Why Full Archive Search Is Justified

Read-only inspection found `raw_posts`, `posts`, and `posts_fts` already present
with equal row counts. The archive exists locally and already has an FTS
primitive. Exposing the full retained text archive through a bounded search
tool is lower complexity than adding more report logic or a vector database.

## Canonical And Derived Boundaries

Canonical:

- SQLite `raw_posts` and `posts`;
- Telegram channel/message/date/URL identity;
- explicit operator reactions and confirmed feedback;
- human-approved saved notes, watch topics, project links, decisions, and
  experiments.

Derived:

- FTS indexes;
- Knowledge Atoms;
- topics/canonical topics;
- assistant answer traces;
- reports, Briefs, Atlases, and library pages;
- enrichment batches.

## Privacy Implications

The corpus is private. The pivot increases retrieval reach, so the system must
strengthen privacy boundaries:

- no raw corpus dump to LLMs;
- bounded context assembly;
- no raw text in logs;
- external embeddings require explicit data-egress approval;
- public fixtures remain sanitized;
- external skills stay disabled until trust review.

## Migration Implications

- Keep V1 Brief/Atlas compatibility until PRM-16 proves a safe demotion.
- Add archive search without deleting Knowledge Atom infrastructure.
- Make reacted posts searchable before enrichment.
- Correct learning-state semantics additively.
- Do not start broad cleanup until PRM-4 and initial retrieval eval prove the
  new product path.

## Not A Generic Memory Platform

This is limited to one operator's retained Telegram research corpus and its
approved derived knowledge. It is not a cross-domain memory daemon, SaaS
product, graph database project, or autonomous personal agent runtime.

## Still Out Of Scope

- public or multi-user product;
- automatic project builds or purchases;
- full archive LLM enrichment backfill;
- vector database before FTS evaluation;
- automatic permanent preference changes;
- external-skill activation without trust review;
- assistant code/config mutation.

## Rollback Path

If PRM-3/PRM-4 fail to show useful retrieval, keep the existing report
pipeline, leave archive FTS internal, and do not accept report demotion or
hybrid retrieval tasks. No canonical archive data should be migrated
destructively for the pivot.

## Approval

This ADR is proposed only. Human approval is required before product/runtime
implementation begins under the new direction.
