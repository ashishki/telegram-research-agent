# ADR-005: PRM-QA Selected Retrieval Policy

Date: 2026-08-15

## Status

Accepted for local manual-test runtime. This does not start PRM-19 dogfood and
does not approve external embeddings, hosted vector services, live web research,
production migrations, or release claims.

## Context

PRM-QA compared archive retrieval variants on 160 generated private regression
cases derived from the local Telegram corpus. The generated cases are
deterministic/silver regression evidence only. They are not human gold labels
and do not prove real operator value.

The current local vector sidecar uses deterministic hashing over words, word
bigrams, and character n-grams. A true multilingual dense retriever was not
available in the local environment because the dense runtime libraries were not
installed. Official model-card candidates recorded for future local-only
evaluation are `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
(Apache-2.0) and `intfloat/multilingual-e5-small` (MIT); neither was adopted.

## Decision

Default runtime retrieval remains SQLite FTS with deterministic OR fallback,
plus bounded generic query rewrites at the memory-research layer. The local
hash-vector sidecar remains fallback-only when FTS returns no evidence.

Always-on hash-vector fusion and the candidate-pool reranker remain eval
adapters, not default runtime policy.

## Evidence

Public aggregate reports:

- `evals/prm_qa/prm_qa_dataset_manifest.v1.json`
- `evals/prm_qa/prm_qa_eval_report.v1.json`
- `evals/prm_qa/prm_qa_holdout_report.v1.json`

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

## Consequences

- Exact/current/reacted/saved/timeline/project paths do not pay always-on vector
  latency by default.
- The sidecar row cache improves eval/runtime vector scans without changing the
  sidecar format or mutating canonical data.
- Dense retrieval can be reconsidered only after a local model is installed,
  license and resource costs are recorded, and untouched holdout gains are
  measured.
