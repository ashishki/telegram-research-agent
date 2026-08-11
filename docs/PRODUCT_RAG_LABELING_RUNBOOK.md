# Product RAG Gold Labeling Runbook

Status: generated seed labels approved for PRM-24; future independent review optional

This is the default path to promote a PRM-24 candidate to independent
human-reviewed gold evidence. Codex must not infer labels from plausible
operator behavior, the candidate question, or repository text unless the
operator explicitly approves a generated seed-label run.

For PRM-24, the operator approved such a generated seed-label run on
2026-08-11:

```text
operator-approval-2026-08-11-all-50-generated-gold
```

That approval covers the committed 50-row generated seed set in
`evals/retrieval/product_rag_gold_labels.jsonl`. The labels use local archive
document/post IDs or explicit no-answer expectations and contain no raw
Telegram text or source URLs. This approval does not approve embeddings, vector
backend adoption, provider egress, live web research, migrations, production
writes, service start, PRM-27, PRM-28, or dogfood.

For each chosen `case_id` in `evals/retrieval/product_rag_candidate.jsonl`, the
operator supplies a row in `evals/retrieval/product_rag_gold_labels.jsonl`.
Use stable source IDs/URLs only; do not paste Telegram content.

```json
{"case_id":"PRAG-ARCH-001","human_approved":true,"human_approval_ref":"operator-labels-YYYY-MM-DD","expected_archive_document_ids":["tg:<channel_id>:<message_id>"],"expected_source_urls":["https://t.me/<channel>/<message_id>"],"freshness_expectation":"archive_only"}
{"case_id":"PRAG-NOANS-001","human_approved":true,"human_approval_ref":"operator-labels-YYYY-MM-DD","expected_no_answer":true,"freshness_expectation":"not_applicable"}
```

Required fields:

- `case_id` must exist exactly once in the candidate file;
- `human_approved` must be `true`;
- `human_approval_ref` must identify your explicit approval record;
- provide at least one expected archive document ID, post ID, or source URL,
  or set `expected_no_answer=true`;
- add stale/forbidden IDs or URLs where relevant, without copied text.

After you provide explicit labels, run:

```bash
PYTHONPATH=src python3 tools/product_rag_eval_manifest.py --root . --json evals/retrieval/product_rag_eval_manifest.json
```

For the approved PRM-24 generated seed set, run:

```bash
PYTHONPATH=src python3 tools/product_rag_seed_gold_labels.py --root . --db data/agent.db --jsonl evals/retrieval/product_rag_gold_labels.jsonl
PYTHONPATH=src python3 tools/product_rag_gold_cases.py --root . --jsonl evals/retrieval/product_rag_gold_cases.jsonl
PYTHONPATH=src python3 tools/archive_retrieval_eval.py --root . --db data/agent.db --cases evals/retrieval/product_rag_gold_cases.jsonl --limit 10 --json evals/retrieval/product_rag_fts_baseline_report.json
PYTHONPATH=src python3 tools/product_rag_eval_manifest.py --root . --json evals/retrieval/product_rag_eval_manifest.json
```

This runbook does not approve embeddings, vector adoption, provider egress,
migrations, production writes, service start, or dogfood.

## Prepared Drafts

`evals/retrieval/product_rag_gold_label_drafts.jsonl` contains seven proposed
negative-control outcomes. These are review aids only: every row remains
`human_approved=false`, has no `human_approval_ref`, is not read by the
manifest/scorer, and must be copied into the gold label file only after you
explicitly confirm the outcome and supply the approval reference.
