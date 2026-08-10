# ADR-002: Vector Backend Gate For Personal Research Memory

Status: proposed_not_accepted
Date: 2026-07-26

## Context

PRM-7 requires an FTS baseline evaluation before any vector or hybrid retrieval
implementation. The current evidence report is
`evals/retrieval/prm7_fts_baseline_report.json`.

The PRM-7 query set had 50 candidate rows and 0 human-approved gold rows.
Candidate rows are useful for latency and safety diagnostics only. They are not
pass/fail relevance evidence and must not justify vector adoption.

2026-08-10 update: PRM-24 now has seven operator-approved no-answer seed
labels, promoted from generated drafts under
`operator-approval-2026-08-10-generated-drafts-as-gold`. Those labels are
useful for no-answer behavior, but they still do not provide recall/citation
failure evidence across archive recall, semantic phrasing, project fit,
linked-source/freshness, and decision-support categories.

## Decision

Do not adopt a vector backend yet.

PRM-8 remains blocked until all of these are true:

- a full human-approved product gold label set exists or the operator
  explicitly waives/changes that requirement;
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

Current PRM-24 state supersedes only the zero-label part of this historical
receipt: seven no-answer labels exist, but no measured recall/citation failure
evidence exists yet. The ADR decision remains unchanged.

## Backend Comparison

| Candidate | Recall | Latency | Update complexity | Privacy | Backup/rollback | Overhead | Cost | Repository fit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SQLite FTS baseline | No recall/citation failure measured on approved product labels yet | Local p95 59.988 ms on candidate load set | Existing derived table and triggers | No provider egress | Same SQLite backup path | Lowest | $0/model and $0/provider | Current fit |
| SQLite-local vector extension | Unknown until full product gold labels and embeddings exist | Unknown; local candidate | Requires embedding generation and extension lifecycle | Can remain local if embeddings are local | Requires vector index rebuild/backup plan | Medium | Embedding/runtime cost | Possible later, not approved |
| Postgres/pgvector | Unknown until full product gold labels and embeddings exist | Unknown in this repo | Requires new service or migration | Adds operational boundary | Separate DB backup and rollback | High | Hosting plus embedding cost | Poor fit before product proof |
| External vector service | Unknown until full product gold labels and embeddings exist | Network-dependent | Requires provider integration and sync | Private corpus egress risk | Provider export/restore dependency | Highest | Provider plus embedding cost | Not acceptable without explicit privacy approval |

## Consequences

- The assistant continues to use SQLite FTS and metadata filters.
- Candidate queries remain unapproved and cannot be relabelled as gold by the
  agent.
- Vector backend adoption is a stop-ship boundary and still requires immediate
  operator review.
- PRM-8 must not start implementation until this ADR or a successor is accepted
  with approved evaluation evidence.
