# RAG Data Readiness

Status: PRM-1 empirical evidence recorded; PRM-2 document contract recorded; PRM-5 reaction fast-lane evidence recorded; PRM-24 product RAG eval set recorded
Last updated: 2026-08-11

## PRM-1 Boundary

This PRM-1 pass was read-only. It did not run live Telegram ingestion, reaction
sync, LLM extraction, Frontier, Radar, report generation, full archive indexing,
embeddings, or external web research. It did not modify production database
contents and did not copy raw Telegram post text into docs, fixtures, or logs.

`sqlite3` CLI was not available, so SQLite inspection used Python's standard
`sqlite3` module with `file:data/agent.db?mode=ro`.

## Corpus Inventory

Observed canonical storage surfaces:

- `raw_posts`: source metadata and retained source payload fields.
- `posts`: normalized archive row and current candidate body source for search.
- `posts_fts`: SQLite FTS5 derived index over `posts.content`; not canonical.
- `signal_feedback`, `user_post_tags`, `reaction_sync_state`: operator
  reaction/feedback linkage metadata; aggregate counts only are safe to record.

Configured channel coverage:

| Measure | Value |
| --- | ---: |
| Configured channels | 21 |
| Active channels | 21 |
| Inactive channels | 0 |
| Configured language `ru` | 21 |
| High priority | 8 |
| Medium priority | 8 |
| Low priority | 5 |
| `market_business_ai` group | 5 |
| Configured channels with raw posts | 21 |
| Configured channels missing raw posts | 0 |
| Unconfigured DB channels | 0 |

Table counts:

| Table | Count |
| --- | ---: |
| `raw_posts` | 3,477 |
| `posts` | 3,477 |
| `posts_fts` | 3,477 |
| `knowledge_atoms` | 1,346 |
| `idea_threads` | 1,290 |
| `signal_feedback` | 23 |
| `user_post_tags` | 23 |
| `reaction_sync_state` | 23 |

Per-configured-channel archive coverage:

| Channel | Raw posts | Posts | FTS rows |
| --- | ---: | ---: | ---: |
| `@gleb_pro_ai` | 180 | 180 | 180 |
| `@tired_glebmikheev` | 167 | 167 | 167 |
| `@ai_newz` | 154 | 154 | 154 |
| `@neuraldeep` | 181 | 181 | 181 |
| `@cryptoEssay` | 153 | 153 | 153 |
| `@llm_under_hood` | 118 | 118 | 118 |
| `@silent_ai_cto` | 38 | 38 | 38 |
| `@its_capitan` | 60 | 60 | 60 |
| `@log_OS_ru` | 37 | 37 | 37 |
| `@data_secrets` | 613 | 613 | 613 |
| `@leadgr` | 114 | 114 | 114 |
| `@leadgenvalley` | 89 | 89 | 89 |
| `@Redmadnews` | 138 | 138 | 138 |
| `@doronin_aiforfriends` | 23 | 23 | 23 |
| `@max_about_ai` | 7 | 7 | 7 |
| `@oestick` | 50 | 50 | 50 |
| `@codecamp` | 817 | 817 | 817 |
| `@NeuralShit` | 242 | 242 | 242 |
| `@kyrillic` | 206 | 206 | 206 |
| `@exitsexist` | 81 | 81 | 81 |
| `@huntermikevolkov` | 9 | 9 | 9 |

## Readiness Metrics

Text and indexability:

| Measure | Value |
| --- | ---: |
| Raw rows with non-empty `text` | 2,793 |
| Raw rows with non-empty `media_caption` | 2,192 |
| Raw rows with non-empty `image_description` | 243 |
| Posts with non-empty normalized `content` | 3,033 |
| Posts with blank/null normalized `content` | 444 |
| Posts with `word_count <= 0` | 444 |
| FTS rows | 3,477 |
| Posts missing FTS row | 0 |
| FTS rows without post | 0 |
| Raw rows without normalized post | 0 |
| Posts without raw row | 0 |
| Blank posts with any raw text/caption/image-description source | 0 |
| Blank posts with no raw text/caption/image-description source | 444 |

Interpretation: row-level archive and FTS coverage is complete, but only 3,033
of 3,477 posts are text-indexable. The 444 blank rows should be excluded from
retrieval evaluation and assistant citation candidates until a human-approved
policy says otherwise.

Metadata coverage:

| Measure | Value |
| --- | ---: |
| Raw rows missing `channel_username` | 0 |
| Raw rows missing `channel_id` | 0 |
| Raw rows missing `message_id` | 0 |
| Raw rows missing `posted_at` | 0 |
| Raw rows with blank `raw_json` | 3,091 |
| Raw rows with non-empty `raw_json` | 386 |
| Posts missing `channel_username` | 0 |
| Posts missing `posted_at` | 0 |
| Posts missing `normalized_at` | 0 |
| Duplicate raw `(channel_id, message_id)` pairs | 0 |
| Duplicate post `raw_post_id` refs | 0 |

Interpretation: archive identity should not depend on `raw_json`, because most
rows have blank `raw_json`. PRM-2 should base identity on `channel_username`,
`channel_id`, `message_id`, `posted_at`, `message_url`, and `posts.id` /
`raw_post_id` mapping.

Date coverage:

| Measure | Value |
| --- | --- |
| Raw min date | 2026-03-30 |
| Raw max date | 2026-07-20 |
| Raw unique dates | 113 |
| Raw invalid dates | 0 |
| Raw future dates after 2026-07-26 | 0 |
| Posts min date | 2026-03-30 |
| Posts max date | 2026-07-20 |
| Posts unique dates | 113 |
| Posts invalid dates | 0 |
| Posts future dates after 2026-07-26 | 0 |

Language coverage:

| Language | Total posts | Blank content | Nonblank content |
| --- | ---: | ---: | ---: |
| `en` | 24 | 0 | 24 |
| `ru` | 3,004 | 0 | 3,004 |
| `unknown` | 449 | 444 | 5 |

URL coverage:

| Measure | Value |
| --- | ---: |
| Raw rows with Telegram `message_url` | 3,477 |
| Raw rows missing `message_url` | 0 |
| Raw URLs matching `https://t.me/<channel>/<message_id>` | 3,477 |
| Raw malformed Telegram URLs | 0 |
| Raw URL channel mismatches | 0 |
| Raw URL message ID mismatches | 0 |
| Posts missing source URL via raw row | 0 |
| Posts with extracted content URLs | 308 |
| Posts without extracted content URLs | 3,169 |
| Sum of extracted content URLs | 366 |

Duplicate and repost coverage:

| Measure | Value |
| --- | ---: |
| Stored content hash column | absent |
| Ephemeral hashable posts | 3,033 |
| Unique ephemeral content hashes | 3,007 |
| Exact duplicate groups | 19 |
| Exact duplicate rows | 45 |
| Exact duplicate excess rows | 26 |
| Largest exact duplicate group | 5 |
| Cross-channel exact duplicate groups | 15 |
| Raw rows with non-empty `forward_from` | 283 |

Interpretation: exact duplicate excess is small at 26 rows, but PRM-2 should add
a stable content-hash and duplicate cluster contract before retrieval scoring.
The 283 forwarded rows should be treated as repost candidates, not automatically
collapsed without preserving source citations.

Reaction and feedback coverage:

| Measure | Value |
| --- | ---: |
| `signal_feedback` rows | 23 |
| Distinct feedback post IDs | 23 |
| Unmatched feedback post IDs | 0 |
| `user_post_tags` rows | 23 |
| Distinct tagged post IDs | 23 |
| Unmatched tagged post IDs | 0 |
| Tag rows with notes | 23 |
| `reaction_sync_state` rows | 23 |
| Distinct reaction message refs | 23 |
| Reactions matched to raw posts | 23 |
| Reactions matched to normalized posts | 23 |
| Reactions unmatched to raw posts | 0 |

## PRM-5 Reaction Fast-Lane Readiness

The PRM-5 implementation adds a read-only `reaction_fast_lane.v1` receipt over
existing rows. It does not run live Telegram sync, LLM extraction, report
generation, full archive indexing, embeddings, or database migration. The
receipt intentionally counts archive search availability before atom/topic/rank
processing, so reacted posts remain searchable even when downstream Knowledge
Atom extraction is incomplete.

Local aggregate result on 2026-07-26:

| Measure | Value |
| --- | ---: |
| Personal reaction events detected | 23 |
| Unique reacted posts | 23 |
| Posts resolved | 23 |
| Archive posts indexed | 22 |
| Archive documents indexed | 26 |
| Searchable archive posts | 22 |
| Searchable archive documents | 26 |
| Archive documents excluded | 1 |
| Enrichment attempts | 22 |
| Enrichment successes | 3 |
| Enrichment failures | 19 |
| Unique atoms linked | 3 |
| Topic link attempts | 22 |
| Topic link successes | 22 |
| Topic link failures | 0 |
| Ranking effects | 0 |

Stage statuses:

| Stage | Status |
| --- | --- |
| Reaction detection | `complete` |
| Source resolution | `complete` |
| Archive index | `partial` |
| Assistant search | `partial` |
| Enrichment | `partial` |
| Topic linkage | `complete` |
| Ranking | `not_evaluated` |

Incomplete-stage reasons:

| Reason | Count |
| --- | ---: |
| `empty_canonical_body` | 1 |
| `knowledge_atom_not_extracted` | 19 |
| `ranking_not_evaluated` | 22 |

PRM-5 fixture verification also covers the W29 failure mode from the product
audit: seven synthetic personal reactions, zero atoms, and seven searchable
archive documents.

## Privacy Exclusions

Committed evidence must exclude:

- raw Telegram post body text, captions, image descriptions, and `raw_json`;
- generated private reports under `data/output/**`;
- source event JSONL under `data/events/**`;
- local SQLite database files under `data/agent.db*`;
- operator feedback text, tag notes, reaction emoji semantics, and preference
  labels beyond aggregate linkage counts;
- any embedding payloads or external provider transcripts.

Retrieval and assistant evidence should use post IDs, source URLs, channel/date
metadata, counts, and hashes. Full post bodies may be read locally only when
needed for deterministic hashing or bounded retrieval, and must not be printed,
logged, committed, or sent to external providers without explicit human
approval.

## Current Data Decisions

For PRM-1 evidence:

- Current normalized body source: `posts.content` when non-empty.
- Source citation: `raw_posts.message_url`.
- Stable local mapping: `posts.id` joined to `raw_posts.id` by
  `posts.raw_post_id`.
- Non-indexable exclusion: rows with blank `posts.content` and no raw text,
  caption, or image description source.
- Duplicate policy: measure exact duplicate/repost candidates only; do not
  collapse rows until PRM-2 defines identity and dedupe fields.
- Provider egress boundary: no raw Telegram text to LLMs, embedding providers,
  external skills, or web research from PRM-1.

## PRM-2 Archive Document Contract

Implementation surface:

- Pure mapper: `src/db/archive_documents.py`.
- Test coverage: `tests/test_archive_documents.py`.
- No production schema migration is part of PRM-2.
- No second full-text store is introduced by this contract.

Canonical row inputs:

| Field | Source | Purpose |
| --- | --- | --- |
| `post_id` | `posts.id` | local row reference, not stable identity |
| `raw_post_id` | `posts.raw_post_id` | local canonical raw-row join |
| `channel_username` | `raw_posts.channel_username` / `posts.channel_username` | display and URL fallback |
| `channel_id` | `raw_posts.channel_id` | stable Telegram channel coordinate |
| `message_id` | `raw_posts.message_id` | stable Telegram message coordinate |
| `posted_at` | `posts.posted_at` | date and freshness filtering |
| `source_url` | `raw_posts.message_url` | citation URL |
| `language` | `posts.language_detected`, default `unknown` | language filter |
| `content` | `posts.content` when non-empty | canonical searchable body |
| `forward_from` | `raw_posts.forward_from` | repost-candidate cluster signal |

Stable identity fields:

| Field | Contract |
| --- | --- |
| `post_archive_document_id` | `tg:{channel_id}:{message_id}` |
| `archive_document_id` for normal posts | same as `post_archive_document_id` |
| `archive_document_id` for chunks | `tg:{channel_id}:{message_id}:chunk:{zero_padded_chunk_index}` |
| `chunk_index` | absent/`None` for normal posts; zero-based only when chunking is required |
| `chunk_count` | `1` for normal posts; total chunk count for long posts |
| `chunk_start_char` / `chunk_end_char` | offsets into the canonical `posts.content` body |

`post_id` and `raw_post_id` remain useful join keys, but they are not the
stable external document identity because they can change across restores,
imports, or fixture construction.

Body and hash contract:

- Canonical body source is non-empty `posts.content`.
- `content_hash` is the full-post hash used for duplicate grouping.
- Hash algorithm is `sha256:v1:ws-casefold`: trim, collapse whitespace to one
  space, casefold, then SHA-256.
- `chunk_content_hash` is computed from the chunk text. For normal posts it is
  equal to `content_hash`.
- Rows with blank canonical bodies are excluded from indexable archive
  documents with reason `empty_canonical_body`.

Chunking contract:

- Normal Telegram posts remain one coherent archive document.
- Default chunk threshold is 3,200 characters.
- Long posts split only when `len(posts.content) > 3200`.
- Splitting prefers paragraph, newline, then space boundaries before the hard
  threshold.
- Every chunk keeps the same `post_archive_document_id`, `post_id`,
  `raw_post_id`, channel, message ID, posted date, source URL, language, and
  full-post `content_hash`.
- Chunking must preserve exact post-level citation. Multiple chunks from the
  same Telegram post point to the same `raw_posts.message_url`.

Dedupe and repost contract:

- Exact duplicate clusters are derived when the same full-post `content_hash`
  appears on more than one distinct `post_archive_document_id`.
- Exact duplicate cluster ID format is `exact:{content_hash}`.
- `repost_cluster_id` is a hash-only forwarded-source candidate:
  `forward:{first_16_hex_chars}`. It must not expose the raw `forward_from`
  value in ordinary logs or committed evidence.
- Dedupe is a retrieval assembly behavior, not canonical-row deletion. All
  original Telegram source URLs remain citeable.
- Near-duplicate clustering is deferred until PRM-7 measures baseline failure
  modes; it must not be introduced as a hidden vector backend.

Incremental update contract:

- Recomputing archive documents from the same canonical rows must produce the
  same IDs and hashes.
- A content edit changes `content_hash` and any chunk boundaries for that post
  only.
- A new Telegram post creates a new `post_archive_document_id` from
  `channel_id` and `message_id`.
- A deleted or intentionally excluded row removes derived index documents only;
  canonical deletion/retention policy remains a separate human-approved path.
- Rebuilds must treat `posts_fts` and future archive indexes as derived state.

## Gold Query Process

`evals/retrieval/query_set_candidate.jsonl` contains candidate queries only.

PRM-1 candidate-set inspection:

| Measure | Value |
| --- | ---: |
| Candidate rows | 50 |
| `human_approved=false` rows | 50 |
| Candidate rows with expected post IDs | 0 |
| Candidate rows with expected source URLs | 0 |
| Candidate rows with copied evidence text keys | 0 |

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

A query becomes gold only when the human operator supplies or approves, in a
separate future label file:

- stable archive document IDs or Telegram source URLs;
- expected relevant/ranking behavior;
- freshness expectation;
- no-answer expectation when applicable;
- allowed distractors or known ambiguity;
- privacy/sanitization status.

Agent-generated candidates must remain `candidate_unapproved` and must not be
used as pass/fail gold evidence unless the operator explicitly approves a
generated seed-label run. Gold labels must reference IDs and optional source
URLs, not copied full post bodies.

## PRM-24 Product RAG Eval Set

`evals/retrieval/product_rag_candidate.jsonl` contains 50 product RAG candidate
questions for the pre-dogfood RAG gate:

| Category | Count |
| --- | ---: |
| `archive_recall` | 10 |
| `semantic_phrasing` | 10 |
| `project_fit` | 8 |
| `linked_source_freshness` | 8 |
| `no_answer` | 7 |
| `decision_support` | 7 |

The candidate file contains no expected source IDs, no expected source URLs, no
copied snippets, and no raw Telegram text. On 2026-08-11 the operator approved
Codex creating all 50 generated seed gold labels under
`operator-approval-2026-08-11-all-50-generated-gold`. The committed label file
contains 43 source-labelled rows using stable local archive document/post IDs
and 7 explicit no-answer rows; it contains no source URLs and no raw Telegram
text. The generated `product_rag_eval_manifest.json` records coverage,
thresholds, and gate status without query text or source URLs.

Baseline SQLite FTS/query-planner evidence is recorded in
`evals/retrieval/product_rag_fts_baseline_report.json`. It is privacy-safe and
contains counts/metrics only. Current metrics: hit@10=1.0,
citation_precision=1.0, latency p95=46.912 ms, duplicate_top10_rate=0.004,
no_answer_accuracy=0.0, stale_rejection=null.

Current gate status:

```text
gold_labels.status=human_approved_gold_labels_present
gold_labels.coverage_status=full_coverage
gold_labels.count=50
vector_backend_adopted=false
embeddings_run=false
```

This completes PRM-24 coverage/eval scaffolding as operator-approved generated
seed evidence. It does not approve embeddings, vector backend adoption,
provider egress, live web research, migrations, production writes, service
start, PRM-27, PRM-28, or dogfood.

## Exact Commands And Results

All commands below were run from
`/srv/openclaw-you/workspace/telegram-research-agent` on 2026-07-26.

SQLite CLI availability check:

```bash
sqlite3 -readonly data/agent.db '.tables'
```

Result:

```text
/bin/bash: line 1: sqlite3: command not found
```

Authoritative aggregate corpus command:

```bash
python3 - <<'PY'
import datetime as dt, hashlib, json, re, sqlite3
from collections import Counter, defaultdict
from pathlib import Path
import yaml
ROOT = Path('.')
DB_URI = 'file:data/agent.db?mode=ro'
NOW_DATE = dt.date(2026, 7, 26)
URL_RE = re.compile(r'^https://t\.me/([^/]+)/([0-9]+)(?:\?.*)?$')
WS_RE = re.compile(r'\s+')
def pct(n, d): return round((n / d) * 100, 2) if d else 0.0
def parse_date(value):
    if not value: return None
    text = str(value).strip()
    if text.endswith('Z'): text = text[:-1] + '+00:00'
    try: return dt.datetime.fromisoformat(text).date()
    except ValueError:
        try: return dt.date.fromisoformat(text[:10])
        except ValueError: return None
def one(conn, sql, params=()): return conn.execute(sql, params).fetchone()[0]
channels = yaml.safe_load((ROOT / 'src/config/channels.yaml').read_text()).get('channels') or []
configured = [str(ch.get('username', '')).strip() for ch in channels if ch.get('username')]
configured_set = set(configured)
result = {
    'database': 'data/agent.db',
    'open_mode': 'sqlite-uri-mode-ro',
    'inspection_date': '2026-07-26',
    'configured_channels': {
        'total': len(channels),
        'active': sum(1 for ch in channels if ch.get('active') is True),
        'inactive': sum(1 for ch in channels if ch.get('active') is False),
        'priority_counts': dict(sorted(Counter(str(ch.get('priority', 'missing')) for ch in channels).items())),
        'language_counts': dict(sorted(Counter(str(ch.get('language', 'missing')) for ch in channels).items())),
        'group_counts': dict(sorted(Counter(str(ch.get('group', 'none')) for ch in channels).items())),
    },
}
conn = sqlite3.connect(DB_URI, uri=True)
conn.row_factory = sqlite3.Row
try:
    raw_total = one(conn, 'SELECT COUNT(*) FROM raw_posts')
    post_total = one(conn, 'SELECT COUNT(*) FROM posts')
    fts_total = one(conn, 'SELECT COUNT(*) FROM posts_fts')
    result['table_counts'] = {table: one(conn, f'SELECT COUNT(*) FROM {table}') for table in ['raw_posts','posts','posts_fts','knowledge_atoms','idea_threads','signal_feedback','user_post_tags','reaction_sync_state']}
    raw_text = one(conn, "SELECT COUNT(*) FROM raw_posts WHERE text IS NOT NULL AND length(trim(text)) > 0")
    raw_caption = one(conn, "SELECT COUNT(*) FROM raw_posts WHERE media_caption IS NOT NULL AND length(trim(media_caption)) > 0")
    raw_image = one(conn, "SELECT COUNT(*) FROM raw_posts WHERE image_description IS NOT NULL AND length(trim(image_description)) > 0")
    post_content = one(conn, "SELECT COUNT(*) FROM posts WHERE content IS NOT NULL AND length(trim(content)) > 0")
    blank_posts = one(conn, "SELECT COUNT(*) FROM posts WHERE content IS NULL OR length(trim(content)) = 0")
    result['text_and_indexability'] = {'raw_text_nonempty': raw_text, 'raw_text_nonempty_pct': pct(raw_text, raw_total), 'raw_caption_nonempty': raw_caption, 'raw_caption_nonempty_pct': pct(raw_caption, raw_total), 'raw_image_description_nonempty': raw_image, 'raw_image_description_nonempty_pct': pct(raw_image, raw_total), 'posts_content_nonempty': post_content, 'posts_content_nonempty_pct': pct(post_content, post_total), 'posts_content_blank_or_null': blank_posts, 'posts_word_count_zero_or_negative': one(conn, 'SELECT COUNT(*) FROM posts WHERE word_count <= 0'), 'fts_rows': fts_total, 'fts_rows_pct_of_posts': pct(fts_total, post_total), 'posts_missing_fts_row': one(conn, 'SELECT COUNT(*) FROM posts p LEFT JOIN posts_fts f ON f.rowid = p.id WHERE f.rowid IS NULL'), 'fts_rows_without_post': one(conn, 'SELECT COUNT(*) FROM posts_fts f LEFT JOIN posts p ON p.id = f.rowid WHERE p.id IS NULL'), 'raw_without_normalized_post': one(conn, 'SELECT COUNT(*) FROM raw_posts r LEFT JOIN posts p ON p.raw_post_id = r.id WHERE p.id IS NULL'), 'posts_without_raw': one(conn, 'SELECT COUNT(*) FROM posts p LEFT JOIN raw_posts r ON r.id = p.raw_post_id WHERE r.id IS NULL'), 'blank_posts_with_any_raw_text_source': one(conn, "SELECT COUNT(*) FROM posts p JOIN raw_posts r ON r.id = p.raw_post_id WHERE length(trim(p.content)) = 0 AND ((r.text IS NOT NULL AND length(trim(r.text)) > 0) OR (r.media_caption IS NOT NULL AND length(trim(r.media_caption)) > 0) OR (r.image_description IS NOT NULL AND length(trim(r.image_description)) > 0))"), 'blank_posts_with_no_raw_text_source': one(conn, "SELECT COUNT(*) FROM posts p JOIN raw_posts r ON r.id = p.raw_post_id WHERE length(trim(p.content)) = 0 AND NOT ((r.text IS NOT NULL AND length(trim(r.text)) > 0) OR (r.media_caption IS NOT NULL AND length(trim(r.media_caption)) > 0) OR (r.image_description IS NOT NULL AND length(trim(r.image_description)) > 0))")}
    result['metadata_readiness'] = {'raw_missing_channel_username': one(conn, "SELECT COUNT(*) FROM raw_posts WHERE channel_username IS NULL OR length(trim(channel_username)) = 0"), 'raw_missing_channel_id': one(conn, 'SELECT COUNT(*) FROM raw_posts WHERE channel_id IS NULL'), 'raw_missing_message_id': one(conn, 'SELECT COUNT(*) FROM raw_posts WHERE message_id IS NULL'), 'raw_missing_posted_at': one(conn, "SELECT COUNT(*) FROM raw_posts WHERE posted_at IS NULL OR length(trim(posted_at)) = 0"), 'raw_json_null': one(conn, 'SELECT COUNT(*) FROM raw_posts WHERE raw_json IS NULL'), 'raw_json_blank': one(conn, "SELECT COUNT(*) FROM raw_posts WHERE raw_json IS NOT NULL AND length(trim(raw_json)) = 0"), 'raw_json_nonempty': one(conn, "SELECT COUNT(*) FROM raw_posts WHERE raw_json IS NOT NULL AND length(trim(raw_json)) > 0"), 'posts_missing_channel_username': one(conn, "SELECT COUNT(*) FROM posts WHERE channel_username IS NULL OR length(trim(channel_username)) = 0"), 'posts_missing_posted_at': one(conn, "SELECT COUNT(*) FROM posts WHERE posted_at IS NULL OR length(trim(posted_at)) = 0"), 'posts_missing_normalized_at': one(conn, "SELECT COUNT(*) FROM posts WHERE normalized_at IS NULL OR length(trim(normalized_at)) = 0"), 'raw_duplicate_channel_message_pairs': one(conn, 'SELECT COALESCE(SUM(cnt - 1), 0) FROM (SELECT COUNT(*) AS cnt FROM raw_posts GROUP BY channel_id, message_id HAVING cnt > 1)'), 'posts_duplicate_raw_post_refs': one(conn, 'SELECT COALESCE(SUM(cnt - 1), 0) FROM (SELECT COUNT(*) AS cnt FROM posts GROUP BY raw_post_id HAVING cnt > 1)')}
    raw_dates = [parse_date(row[0]) for row in conn.execute('SELECT posted_at FROM raw_posts')]
    post_dates = [parse_date(row[0]) for row in conn.execute('SELECT posted_at FROM posts')]
    raw_valid = [d for d in raw_dates if d]
    post_valid = [d for d in post_dates if d]
    result['date_coverage'] = {'raw_min_date': min(raw_valid).isoformat(), 'raw_max_date': max(raw_valid).isoformat(), 'raw_unique_dates': len(set(raw_valid)), 'raw_invalid_dates': len(raw_dates) - len(raw_valid), 'raw_future_dates_after_2026_07_26': sum(1 for d in raw_valid if d > NOW_DATE), 'posts_min_date': min(post_valid).isoformat(), 'posts_max_date': max(post_valid).isoformat(), 'posts_unique_dates': len(set(post_valid)), 'posts_invalid_dates': len(post_dates) - len(post_valid), 'posts_future_dates_after_2026_07_26': sum(1 for d in post_valid if d > NOW_DATE)}
    db_channels = {row['channel_username'] for row in conn.execute('SELECT DISTINCT channel_username FROM raw_posts')}
    result['channel_coverage'] = {'db_distinct_raw_channels': len(db_channels), 'configured_channels_with_raw_posts': len(configured_set & db_channels), 'configured_channels_missing_raw_posts': len(configured_set - db_channels), 'unconfigured_raw_channel_count': len(db_channels - configured_set), 'per_configured_channel_counts': [{'channel': ch, 'raw_posts': one(conn, 'SELECT COUNT(*) FROM raw_posts WHERE channel_username = ?', (ch,)), 'posts': one(conn, 'SELECT COUNT(*) FROM posts WHERE channel_username = ?', (ch,)), 'fts_rows': one(conn, 'SELECT COUNT(*) FROM posts p JOIN posts_fts f ON f.rowid = p.id WHERE p.channel_username = ?', (ch,))} for ch in configured]}
    lang_counts = Counter('missing_or_blank' if row[0] is None or str(row[0]).strip() == '' else str(row[0]).strip() for row in conn.execute('SELECT language_detected FROM posts'))
    result['language_coverage'] = {'posts_language_detected_counts': dict(sorted(lang_counts.items())), 'posts_missing_language_detected': lang_counts.get('missing_or_blank', 0), 'configured_non_ru_channels': sum(1 for ch in channels if str(ch.get('language', '')).strip() != 'ru'), 'by_language_blank_content': [dict(row) for row in conn.execute("SELECT COALESCE(NULLIF(trim(language_detected), ''), 'missing_or_blank') AS language, COUNT(*) AS total, SUM(CASE WHEN content IS NULL OR length(trim(content)) = 0 THEN 1 ELSE 0 END) AS blank_content, SUM(CASE WHEN content IS NOT NULL AND length(trim(content)) > 0 THEN 1 ELSE 0 END) AS nonblank_content FROM posts GROUP BY language ORDER BY language")]}
    missing_url = malformed = channel_mismatch = message_mismatch = valid_url = 0
    for row in conn.execute('SELECT channel_username, message_id, message_url FROM raw_posts'):
        url = (row['message_url'] or '').strip()
        if not url:
            missing_url += 1; continue
        match = URL_RE.match(url)
        if not match:
            malformed += 1; continue
        valid_url += 1
        url_channel, url_message = match.groups()
        channel_mismatch += int(url_channel.lower() != str(row['channel_username']).lstrip('@').lower())
        message_mismatch += int(str(row['message_id']) != url_message)
    result['url_coverage'] = {'raw_message_url_present': raw_total - missing_url, 'raw_message_url_present_pct': pct(raw_total - missing_url, raw_total), 'raw_message_url_missing': missing_url, 'raw_message_url_valid_tme_pattern': valid_url, 'raw_message_url_malformed': malformed, 'raw_message_url_channel_mismatch': channel_mismatch, 'raw_message_url_message_id_mismatch': message_mismatch, 'posts_missing_source_url_via_raw': one(conn, "SELECT COUNT(*) FROM posts p JOIN raw_posts r ON r.id = p.raw_post_id WHERE r.message_url IS NULL OR length(trim(r.message_url)) = 0"), 'posts_with_extracted_urls': one(conn, 'SELECT COUNT(*) FROM posts WHERE url_count > 0'), 'posts_without_extracted_urls': one(conn, 'SELECT COUNT(*) FROM posts WHERE url_count = 0'), 'posts_url_count_sum': one(conn, 'SELECT COALESCE(SUM(url_count), 0) FROM posts')}
    hash_channels, hash_counts, hashable = defaultdict(set), Counter(), 0
    for row in conn.execute('SELECT p.channel_username, p.content FROM posts p'):
        normalized = WS_RE.sub(' ', (row['content'] or '').strip()).lower()
        if not normalized: continue
        digest = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
        hashable += 1; hash_counts[digest] += 1; hash_channels[digest].add(row['channel_username'])
    duplicate_groups = [count for count in hash_counts.values() if count > 1]
    result['duplicates_and_reposts'] = {'stored_content_hash_column': 'absent', 'ephemeral_hashable_posts': hashable, 'unique_ephemeral_content_hashes': len(hash_counts), 'exact_duplicate_groups': len(duplicate_groups), 'exact_duplicate_rows': sum(duplicate_groups), 'exact_duplicate_rows_pct': pct(sum(duplicate_groups), post_total), 'exact_duplicate_excess_rows': sum(count - 1 for count in duplicate_groups), 'exact_duplicate_excess_rows_pct': pct(sum(count - 1 for count in duplicate_groups), post_total), 'largest_exact_duplicate_group': max(duplicate_groups) if duplicate_groups else 0, 'cross_channel_exact_duplicate_groups': sum(1 for digest, chans in hash_channels.items() if len(chans) > 1 and hash_counts[digest] > 1), 'raw_forward_from_nonempty': one(conn, "SELECT COUNT(*) FROM raw_posts WHERE forward_from IS NOT NULL AND length(trim(forward_from)) > 0")}
    result['reaction_and_feedback_coverage'] = {'signal_feedback_rows': one(conn, 'SELECT COUNT(*) FROM signal_feedback'), 'signal_feedback_distinct_posts': one(conn, 'SELECT COUNT(DISTINCT post_id) FROM signal_feedback'), 'signal_feedback_unmatched_posts': one(conn, 'SELECT COUNT(*) FROM signal_feedback sf LEFT JOIN posts p ON p.id = sf.post_id WHERE p.id IS NULL'), 'user_post_tag_rows': one(conn, 'SELECT COUNT(*) FROM user_post_tags'), 'user_post_tag_distinct_posts': one(conn, 'SELECT COUNT(DISTINCT post_id) FROM user_post_tags'), 'user_post_tag_unmatched_posts': one(conn, 'SELECT COUNT(*) FROM user_post_tags t LEFT JOIN posts p ON p.id = t.post_id WHERE p.id IS NULL'), 'user_post_tag_notes_nonempty': one(conn, "SELECT COUNT(*) FROM user_post_tags WHERE note IS NOT NULL AND length(trim(note)) > 0"), 'reaction_sync_state_rows': one(conn, 'SELECT COUNT(*) FROM reaction_sync_state'), 'reaction_sync_state_distinct_message_refs': one(conn, 'SELECT COUNT(*) FROM (SELECT DISTINCT channel_username, message_id FROM reaction_sync_state)'), 'reaction_sync_state_matched_raw_posts': one(conn, 'SELECT COUNT(*) FROM reaction_sync_state rss JOIN raw_posts r ON r.channel_username = rss.channel_username AND r.message_id = rss.message_id'), 'reaction_sync_state_matched_posts': one(conn, 'SELECT COUNT(*) FROM reaction_sync_state rss JOIN raw_posts r ON r.channel_username = rss.channel_username AND r.message_id = rss.message_id JOIN posts p ON p.raw_post_id = r.id'), 'reaction_sync_state_unmatched_raw_posts': one(conn, 'SELECT COUNT(*) FROM reaction_sync_state rss LEFT JOIN raw_posts r ON r.channel_username = rss.channel_username AND r.message_id = rss.message_id WHERE r.id IS NULL')}
finally:
    conn.close()
print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
PY
```

Result:

```json
{
  "channel_coverage": {
    "configured_channels_missing_raw_posts": 0,
    "configured_channels_with_raw_posts": 21,
    "db_distinct_raw_channels": 21,
    "per_configured_channel_counts": [
      {"channel": "@gleb_pro_ai", "fts_rows": 180, "posts": 180, "raw_posts": 180},
      {"channel": "@tired_glebmikheev", "fts_rows": 167, "posts": 167, "raw_posts": 167},
      {"channel": "@ai_newz", "fts_rows": 154, "posts": 154, "raw_posts": 154},
      {"channel": "@neuraldeep", "fts_rows": 181, "posts": 181, "raw_posts": 181},
      {"channel": "@cryptoEssay", "fts_rows": 153, "posts": 153, "raw_posts": 153},
      {"channel": "@llm_under_hood", "fts_rows": 118, "posts": 118, "raw_posts": 118},
      {"channel": "@silent_ai_cto", "fts_rows": 38, "posts": 38, "raw_posts": 38},
      {"channel": "@its_capitan", "fts_rows": 60, "posts": 60, "raw_posts": 60},
      {"channel": "@log_OS_ru", "fts_rows": 37, "posts": 37, "raw_posts": 37},
      {"channel": "@data_secrets", "fts_rows": 613, "posts": 613, "raw_posts": 613},
      {"channel": "@leadgr", "fts_rows": 114, "posts": 114, "raw_posts": 114},
      {"channel": "@leadgenvalley", "fts_rows": 89, "posts": 89, "raw_posts": 89},
      {"channel": "@Redmadnews", "fts_rows": 138, "posts": 138, "raw_posts": 138},
      {"channel": "@doronin_aiforfriends", "fts_rows": 23, "posts": 23, "raw_posts": 23},
      {"channel": "@max_about_ai", "fts_rows": 7, "posts": 7, "raw_posts": 7},
      {"channel": "@oestick", "fts_rows": 50, "posts": 50, "raw_posts": 50},
      {"channel": "@codecamp", "fts_rows": 817, "posts": 817, "raw_posts": 817},
      {"channel": "@NeuralShit", "fts_rows": 242, "posts": 242, "raw_posts": 242},
      {"channel": "@kyrillic", "fts_rows": 206, "posts": 206, "raw_posts": 206},
      {"channel": "@exitsexist", "fts_rows": 81, "posts": 81, "raw_posts": 81},
      {"channel": "@huntermikevolkov", "fts_rows": 9, "posts": 9, "raw_posts": 9}
    ],
    "unconfigured_raw_channel_count": 0
  },
  "configured_channels": {
    "active": 21,
    "group_counts": {"market_business_ai": 5, "none": 16},
    "inactive": 0,
    "language_counts": {"ru": 21},
    "priority_counts": {"high": 8, "low": 5, "medium": 8},
    "total": 21
  },
  "database": "data/agent.db",
  "date_coverage": {
    "posts_future_dates_after_2026_07_26": 0,
    "posts_invalid_dates": 0,
    "posts_max_date": "2026-07-20",
    "posts_min_date": "2026-03-30",
    "posts_unique_dates": 113,
    "raw_future_dates_after_2026_07_26": 0,
    "raw_invalid_dates": 0,
    "raw_max_date": "2026-07-20",
    "raw_min_date": "2026-03-30",
    "raw_unique_dates": 113
  },
  "duplicates_and_reposts": {
    "cross_channel_exact_duplicate_groups": 15,
    "ephemeral_hashable_posts": 3033,
    "exact_duplicate_excess_rows": 26,
    "exact_duplicate_excess_rows_pct": 0.75,
    "exact_duplicate_groups": 19,
    "exact_duplicate_rows": 45,
    "exact_duplicate_rows_pct": 1.29,
    "largest_exact_duplicate_group": 5,
    "raw_forward_from_nonempty": 283,
    "stored_content_hash_column": "absent",
    "unique_ephemeral_content_hashes": 3007
  },
  "inspection_date": "2026-07-26",
  "language_coverage": {
    "by_language_blank_content": [
      {"blank_content": 0, "language": "en", "nonblank_content": 24, "total": 24},
      {"blank_content": 0, "language": "ru", "nonblank_content": 3004, "total": 3004},
      {"blank_content": 444, "language": "unknown", "nonblank_content": 5, "total": 449}
    ],
    "configured_non_ru_channels": 0,
    "posts_language_detected_counts": {"en": 24, "ru": 3004, "unknown": 449},
    "posts_missing_language_detected": 0
  },
  "metadata_readiness": {
    "posts_duplicate_raw_post_refs": 0,
    "posts_missing_channel_username": 0,
    "posts_missing_normalized_at": 0,
    "posts_missing_posted_at": 0,
    "raw_duplicate_channel_message_pairs": 0,
    "raw_json_blank": 3091,
    "raw_json_nonempty": 386,
    "raw_json_null": 0,
    "raw_missing_channel_id": 0,
    "raw_missing_channel_username": 0,
    "raw_missing_message_id": 0,
    "raw_missing_posted_at": 0
  },
  "open_mode": "sqlite-uri-mode-ro",
  "reaction_and_feedback_coverage": {
    "reaction_sync_state_distinct_message_refs": 23,
    "reaction_sync_state_matched_posts": 23,
    "reaction_sync_state_matched_raw_posts": 23,
    "reaction_sync_state_rows": 23,
    "reaction_sync_state_unmatched_raw_posts": 0,
    "signal_feedback_distinct_posts": 23,
    "signal_feedback_rows": 23,
    "signal_feedback_unmatched_posts": 0,
    "user_post_tag_distinct_posts": 23,
    "user_post_tag_notes_nonempty": 23,
    "user_post_tag_rows": 23,
    "user_post_tag_unmatched_posts": 0
  },
  "table_counts": {
    "idea_threads": 1290,
    "knowledge_atoms": 1346,
    "posts": 3477,
    "posts_fts": 3477,
    "raw_posts": 3477,
    "reaction_sync_state": 23,
    "signal_feedback": 23,
    "user_post_tags": 23
  },
  "text_and_indexability": {
    "blank_posts_with_any_raw_text_source": 0,
    "blank_posts_with_no_raw_text_source": 444,
    "fts_rows": 3477,
    "fts_rows_pct_of_posts": 100.0,
    "fts_rows_without_post": 0,
    "posts_content_blank_or_null": 444,
    "posts_content_nonempty": 3033,
    "posts_content_nonempty_pct": 87.23,
    "posts_missing_fts_row": 0,
    "posts_without_raw": 0,
    "posts_word_count_zero_or_negative": 444,
    "raw_caption_nonempty": 2192,
    "raw_caption_nonempty_pct": 63.04,
    "raw_image_description_nonempty": 243,
    "raw_image_description_nonempty_pct": 6.99,
    "raw_text_nonempty": 2793,
    "raw_text_nonempty_pct": 80.33,
    "raw_without_normalized_post": 0
  },
  "url_coverage": {
    "posts_missing_source_url_via_raw": 0,
    "posts_url_count_sum": 366,
    "posts_with_extracted_urls": 308,
    "posts_without_extracted_urls": 3169,
    "raw_message_url_channel_mismatch": 0,
    "raw_message_url_malformed": 0,
    "raw_message_url_message_id_mismatch": 0,
    "raw_message_url_missing": 0,
    "raw_message_url_present": 3477,
    "raw_message_url_present_pct": 100.0,
    "raw_message_url_valid_tme_pattern": 3477
  }
}
```

The command printed no post bodies, captions, raw JSON, tag notes, feedback
labels, reaction emoji, or generated report text.

PRM-5 reaction fast-lane read-only inspection command:

```bash
PYTHONPATH=src python3 - <<'PY'
import json
import sqlite3
from db.reaction_fast_lane import build_reaction_fast_lane_receipt, validate_reaction_fast_lane_receipt
conn = sqlite3.connect('file:data/agent.db?mode=ro', uri=True)
try:
    receipt = validate_reaction_fast_lane_receipt(build_reaction_fast_lane_receipt(conn))
    print(json.dumps({
        'schema_version': receipt['schema_version'],
        'counts': receipt['counts'],
        'stage_statuses': receipt['stage_statuses'],
        'search_availability': receipt['search_availability'],
        'incomplete_stage_reasons': receipt['incomplete_stage_reasons'],
        'privacy': receipt['privacy'],
    }, ensure_ascii=True, sort_keys=True, indent=2))
finally:
    conn.close()
PY
```

Result:

```json
{
  "counts": {
    "archive_documents_excluded": 1,
    "archive_documents_indexed": 26,
    "archive_posts_indexed": 22,
    "enrichment_attempts": 22,
    "enrichment_failures": 19,
    "enrichment_successes": 3,
    "indexed_documents": 26,
    "personal_reaction_events_detected": 23,
    "post_level_interest_signals": 22,
    "posts_resolved": 23,
    "ranking_effects": 0,
    "searchable_archive_documents": 26,
    "searchable_archive_posts": 22,
    "topic_link_attempts": 22,
    "topic_link_failures": 0,
    "topic_link_successes": 22,
    "topic_links": 22,
    "unique_atoms_linked": 3,
    "unique_reacted_posts": 23
  },
  "incomplete_stage_reasons": {
    "empty_canonical_body": 1,
    "knowledge_atom_not_extracted": 19,
    "ranking_not_evaluated": 22
  },
  "privacy": {
    "emoji_values_included": false,
    "raw_text_included": false,
    "source_urls_included": false
  },
  "schema_version": "reaction_fast_lane.v1",
  "search_availability": {
    "assistant_archive_search_available": true,
    "backend": "sqlite_fts",
    "requires_knowledge_atoms": false
  },
  "stage_statuses": {
    "archive_index": "partial",
    "assistant_search": "partial",
    "enrichment": "partial",
    "ranking": "not_evaluated",
    "reaction_detection": "complete",
    "source_resolution": "complete",
    "topic_linkage": "complete"
  }
}
```

The command printed no post bodies, captions, raw JSON, tag notes, feedback
labels, reaction emoji values, source URLs, or generated report text.

Candidate query inspection command:

```bash
python3 - <<'PY'
import json
from collections import Counter
from pathlib import Path
path = Path('evals/retrieval/query_set_candidate.jsonl')
rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
print(f'file={path}')
print(f'row_count={len(rows)}')
print('human_approved_counts=' + json.dumps(dict(sorted(Counter(row.get('human_approved') for row in rows).items(), key=lambda item: str(item[0])))))
print('validation_status_counts=' + json.dumps(dict(sorted(Counter(row.get('validation_status') for row in rows).items()))))
print('expected_evidence_status_counts=' + json.dumps(dict(sorted(Counter(row.get('expected_evidence_status') for row in rows).items()))))
print('category_counts=' + json.dumps(dict(sorted(Counter(row.get('category') for row in rows).items()))))
print(f'rows_with_expected_post_ids={sum(1 for row in rows if row.get("expected_post_ids"))}')
print(f'rows_with_expected_source_urls={sum(1 for row in rows if row.get("expected_source_urls"))}')
print(f'rows_with_copied_evidence_text_keys={sum(1 for row in rows if any(key in row for key in ("expected_text", "post_text", "raw_text", "evidence_quote", "full_text")))}')
PY
```

Result:

```text
file=evals/retrieval/query_set_candidate.jsonl
row_count=50
human_approved_counts={"false": 50}
validation_status_counts={"candidate_unapproved": 50}
expected_evidence_status_counts={"expected_insufficient_evidence_external_verification_required": 1, "expected_insufficient_evidence_requires_human_label": 2, "likely_insufficient_evidence_requires_human_label": 1, "likely_irrelevant_requires_human_label": 3, "must_not_answer_as_financial_advice_requires_human_label": 1, "requires_human_label": 42}
category_counts={"case_study": 8, "comparison": 6, "distractor": 4, "exact_known_item": 8, "freshness_news": 6, "no_answer": 4, "project_life_application": 6, "semantic_topic": 8}
rows_with_expected_post_ids=0
rows_with_expected_source_urls=0
rows_with_copied_evidence_text_keys=0
```
