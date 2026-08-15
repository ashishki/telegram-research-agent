# PRM Retrieval Ablation

Status: active
Date: 2026-08-15

Harness: `tools/prm_qa_eval.py`

Reports:

- `evals/prm_qa/prm_qa_eval_report.v1.json`
- `evals/prm_qa/prm_qa_holdout_report.v1.json`
- `evals/prm_qa/prm_qa_api_dense_report.v1.json`
- `evals/prm_qa/prm_qa_api_dense_holdout_report.v1.json`

## Variants

- R0: SQLite FTS strict/OR baseline.
- R1: FTS plus current hash-vector fallback.
- R2: FTS plus current hash-vector always-on fusion.
- R3: FTS plus bounded query rewrite.
- R4: FTS plus OpenAI API dense hybrid candidate using
  `text-embedding-3-large`.
- R5: candidate pool plus bounded reranker.

## Result

Selected runtime policy: R1/R3 behavior. Runtime uses FTS with deterministic OR
fallback, bounded generic rewrites, and local hash-vector fallback only on FTS
miss. R2 and R5 remain eval adapters because they did not improve holdout recall
or nDCG and had much worse p95 latency.

API dense retrieval was implemented and measured after explicit operator
approval. The `text-embedding-3-large` sidecar indexed 3,706 chunks from 3,590
archive rows, used 29 provider calls and 1,356,089 input tokens, and produced a
130.8 MB gitignored SQLite sidecar. It was not adopted as default because
holdout MRR/nDCG regressed versus R1:

- R1 holdout: Recall@10 1.0000, MRR 1.0000, nDCG@10 1.0000, p95 86.0825 ms.
- R4 API dense hybrid holdout: Recall@10 1.0000, MRR 0.7240, nDCG@10 0.7957,
  p95 618.3259 ms.

The 2026-08-15 PRM-QA-16 rerun preserved the same selection with
`retrieval_by_job_type` added to the public reports:

- R1 holdout: Recall@10 1.0000, MRR 1.0000, nDCG@10 1.0000,
  context precision@5 0.2471, p95 86.0825 ms.
- R4 API dense hybrid holdout: Recall@10 1.0000, MRR 0.7240, nDCG@10 0.7957,
  context precision@5 0.2471, p95 618.3259 ms.

No holdout job-type segment showed a material enough API dense gain to justify
changing the default retrieval policy.
