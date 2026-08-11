# Retrieval Evaluation Plan

Status: draft; PRM-3 FTS baseline implemented; PRM-7 baseline gate recorded; PRM-24 product RAG eval set recorded
Last updated: 2026-08-11

## Baseline

The first baseline is persistent SQLite FTS over retained archive posts with
metadata filters. Knowledge Atoms and topics are not required for search.

PRM-3 implementation:

- Search API: `src/db/archive_search.py`.
- Identity/chunk mapper: `src/db/archive_documents.py`.
- Tests: `tests/test_archive_search.py` and `tests/test_archive_documents.py`.
- Backend: existing persistent SQLite FTS5 table `posts_fts`.
- Canonical rows: `posts` joined to `raw_posts`.
- No vector backend, embedding provider, Knowledge Atom dependency, production
  schema migration, or full archive indexing job is introduced.

Query behavior:

- A strict `AND` FTS query runs first.
- If strict matching returns no rows, the same terms run through deterministic
  `OR` fallback for verbose/concept-like natural-language queries.
- Search excludes blank canonical bodies with `length(trim(posts.content)) > 0`.
- Results are ordered by SQLite `bm25(posts_fts)`, then post date and ID.
- Returned snippets are bounded by SQLite FTS `snippet`; raw snippets must not
  be printed in test logs or committed evidence.

Supported filters:

- channel username;
- language;
- half-open date range;
- reacted-only or specific `signal_feedback.feedback` values;
- `user_post_tags.tag`;
- linked `projects.name` through `post_project_links`.

Minimum result schema:

| Field | Source |
| --- | --- |
| `archive_document_id` | PRM-2 document/chunk identity |
| `post_archive_document_id` | PRM-2 post identity |
| `post_id` | `posts.id` |
| `raw_post_id` | `posts.raw_post_id` |
| `channel_username` | `posts.channel_username` |
| `channel_id` | `raw_posts.channel_id` |
| `message_id` | `raw_posts.message_id` |
| `posted_at` | `posts.posted_at` |
| `source_url` | `raw_posts.message_url` with Telegram-coordinate fallback |
| `language` | `posts.language_detected`, default `unknown` |
| `snippet` | bounded SQLite FTS snippet |
| `rank` | SQLite `bm25(posts_fts)` |
| `content_hash` | PRM-2 full-post content hash |
| `duplicate_cluster_id` | PRM-2 exact duplicate cluster when known |
| `repost_cluster_id` | PRM-2 hash-only forwarded-source candidate |
| `chunk_index` / `chunk_count` | PRM-2 chunk metadata |
| `reaction_count` | aggregate `signal_feedback` count |
| `tag_count` | aggregate `user_post_tags` count |
| `project_names` | linked project names |

## Dataset

Use `evals/retrieval/query_set_candidate.jsonl` as candidate input. Human
approval is required before labels count as gold evidence.

PRM-1 inspection result:

| Measure | Value |
| --- | ---: |
| Candidate rows | 50 |
| Rows with `human_approved=false` | 50 |
| Rows with expected post IDs | 0 |
| Rows with expected source URLs | 0 |
| Rows with copied evidence text keys | 0 |

Category distribution:

| Category | Count |
| --- | ---: |
| `exact_known_item` | 8 |
| `semantic_topic` | 8 |
| `case_study` | 8 |
| `comparison` | 6 |
| `freshness_news` | 6 |
| `project_life_application` | 6 |
| `distractor` | 4 |
| `no_answer` | 4 |

Candidate cases are useful for shaping coverage, not for pass/fail scoring.
Agent-generated expected labels, inferred source URLs, or guessed citations must
not be promoted to gold evidence.

## Gold Label Promotion

Gold labels must live outside `query_set_candidate.jsonl` in a separate
human-approved label file created after PRM-1. Each approved case must include:

- `case_id` matching the candidate row;
- `human_approval_ref` pointing to the operator-provided approval record;
- stable archive document IDs or Telegram source URLs;
- expected relevant/ranking behavior;
- freshness expectation when time matters;
- no-answer expectation when applicable;
- allowed distractors or ambiguity notes;
- privacy/sanitization status.

Gold label files must not include copied raw Telegram post bodies, long
captions, raw JSON, tag notes, feedback labels, or generated private report
text. Retrieval scoring commands in PRM-7 must separate unapproved candidate
rows from human-approved gold rows in their output.

## Metrics

| Metric | Gold Scoring Status | Candidate Diagnostic Status |
| --- | --- | --- |
| hit@10 | Requires human-approved expected document/post/source labels | Not scored |
| MRR | Requires human-approved expected document/post/source labels | Not scored |
| citation precision | Requires human-approved expected document/post/source labels | Not scored |
| stale-document rejection | Requires human-approved stale/forbidden labels | Not scored |
| no-answer accuracy | Requires human-approved no-answer labels | Not scored |
| duplicate top-10 result rate | Scored for gold rows when present | Diagnostic only |
| p95 local retrieval latency | Scored for the run | Diagnostic only |
| reacted-post search availability after sync | Aggregate fast-lane diagnostic | Aggregate fast-lane diagnostic |

## PRM-24 Product RAG Eval Set

PRM-24 adds a product-level RAG eval layer before any vector/backend adoption.
It is intentionally split into candidate questions, human-approved gold labels,
thresholds, a derived scoreable gold-cases view, a baseline report, and a
privacy-safe manifest.

Files:

| File | Purpose |
| --- | --- |
| `evals/retrieval/product_rag_candidate.jsonl` | 50 candidate product questions; not gold evidence |
| `evals/retrieval/product_rag_gold_labels.jsonl` | 50 operator-approved generated seed gold labels; no raw text or source URLs |
| `evals/retrieval/product_rag_gold_cases.jsonl` | derived scoreable view that merges candidate queries with approved labels for eval only |
| `evals/retrieval/product_rag_thresholds.json` | proposed RAG acceptance thresholds |
| `evals/retrieval/product_rag_eval_manifest.json` | generated privacy-safe coverage/gate manifest |
| `evals/retrieval/product_rag_fts_baseline_report.json` | privacy-safe SQLite FTS/query-planner baseline report |

Candidate category distribution:

| Category | Count |
| --- | ---: |
| `archive_recall` | 10 |
| `semantic_phrasing` | 10 |
| `project_fit` | 8 |
| `linked_source_freshness` | 8 |
| `no_answer` | 7 |
| `decision_support` | 7 |

Proposed acceptance thresholds:

| Metric | Direction | Threshold |
| --- | --- | ---: |
| `recall_at_5` | >= | 0.70 |
| `recall_at_10` | >= | 0.85 |
| `citation_precision` | >= | 0.90 |
| `no_answer_accuracy` | >= | 0.90 |
| `stale_rejection` | >= | 0.85 |
| `duplicate_top10_rate` | <= | 0.15 |
| `latency_ms_p95` | <= | 1500 ms |

Manifest command:

```bash
PYTHONPATH=src python3 tools/product_rag_eval_manifest.py --root . --json evals/retrieval/product_rag_eval_manifest.json
```

Current PRM-24 manifest result:

```text
product_rag_eval_manifest: cases=50 gold_labels=50 output=evals/retrieval/product_rag_eval_manifest.json
```

Gold-label materialization and scoring commands:

```bash
PYTHONPATH=src python3 tools/product_rag_seed_gold_labels.py --root . --db data/agent.db --jsonl evals/retrieval/product_rag_gold_labels.jsonl
PYTHONPATH=src python3 tools/product_rag_gold_cases.py --root . --jsonl evals/retrieval/product_rag_gold_cases.jsonl
PYTHONPATH=src python3 tools/archive_retrieval_eval.py --root . --db data/agent.db --cases evals/retrieval/product_rag_gold_cases.jsonl --limit 10 --json evals/retrieval/product_rag_fts_baseline_report.json
```

Current PRM-24 baseline result:

```text
archive_retrieval_eval: rows=50 gold=50 candidates=0 output=evals/retrieval/product_rag_fts_baseline_report.json
```

Boundary:

- `gold_labels.status=human_approved_gold_labels_present`;
- `gold_labels.coverage_status=full_coverage`;
- current approved labels cover all 50 PRM-24 rows under operator approval
  `operator-approval-2026-08-11-all-50-generated-gold`;
- label quality is explicitly
  `operator_approved_generated_seed_not_independent_human_review`;
- the candidate file remains `human_approved=false` and label-free; the
  derived gold-cases file is the scorer input;
- the manifest omits query text, source URLs, snippets, raw Telegram text, and
  provider payloads;
- `vector_backend_gate.vector_backend_adopted=false`;
- `vector_backend_gate.embeddings_run=false`.

Baseline metrics:

| Metric | Value | Interpretation |
| --- | ---: | --- |
| `hit_at_10` | 1.0 | generated source labels are recovered by the deterministic planner |
| `mrr` | 1.0 | generated source labels are first-rank under the seed method |
| `citation_precision` | 1.0 | generated seed source labels match returned citations |
| `no_answer_accuracy` | 0.0 | raw FTS returns related evidence for no-answer/control questions; answer-level refusal still needs PRM-28 gating |
| `stale_rejection` | null | no stale/forbidden document labels were approved in this generated seed set |
| `duplicate_top10_rate` | 0.004 | below proposed duplicate threshold |
| `latency_ms_p95` | 46.912 ms | below proposed local latency threshold |
| `reacted_post_searchability` | 0.967742 | aggregate local archive diagnostic |

The optional draft simulation receipt remains historical non-gating evidence:
it checked that prepared drafts were unapproved before the operator promoted
the seven no-answer drafts to gold labels on 2026-08-10. It is superseded for
coverage by the 2026-08-11 50-row generated seed label set.

For future independent review, use
[the operator labeling runbook](PRODUCT_RAG_LABELING_RUNBOOK.md).

PRM-7 result path:

```text
evals/retrieval/prm7_fts_baseline_report.json
```

## PRM-3 Latency Evidence

The PRM-3 latency run used candidate queries as an unapproved load set only. It
does not establish hit@10, MRR, citation precision, freshness rejection, or
no-answer accuracy.

Command:

```bash
PYTHONPATH=src python3 - <<'PY'
import json
import sqlite3
import time
from pathlib import Path
from statistics import quantiles

from db.archive_search import ArchiveSearchError, search_telegram_archive

rows = [json.loads(line) for line in Path('evals/retrieval/query_set_candidate.jsonl').read_text().splitlines() if line.strip()]
connection = sqlite3.connect('file:data/agent.db?mode=ro', uri=True)
connection.row_factory = sqlite3.Row
latencies_ms = []
result_counts = []
errors = []
try:
    for row in rows:
        started = time.perf_counter()
        try:
            results = search_telegram_archive(connection, row['query'], limit=10)
            result_counts.append(len(results))
        except (ArchiveSearchError, sqlite3.Error) as exc:
            errors.append({'case_id': row.get('case_id'), 'error_type': type(exc).__name__})
            result_counts.append(0)
        latencies_ms.append((time.perf_counter() - started) * 1000)
finally:
    connection.close()
ordered = sorted(latencies_ms)
p95 = ordered[int(len(ordered) * 0.95) - 1] if ordered else 0.0
print(json.dumps({
    'query_file': 'evals/retrieval/query_set_candidate.jsonl',
    'dataset_status': 'candidate_unapproved_latency_only_not_gold',
    'sample_size': len(rows),
    'successful_searches': len(rows) - len(errors),
    'errors': errors,
    'result_count_min': min(result_counts) if result_counts else 0,
    'result_count_max': max(result_counts) if result_counts else 0,
    'result_count_nonzero_queries': sum(1 for count in result_counts if count > 0),
    'latency_ms_min': round(min(latencies_ms), 3) if latencies_ms else 0.0,
    'latency_ms_median': round(quantiles(latencies_ms, n=2)[0], 3) if len(latencies_ms) >= 2 else 0.0,
    'latency_ms_p95': round(p95, 3),
    'latency_ms_max': round(max(latencies_ms), 3) if latencies_ms else 0.0,
    'printed_raw_telegram_text': False,
}, ensure_ascii=True, sort_keys=True))
PY
```

Result:

```json
{"dataset_status": "candidate_unapproved_latency_only_not_gold", "errors": [], "latency_ms_max": 454.038, "latency_ms_median": 43.242, "latency_ms_min": 15.008, "latency_ms_p95": 63.484, "printed_raw_telegram_text": false, "query_file": "evals/retrieval/query_set_candidate.jsonl", "result_count_max": 10, "result_count_min": 10, "result_count_nonzero_queries": 50, "sample_size": 50, "successful_searches": 50}
```

The command opened `data/agent.db` read-only and printed no raw Telegram text.

## PRM-7 Baseline Gate Evidence

PRM-7 added deterministic evaluator code:

- `src/db/archive_retrieval_eval.py`
- `tools/archive_retrieval_eval.py`
- `tests/test_archive_retrieval_eval.py`

The evaluator separates human-approved gold rows from unapproved candidate rows.
It omits query text, snippets, source URLs, raw Telegram text, and provider
payloads from the JSON report.

Command:

```bash
PYTHONPATH=src python3 tools/archive_retrieval_eval.py --root . --db data/agent.db --cases evals/retrieval/query_set_candidate.jsonl --limit 10 --json evals/retrieval/prm7_fts_baseline_report.json
```

Result:

```text
archive_retrieval_eval: rows=50 gold=0 candidates=50 output=evals/retrieval/prm7_fts_baseline_report.json
```

Report summary:

| Measure | Value |
| --- | ---: |
| Gold rows | 0 |
| Candidate rows | 50 |
| Candidate p95 latency | 59.988 ms |
| Candidate duplicate top-10 rate | 0.008 |
| Reacted-post searchability | 0.956522 |
| Vector backend adopted | false |
| Embeddings run | false |

Gold metrics are present but intentionally unscored:

| Metric | Value |
| --- | --- |
| `hit_at_10` | null |
| `mrr` | null |
| `citation_precision` | null |
| `stale_rejection` | null |
| `no_answer_accuracy` | null |
| `duplicate_top10_rate` | null |
| `latency_ms_p95` | `0.0` |
| `reacted_post_searchability` | `0.956522` |

This section is historical PRM-7 evidence. The vector gate was closed with
`vector_backend_gate.status=blocked_no_human_approved_gold` at that time.
Current PRM-24 now has a full generated seed gold set and baseline report, but
still lacks independent human-reviewed labels and PRM-28 product chat
acceptance evidence.

Verification:

```text
python3 -m pytest tests/test_archive_retrieval_eval.py tests/test_archive_search.py tests/test_archive_documents.py tests/test_reaction_fast_lane.py -q
21 passed in 0.24s
python3 -m pytest tests/ -q
1 failed, 992 passed, 281 subtests passed in 266.22s
FAILED tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
```

## Failure Taxonomy

- missing archive document;
- missing source URL;
- FTS tokenization miss;
- language mismatch;
- duplicate/repost crowding;
- stale result selected for freshness query;
- no-answer false positive;
- atom-gated invisibility;
- assistant synthesis ignores retrieved evidence.

## Hybrid ADR Gate

PRM-7 may propose embeddings/hybrid retrieval only after baseline failures are
measured. The ADR must compare recall, latency, update complexity, privacy,
backup/rollback, operational overhead, cost, and repository fit.

PRM-7 ADR gate:

```text
docs/adr/ADR-002-vector-backend-gate.md
```

ADR-002 is `proposed_not_accepted` and makes a negative decision for now: no
vector backend is adopted because there is still no full approved product gold
set or measured recall/citation failure evidence that justifies vector work.
