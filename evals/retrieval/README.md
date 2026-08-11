# Retrieval Evaluation Candidates

Status: candidate-plus-generated-seed-gold
Last updated: 2026-08-11

This directory contains candidate retrieval queries for Personal Telegram
Research Memory. The cases are not gold evidence.

Rules:

- Agent-drafted queries remain candidates until the human operator approves the
  query, expected evidence, source citations, no-answer expectation, or an
  explicit generated seed-label run.
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
- `product_rag_gold_labels.jsonl`: contains 50 operator-approved generated
  seed labels created from local read-only SQLite FTS/query-planner evidence
  under `operator-approval-2026-08-11-all-50-generated-gold`. It includes 43
  source-labelled rows by stable archive document/post IDs and 7 explicit
  no-answer rows. It contains no raw Telegram text and no source URLs.
- `product_rag_gold_cases.jsonl`: derived scoreable eval view that merges the
  label file with candidate queries; the candidate file itself remains
  `human_approved=false` and label-free.
- `product_rag_fts_baseline_report.json`: privacy-safe baseline report over
  `product_rag_gold_cases.jsonl`; contains metrics/counts only, not queries,
  snippets, source URLs, or raw Telegram text.
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

Generated seed label materialization and baseline eval:

```bash
PYTHONPATH=src python3 tools/product_rag_seed_gold_labels.py \
  --root . \
  --db data/agent.db \
  --jsonl evals/retrieval/product_rag_gold_labels.jsonl
PYTHONPATH=src python3 tools/product_rag_gold_cases.py \
  --root . \
  --jsonl evals/retrieval/product_rag_gold_cases.jsonl
PYTHONPATH=src python3 tools/archive_retrieval_eval.py \
  --root . \
  --db data/agent.db \
  --cases evals/retrieval/product_rag_gold_cases.jsonl \
  --limit 10 \
  --json evals/retrieval/product_rag_fts_baseline_report.json
```

Non-gating draft simulation:

```bash
PYTHONPATH=src python3 tools/product_rag_simulation_manifest.py --root . --json evals/retrieval/product_rag_simulation_manifest.json
```
