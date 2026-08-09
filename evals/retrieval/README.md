# Retrieval Evaluation Candidates

Status: candidate
Last updated: 2026-08-08

This directory contains candidate retrieval queries for Personal Telegram
Research Memory. The cases are not gold evidence.

Rules:

- Agent-drafted queries remain candidates until the human operator approves the
  query, expected evidence, source citations, and no-answer expectation.
- No query in query_set_candidate.jsonl may be used as a pass/fail gold label
  without a human-approved label file.
- Private Telegram post text must not be copied into public fixtures.
- Gold labels should reference stable document identities and Telegram source
  links, not copied full post bodies.

Planned distribution:

- 8 exact known-item candidates
- 8 semantic topic candidates
- 8 case-study candidates
- 6 multi-document comparison candidates
- 6 freshness/news candidates
- 6 project or life application candidates
- 4 distractor candidates
- 4 no-answer candidates

Human-approved gold labels should be created in a separate file after PRM-1.

## PRM-24 Product RAG Eval Files

- `product_rag_candidate.jsonl`: 50 product RAG candidate questions across
  archive recall, semantic phrasing, project fit, linked-source/freshness,
  no-answer, and decision-support categories. All rows are
  `human_approved=false` and contain no expected labels.
- `product_rag_gold_labels.jsonl`: intentionally empty until the human
  operator approves expected source IDs/URLs or explicit no-answer labels.
- `product_rag_gold_label_drafts.jsonl`: seven non-gold, operator-review
  suggestions for the no-answer/external-verification cases. It is never read
  by the manifest or retrieval scorer.
- `product_rag_thresholds.json`: proposed acceptance thresholds for recall,
  citation precision, no-answer accuracy, stale rejection, duplicate rate, and
  p95 latency.
- `product_rag_eval_manifest.json`: privacy-safe manifest generated from the
  files above. It contains counts and gate status, not query text, source URLs,
  snippets, provider payloads, or raw Telegram text.

Validation:

```bash
PYTHONPATH=src python3 tools/product_rag_eval_manifest.py \
  --root . \
  --json evals/retrieval/product_rag_eval_manifest.json
```

Non-gating draft simulation:

```bash
PYTHONPATH=src python3 tools/product_rag_simulation_manifest.py --root . --json evals/retrieval/product_rag_simulation_manifest.json
```
