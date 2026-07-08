# Curated Semantic Retrieval Decision

Status: implemented by HPI-9-lite on 2026-07-08.

## Decision

PI Assistant should not add broad vector RAG now. The implemented HPI-9-lite
step is a curated-only retrieval prototype:

- keep SQLite tables and workbook/JSON sidecars as source of truth;
- build `IntelligenceRetrievalItem` objects from curated artifacts exactly as
  before;
- apply filters first: week, item type, project, thread, and status;
- rank the filtered curated set with deterministic scoring plus transient
  SQLite FTS5;
- keep raw Telegram firehose posts out of assistant retrieval;
- keep vector embeddings deferred until dogfood shows specific misses that
  deterministic+FTS cannot solve.

## Dream Motif Reference

Dream Motif Interpreter uses a stronger retrieval stack in
`app/retrieval/query.py`: query expansion, exact FTS, vector candidates,
reciprocal-rank fusion, insufficient-evidence states, and facade/tools
separation. The reusable patterns for this repository are:

- retrieval stays behind a bounded assistant facade;
- exact/lexical search is available before or alongside semantic search;
- filters and provenance are part of the retrieval contract;
- missing evidence is a valid answer;
- tool prompts tell the assistant which retrieval surface is allowed.

The parts not adopted now are Postgres/pgvector, persisted embeddings, and LLM
query expansion. They are unnecessary until there are measured curated-search
misses.

## Prototype

`src/assistant/semantic_retrieval.py` implements the HPI-9-lite prototype. It
does not persist an index. For each request it:

1. receives curated `IntelligenceRetrievalItem` objects;
2. rejects raw Telegram item types if they are ever passed accidentally;
3. applies filters before indexing;
4. expands a small set of domain terms deterministically;
5. builds an in-memory SQLite FTS5 table;
6. merges deterministic and FTS ranks with reciprocal-rank style scoring;
7. returns the same item DTO shape with source refs, atom IDs, evidence tier,
   verification status, and `retrieval_mode`.

The facade exposes the decision in `search_intelligence_items` as
`retrieval_decision`, with vector status set to deferred and raw Telegram RAG
set to disabled.

## Deferred

Vector retrieval remains a later dogfood decision. Add it only if the operator
records concrete examples where curated deterministic+FTS retrieval misses
useful workbook cards, Knowledge Atoms, Idea Threads, MVP dossiers, feedback
summaries, or Strategy Reviewer notes.
