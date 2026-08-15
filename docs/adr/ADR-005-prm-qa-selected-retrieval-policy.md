# ADR-005: PRM-QA Selected Retrieval Policy

Date: 2026-08-15

## Status

Accepted for manual-test runtime. This does not start PRM-19 dogfood and does
not approve hosted vector services, live web research, production migrations, or
release claims. On 2026-08-15 the operator separately approved API embeddings
for this product; this ADR now records the measured OpenAI embedding candidate.

## Context

PRM-QA compared archive retrieval variants on 160 generated private regression
cases derived from the local Telegram corpus. The generated cases are
deterministic/silver regression evidence only. They are not human gold labels
and do not prove real operator value.

The current local vector sidecar uses deterministic hashing over words, word
bigrams, and character n-grams. After the initial local-only pass, the operator
approved API embeddings because this is an API-backed assistant product. The
API candidate uses OpenAI `text-embedding-3-large`, which official OpenAI docs
describe as the most capable embedding model for English and non-English tasks.
The sidecar remains local SQLite; provider egress is limited to bounded archive
chunks and query strings sent for embeddings. No hosted vector database is used.

## Decision

Default runtime retrieval remains SQLite FTS with deterministic OR fallback,
plus bounded generic query rewrites at the memory-research layer. The local
hash-vector sidecar remains fallback-only when FTS returns no evidence.

Always-on hash-vector fusion, API dense hybrid fusion, and the candidate-pool
reranker remain eval adapters, not default runtime policy.

## Evidence

Public aggregate reports:

- `evals/prm_qa/prm_qa_dataset_manifest.v1.json`
- `evals/prm_qa/prm_qa_eval_report.v1.json`
- `evals/prm_qa/prm_qa_holdout_report.v1.json`
- `evals/prm_qa/prm_qa_api_dense_report.v1.json`
- `evals/prm_qa/prm_qa_api_dense_holdout_report.v1.json`

All-partition selected metrics:

- R1 FTS + hash-vector fallback: Recall@10 1.0000, MRR 0.9845, nDCG@10
  0.9885, p95 94.0055 ms.
- R3 bounded query rewrite: Recall@10 1.0000, MRR 0.9845, nDCG@10 0.9885,
  p95 112.2836 ms.
- R2 always-on hash-vector fusion: Recall@10 1.0000, MRR 0.8750, nDCG@10
  0.9069, p95 682.4433 ms.
- R5 candidate-pool reranker: Recall@10 1.0000, MRR 0.8702, nDCG@10 0.9030,
  p95 755.2147 ms.

Holdout selected metrics:

- R1: Recall@10 1.0000, MRR 1.0000, nDCG@10 1.0000, p95 78.7893 ms.
- R3: Recall@10 1.0000, MRR 1.0000, nDCG@10 1.0000, p95 111.1032 ms.
- R2/R5 did not improve recall and materially worsened ranking latency.
- API dense hybrid with `text-embedding-3-large`: Recall@10 1.0000, MRR
  0.7240, nDCG@10 0.7957, context_precision@5 0.2471, p95 618.3259 ms.
- PRM-QA-16 added `retrieval_by_job_type` to the public R1/R4 reports. No
  holdout job-type segment showed a material enough API dense gain to adopt R4.

API sidecar build evidence:

- provider/model: OpenAI `text-embedding-3-large`
- dimensions: 3072
- sidecar: gitignored local path data/vector/archive_api_vector.sqlite
- sidecar size: 130.8 MB
- indexed chunks: 3,706 from 3,590 archive rows
- provider calls: 29
- input tokens: 1,356,089
- canonical DB mutated: false

## Consequences

- Exact/current/reacted/saved/timeline/project paths do not pay always-on vector
  latency by default.
- The sidecar row cache improves eval/runtime vector scans without changing the
  sidecar format or mutating canonical data.
- API dense retrieval is available as an explicitly approved measured adapter,
  but is not the default because it did not improve holdout nDCG/MRR and added
  latency/provider cost.
- API dense can be reconsidered after query/document shaping, chunk policy, or
  reranking changes produce a real holdout gain without weakening privacy.
