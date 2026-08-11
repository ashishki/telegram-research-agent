# ADR-004: PRM-27 Local Vector Sidecar

Status: accepted_local_sidecar
Date: 2026-08-11
Approval: operator-approval-2026-08-11-full-stack-local-vector-telegram-llm
Supersedes-for-PRM-27: ADR-003 `accepted_no_vector_for_now`

## Context

ADR-003 accepted the no-vector path because the generated PRM-24 seed eval did
not prove an independent recall failure. The operator later explicitly asked to
finish the product path with vectors, RAG, LLM, Telegram AI, and then test the
system before giving dogfood feedback.

This approval changes the PRM-27 implementation gate, but it does not approve
external embedding providers, production database migrations, broad provider
egress, live web research, compatibility cleanup, release claims, or PRM-19
dogfood start.

## Decision

Adopt a local SQLite sidecar vector index for PRM-27:

- canonical `raw_posts`, `posts`, and `posts_fts` remain unchanged;
- the sidecar lives outside the canonical DB, defaulting to
  `data/vector/archive_vector.sqlite`;
- `data/vector/` is ignored by git because it contains derived private archive
  state;
- vectorization uses deterministic local hashing
  `local_hashing_text_vector.v1`, not a provider embedding model;
- retrieval can run as SQLite FTS only, local vector only, or hybrid FTS-first
  fallback. The default hybrid policy returns FTS evidence when FTS has matches
  and uses vector fallback only on FTS misses; an explicit internal `always`
  policy exists for fusion tests/diagnostics;
- Telegram `/research`, `/brief`, and ordinary-message auto routing use hybrid
  archive retrieval only when `PRM_ARCHIVE_HYBRID_RETRIEVAL=approved` is set;
- LLM-backed `/chat` and auto-LLM routing remain separately gated by
  `PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1` and
  `PRM_TELEGRAM_AUTO_LLM_ROUTER=1`.

## Privacy And Cost Budget

| Control | Value |
| --- | --- |
| Embedding provider | local deterministic hashing only |
| Embedding model | `local_hashing_text_vector.v1` |
| Vector backend | local SQLite sidecar |
| Provider egress for vectorization | false |
| Raw Telegram corpus provider egress | false |
| Canonical DB mutation | false |
| Sidecar persistence | allowed under `data/vector/`, gitignored |
| Production migrations | not approved by this ADR |
| Max provider cost | $0 for vector indexing/search |
| Logs/receipts | aggregate counts, paths redacted from research receipts, bounded snippets only in user-facing answers |

## Rollback

Rollback is deleting or moving aside the derived sidecar and disabling the
hybrid flag:

```text
unset PRM_ARCHIVE_HYBRID_RETRIEVAL
rm data/vector/archive_vector.sqlite
```

The canonical archive database does not need restoration because the indexer
opens it read-only and writes only the sidecar. Before any long-running
production rebuild, take a normal database backup or snapshot so operator
rollback evidence can show the canonical source state was preserved.

## Validation

Required focused validation for PRM-27:

```text
python3 -m py_compile src/db/archive_vector.py src/db/archive_search.py src/assistant/pi_facade.py src/assistant/memory_research.py src/assistant/rag_context_pack.py src/bot/handlers.py src/main.py
PYTHONPATH=src python3 -m pytest tests/test_archive_vector.py tests/test_archive_search.py tests/test_archive_retrieval_eval.py tests/test_rag_context_pack.py tests/test_memory_research.py tests/test_pi_facade_archive_vector.py tests/test_cli.py tests/test_handlers.py -q
```

Optional production-sidecar eval, after the local sidecar exists:

```text
python3 src/main.py memory vector-index --json
PYTHONPATH=src python3 tools/archive_retrieval_eval.py --root . --db data/agent.db --cases evals/retrieval/product_rag_gold_cases.jsonl --limit 10 --retrieval-mode hybrid-local-vector --vector-index-path data/vector/archive_vector.sqlite --json evals/retrieval/product_rag_hybrid_local_vector_report.json
```

The report must not print raw Telegram text, snippets, source URLs, prompts,
provider payloads, or external embedding payloads.

Current aggregate report:
`evals/retrieval/product_rag_hybrid_local_vector_report.json`. Metrics on the
50 generated seed gold cases are hit@10=1.0, MRR=1.0,
citation_precision=1.0, duplicate_top10_rate=0.004, latency_ms_p95=59.077, and
reacted_post_searchability=0.967742. Raw retrieval no_answer_accuracy remains
0.0, so PRM-28 answer gating remains the product no-answer boundary.

## Non-Approvals

This ADR is not approval for:

- PRM-19 dogfood start;
- Telegram service installation/enabling/start as dogfood;
- live web research;
- external embedding providers or hosted vector services;
- provider synthesis without the existing provider-egress switches;
- production database migrations or canonical archive writes;
- committing private Telegram-derived sidecar files;
- archive/delete/move of compatibility files.
