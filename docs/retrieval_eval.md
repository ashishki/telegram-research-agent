# Retrieval Evaluation Plan

Status: draft; PRM-7 owns baseline execution

## Baseline

The first baseline is persistent SQLite FTS over retained archive posts with
metadata filters. Knowledge Atoms and topics are not required for search.

## Dataset

Use `evals/retrieval/query_set_candidate.jsonl` as candidate input. Human
approval is required before labels count as gold evidence.

## Metrics

- hit@10 for known-item cases;
- MRR;
- citation precision;
- stale-document rejection;
- no-answer accuracy;
- duplicate top-10 result rate;
- p95 local retrieval latency;
- reacted-post search availability after sync.

## Failure Taxonomy

- missing archive document;
- missing source URL;
- FTS tokenization miss;
- language mismatch;
- duplicate/repost crowding;
- stale result selected for freshness query;
- no-answer false positive;
- atom-gated invisibility;
- assistant synthesis ignores retrieved evidence.

## Hybrid ADR Gate

PRM-7 may propose embeddings/hybrid retrieval only after baseline failures are
measured. The ADR must compare recall, latency, update complexity, privacy,
backup/rollback, operational overhead, cost, and repository fit.
