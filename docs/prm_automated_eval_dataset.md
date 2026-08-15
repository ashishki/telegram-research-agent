# PRM Automated Eval Dataset

Status: active
Date: 2026-08-15

Generator: `tools/prm_qa_generate_private_eval.py`

Private output: `data/evals/private/prm_qa/cases.v1.jsonl` (gitignored)

Public manifest: `evals/prm_qa/prm_qa_dataset_manifest.v1.json`

## Dataset

- Cases: 160
- Partitions: development 89, tuning 37, holdout 34
- Labels: deterministic 75, silver 80, synthetic negative 5
- Corpus fingerprint:
  `sha256:59e2dc9c852887a3a67f05d195870ddfb24cb11fc870dc0abd9dfd56f14d9a57`

## Categories

The generator covers exact known item, semantic topic, case study, comparison,
timeline/freshness, named-project decision, ambiguous project, writer/editor,
learning experiment, reacted-post recall, saved-knowledge recall, no-answer,
current-fact, and hard-negative distractor cases.

## Privacy

Private cases may contain generated private queries and source URLs. The public
manifest contains counts, fingerprints, partitions, schema version, generator
version, and privacy flags only. It contains no raw Telegram body, raw question,
source URL, chat ID, prompt, completion, or snippet.
