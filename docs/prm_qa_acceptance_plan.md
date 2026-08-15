# PRM-QA Acceptance Plan

Status: active
Date: 2026-08-15

## Automated Gates

- Private dataset generation succeeds with at least 150 cases.
- Dev/tuning/holdout partitions are separate.
- Routing, retrieval, evidence, grounding, presentation, and task-success proxy
  metrics are reported separately.
- Retrieval ablation compares R0 through R5.
- Selected retrieval policy is based on measured results.
- Dense retrieval, including approved API embeddings, is adopted as default only
  after a measured holdout gain.
- Retrieval reports include job-type metrics before changing a default policy.
- Evidence quality and source independence are represented.
- Claim ledger and citation checks exist.
- Ambiguous project requests clarify.
- Named project requests render a decision memo.
- Approved Telegram API synthesis runs before job-specific fallback templates
  for normal source-backed answers.
- Job-specific Telegram fallback renderers exist.
- Feedback receipts and private failed-case traces are gitignored.
- Current-fact safety has zero violations.
- Focused PRM tests and safety checks pass.

## Non-Automated Gate

Real product-value claims still require future operator usage evidence. Automated
metrics alone cannot prove usefulness.
