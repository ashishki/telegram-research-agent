# PRM Retrieval Ablation

Status: active
Date: 2026-08-15

Harness: `tools/prm_qa_eval.py`

Reports:

- `evals/prm_qa/prm_qa_eval_report.v1.json`
- `evals/prm_qa/prm_qa_holdout_report.v1.json`

## Variants

- R0: SQLite FTS strict/OR baseline.
- R1: FTS plus current hash-vector fallback.
- R2: FTS plus current hash-vector always-on fusion.
- R3: FTS plus bounded query rewrite.
- R4: true local dense candidate.
- R5: candidate pool plus bounded reranker.

## Result

Selected runtime policy: R1/R3 behavior. Runtime uses FTS with deterministic OR
fallback, bounded generic rewrites, and local hash-vector fallback only on FTS
miss. R2 and R5 remain eval adapters because they did not improve holdout recall
or nDCG and had much worse p95 latency.

Dense retrieval was not adopted. The local environment did not have
`sentence_transformers`; no dense holdout gain was measured.
