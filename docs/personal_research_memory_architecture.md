# Personal Research Memory Architecture

Status: proposed product architecture

Canonical architecture summary: `docs/ARCHITECTURE.md`

## Target Diagram

```text
                         +---------------------+
Telegram channels -----> | Canonical Archive   |
                         | every retained post |
                         +----------+----------+
                                    |
                     +--------------+--------------+
                     |                             |
               Archive Search                Selective Enrichment
               every post                    important posts only
                     |                             |
        FTS + metadata + optional       reactions / user queries /
        hybrid semantic retrieval       watch topics / projects
                     |                             |
                     +--------------+--------------+
                                    |
                          Assistant Router
                                    |
         +-------------+------------+------------+-------------+
         |             |            |            |             |
    Archive search  Curated topics  Project    Saved memory   Web verify
                                   context
         |             |            |            |             |
         +-------------+------------+------------+-------------+
                                    |
                             Grounded answer
                             with source links
                                    |
                     +--------------+--------------+
                     |                             |
              Save Knowledge Note          Create watch/action/
                                            project/experiment
                     |                             |
                     +--------------+--------------+
                                    |
                          Secondary projections
                          Weekly Brief / Library
```

## Archive Memory

Archive Memory is the searchable retained Telegram corpus.

Minimum document identity:

- `archive_document_id`;
- `post_id`;
- `raw_post_id`;
- channel username and channel ID;
- message ID;
- posted date;
- Telegram URL;
- language;
- content hash;
- duplicate/repost cluster ID when known;
- chunk index only when chunking is required.

Normal posts remain one document. Long posts may be chunked, but all chunks
must preserve post-level citation.

## Curated Knowledge

Curated Knowledge enriches only important posts and saved results. It never
controls whether a post is searchable.

Objects:

- atoms;
- claims;
- cases;
- tools;
- practices;
- warnings;
- entities;
- canonical topics;
- Knowledge Notes;
- Watch Topics;
- project links;
- decisions;
- experiments.

## Router

The router should be deterministic where possible:

- exact quoted phrase or source/date filters -> archive search;
- reacted recall -> reacted archive filter plus enrichment status;
- topic page request -> curated topic page, with archive fallback;
- current/high-stakes/unstable question -> archive discovery plus optional
  external verification path;
- save/watch/project/action/experiment request -> proposal tool, then
  confirmation gate.

Bounded LLM routing may be used when intent is ambiguous. Tool loop max remains
small and traceable.

## Retrieval Assembly

The answer context assembly must:

- dedupe reposts and near-duplicates;
- preserve source diversity;
- mark stale documents for freshness questions;
- separate Telegram evidence from model background;
- include enough snippet context to verify relevance;
- keep raw text out of logs.

## Secondary Projections

Reports and library pages are generated views over archive and curated layers.
They do not become source of truth.

Knowledge Library topic pages are deterministic projections over bounded topic
evidence supplied by archive search, selective enrichment, and confirmed memory
events. The old global Atlas remains a Knowledge Audit Explorer for
compatibility/debug inspection rather than the primary user surface.
