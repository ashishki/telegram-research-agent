# ADR-002: Vector Backend Gate For Personal Research Memory

Status: proposed_not_accepted
Date: 2026-08-11

## Context

PRM-7 requires an FTS baseline evaluation before any vector or hybrid retrieval
implementation. The current evidence report is
`evals/retrieval/prm7_fts_baseline_report.json`.

The PRM-7 query set had 50 candidate rows and 0 human-approved gold rows.
Candidate rows are useful for latency and safety diagnostics only. They are not
pass/fail relevance evidence and must not justify vector adoption.

2026-08-11 update: PRM-24 now has 50 operator-approved generated seed gold
labels under `operator-approval-2026-08-11-all-50-generated-gold`, plus a
privacy-safe SQLite FTS/query-planner baseline report at
`evals/retrieval/product_rag_fts_baseline_report.json`. The labels cover
archive recall, semantic phrasing, project fit, linked-source/freshness,
no-answer, and decision-support categories, but they are generated seed labels,
not independent human review.

## Decision

Do not adopt a vector backend yet.

PRM-8 remains blocked until all of these are true:

- PRM-26 or a successor ADR is accepted by the operator;
- FTS baseline metrics and PRM-24/PRM-25 evidence are mapped to concrete
  retrieval mechanisms and product gaps;
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

Historical PRM-7 summary:

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

Current PRM-24 state supersedes the zero-label part of this historical receipt.
The current generated seed baseline reports:

| Measure | Value |
| --- | ---: |
| Rows | 50 |
| Gold rows | 50 |
| Candidate rows | 0 |
| hit@10 | 1.0 |
| MRR | 1.0 |
| Citation precision | 1.0 |
| No-answer accuracy | 0.0 |
| Stale rejection | null |
| Duplicate top-10 rate | 0.004 |
| p95 latency | 46.912 ms |
| Reacted-post searchability | 0.967742 |

Interpretation: the generated seed source labels are recovered by the current
SQLite FTS/query planner, but no-answer/refusal behavior fails at the raw
retrieval layer and stale/forbidden labels remain unmeasured. The ADR decision
remains unchanged.

## Backend Comparison

| Candidate | Recall | Latency | Update complexity | Privacy | Backup/rollback | Overhead | Cost | Repository fit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SQLite FTS baseline | Generated seed source-label recall/citation is 1.0; no-answer accuracy is 0.0 | Local p95 46.912 ms on PRM-24 generated seed gold set | Existing derived table and triggers | No provider egress | Same SQLite backup path | Lowest | $0/model and $0/provider | Current fit, but answer-level refusal still needs PRM-28 gating |
| SQLite-local vector extension | Unknown until PRM-26 approves a local embedding/index plan | Unknown; local candidate | Requires embedding generation and extension lifecycle | Can remain local if embeddings are local | Requires vector index rebuild/backup plan | Medium | Embedding/runtime cost | Possible later, not approved |
| Postgres/pgvector | Unknown until PRM-26 approves a service/migration plan | Unknown in this repo | Requires new service or migration | Adds operational boundary | Separate DB backup and rollback | High | Hosting plus embedding cost | Poor fit before accepted ADR |
| External vector service | Unknown until PRM-26 approves provider privacy/cost budget | Network-dependent | Requires provider integration and sync | Private corpus egress risk | Provider export/restore dependency | Highest | Provider plus embedding cost | Not acceptable without explicit privacy approval |

## Consequences

- The assistant continues to use SQLite FTS and metadata filters.
- PRM-24 candidate queries remain unapproved in the candidate file; the
  separate 50-row generated seed label file is operator-approved for PRM-24
  eval scaffolding only.
- Vector backend adoption is a stop-ship boundary and still requires immediate
  operator review.
- PRM-8 must not start implementation until this ADR or a successor is accepted
  with approved evaluation evidence.
