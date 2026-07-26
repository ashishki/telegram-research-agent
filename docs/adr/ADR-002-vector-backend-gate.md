# ADR-002: Vector Backend Gate For Personal Research Memory

Status: proposed_not_accepted
Date: 2026-07-26

## Context

PRM-7 requires an FTS baseline evaluation before any vector or hybrid retrieval
implementation. The current evidence report is
`evals/retrieval/prm7_fts_baseline_report.json`.

The available query set currently has 50 candidate rows and 0 human-approved
gold rows. Candidate rows are useful for latency and safety diagnostics only.
They are not pass/fail relevance evidence and must not justify vector adoption.

## Decision

Do not adopt a vector backend yet.

PRM-8 remains blocked until all of these are true:

- a human-approved gold label file exists;
- FTS baseline metrics show measured recall or ranking failures;
- candidate/hybrid comparison improves approved metrics without reducing
  citation precision below target;
- the operator explicitly accepts this or a successor ADR.

No embeddings were run, no vector database was created, and no retrieval path was
changed by PRM-7.

## Evidence

PRM-7 FTS baseline command:

```text
PYTHONPATH=src python3 tools/archive_retrieval_eval.py --root . --db data/agent.db --cases evals/retrieval/query_set_candidate.jsonl --limit 10 --json evals/retrieval/prm7_fts_baseline_report.json
archive_retrieval_eval: rows=50 gold=0 candidates=50 output=evals/retrieval/prm7_fts_baseline_report.json
```

Summary:

| Measure | Value |
| --- | ---: |
| Rows | 50 |
| Human-approved gold rows | 0 |
| Candidate rows | 50 |
| Candidate p95 latency | 59.988 ms |
| Candidate duplicate top-10 rate | 0.008 |
| Reacted-post searchability | 0.956522 |

The report has `vector_backend_gate.status=blocked_no_human_approved_gold`,
`vector_backend_adopted=false`, and `embeddings_run=false`.

## Backend Comparison

| Candidate | Recall | Latency | Update complexity | Privacy | Backup/rollback | Overhead | Cost | Repository fit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SQLite FTS baseline | Measured only for latency until gold labels exist | Local p95 59.988 ms on candidate load set | Existing derived table and triggers | No provider egress | Same SQLite backup path | Lowest | $0/model and $0/provider | Current fit |
| SQLite-local vector extension | Unknown until gold labels and embeddings exist | Unknown; local candidate | Requires embedding generation and extension lifecycle | Can remain local if embeddings are local | Requires vector index rebuild/backup plan | Medium | Embedding/runtime cost | Possible later, not approved |
| Postgres/pgvector | Unknown until gold labels and embeddings exist | Unknown in this repo | Requires new service or migration | Adds operational boundary | Separate DB backup and rollback | High | Hosting plus embedding cost | Poor fit before product proof |
| External vector service | Unknown until gold labels and embeddings exist | Network-dependent | Requires provider integration and sync | Private corpus egress risk | Provider export/restore dependency | Highest | Provider plus embedding cost | Not acceptable without explicit privacy approval |

## Consequences

- The assistant continues to use SQLite FTS and metadata filters.
- Candidate queries remain unapproved and cannot be relabelled as gold by the
  agent.
- Vector backend adoption is a stop-ship boundary and still requires immediate
  operator review.
- PRM-8 must not start implementation until this ADR or a successor is accepted
  with approved evaluation evidence.
