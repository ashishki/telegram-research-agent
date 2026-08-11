# Rollback And Reindex Plan

Status: draft; PRM-2 archive document rollback recorded; PRM-15 learning-state migration rollback recorded; PRM-17 workflow rollback/dry-run contract recorded; PRM-26 vector gate rollback recorded; PRM-27 local vector sidecar rollback recorded
Last updated: 2026-08-11

## Archive Search

The canonical archive is SQLite `raw_posts` and `posts`. FTS/search indexes are
rebuildable derived state.

PRM-2 adds a deterministic archive document identity contract without a
production database migration. The mapper in `src/db/archive_documents.py`
derives document IDs, content hashes, chunk IDs, duplicate cluster IDs, and
repost cluster candidates from canonical rows in memory.

Archive document contract version:

| Field | Value |
| --- | --- |
| Contract version | `archive-document-contract.v1` |
| Post identity | `tg:{channel_id}:{message_id}` |
| Chunk identity | `tg:{channel_id}:{message_id}:chunk:{zero_padded_chunk_index}` |
| Hash algorithm | `sha256:v1:ws-casefold` |
| Default chunk threshold | 3,200 characters |
| Canonical body | non-empty `posts.content` |
| Citation | `raw_posts.message_url` |

Rollback requirements before PRM-3:

- record index schema version;
- record source table counts;
- expose index freshness;
- provide rebuild command;
- provide integrity check;
- keep backup of SQLite file before migrations.

PRM-2 rollback rules:

- Do not delete, archive, or mutate `raw_posts` or `posts` to roll back derived
  search behavior.
- If archive document mapping is wrong before any persisted index adoption,
  rollback is a code/doc revert plus rerunning deterministic tests.
- If a future FTS/archive index has been built from this contract, rollback
  restores the previous derived index version from backup or rebuilds the
  derived index from canonical rows.
- Production rebuild, schema migration, or index replacement requires explicit
  human approval before execution.
- Any rollback receipt must record source table counts before and after the
  operation and must not print raw Telegram text.

Current FTS integrity checks are aggregate-only:

```sql
SELECT COUNT(*) FROM raw_posts;
SELECT COUNT(*) FROM posts;
SELECT COUNT(*) FROM posts_fts;
SELECT COUNT(*)
FROM posts p
LEFT JOIN posts_fts f ON f.rowid = p.id
WHERE f.rowid IS NULL;
SELECT COUNT(*)
FROM posts_fts f
LEFT JOIN posts p ON p.id = f.rowid
WHERE p.id IS NULL;
```

Current SQLite FTS rebuild command, for approved maintenance windows only:

```sql
INSERT INTO posts_fts(posts_fts) VALUES('rebuild');
```

This rebuild command mutates derived FTS state and must not be run against
production data from PRM-2 without explicit authorization.

Future archive-document index rollback procedure:

1. Stop scheduled jobs that could mutate ingestion, reaction sync, enrichment,
   report generation, or index state.
2. Back up the SQLite database file and record file hash and source table
   counts.
3. Record current index contract version, index row count, and freshness.
4. Disable the derived archive index path or select the previous index version.
5. Rebuild only derived index rows from `raw_posts` and `posts`, preserving
   canonical source rows.
6. Run aggregate integrity checks and a privacy review of receipts/logs.
7. Re-enable only the read path that passed verification.

## Enrichment

Enrichment writes must be additive and traceable:

- batch ID;
- source post IDs;
- model/prompt version;
- cost;
- success/failure reason;
- generated object IDs.

Failed enrichment does not remove archive search documents.

## PRM-27 Local Vector Sidecar

ADR-004 approves only a derived local SQLite sidecar. Canonical `raw_posts`,
`posts`, and `posts_fts` remain authoritative and are not mutated by the
sidecar indexer.

Reindex:

```bash
python3 src/main.py memory vector-index --json
```

Hybrid search smoke:

```bash
PRM_ARCHIVE_HYBRID_RETRIEVAL=approved \
python3 src/main.py memory research --hybrid "что из моих постов про AI transformation ROI?"
```

Rollback to FTS-only behavior:

```bash
unset PRM_ARCHIVE_HYBRID_RETRIEVAL
rm -f data/vector/archive_vector.sqlite
```

Rollback requirements:

1. Preserve canonical `raw_posts`, `posts`, and `posts_fts`.
2. Version every sidecar schema and local vectorization model.
3. Keep `PRM_ARCHIVE_HYBRID_RETRIEVAL` as the feature flag that disables vector
   retrieval and falls back to SQLite FTS.
4. Keep `data/vector/` gitignored.
5. Before long-running production rebuilds, snapshot or back up the canonical
   SQLite database plus sidecar path for operator evidence.
6. Verify aggregate row counts and eval metrics after rollback without printing
   raw Telegram text.

External embedding providers, hosted vector services, and production migrations
remain outside ADR-004 and require a separate approval.

## Report/Library Projections

Weekly Brief and Knowledge Library pages are derived. Regenerate or discard
them without changing canonical archive records.

PRM-16 and PRM-17 add explicit projection/runtime rollback rules:

- Weekly Brief V3 artifacts are derived from bounded supplied context and may be
  discarded or regenerated without changing archive or memory rows.
- Knowledge Library topic pages are derived and may be discarded or regenerated
  without changing confirmed memory events or archive rows.
- A failed Radar, Brief, or Library projection must degrade only that surface or
  card when archive search and assistant receipts remain valid.

## Runtime Workflow Rollback And Dry-Run Validation

PRM-17 defines workflow rollback contracts in
`src/processing/workflow_telemetry.py` and
`docs/AUTONOMOUS_WORKFLOW_CONTRACT.md`. Runtime activation remains unapproved.

Rollback/reindex safety rules:

1. Stop scheduled jobs before any approved maintenance that can mutate
   ingestion, reaction sync, enrichment, report generation, or index state.
2. Take and verify a `backup_snapshot` receipt before any production migration,
   reindex, or rollback.
3. Run `rollback_reindex_dry_run` first and record only aggregate counts,
   checksum refs, error class, and approval requirement.
4. Preserve canonical `raw_posts`, `posts`, confirmed memory events, reactions,
   and feedback rows.
5. Rebuild only derived FTS/projection state from canonical rows.
6. Record index freshness, queue age, retrieval/generation latency, cost,
   no-answer rate, and error class without raw post text.
7. Stop immediately for human review if dry-run counts diverge, backup
   verification fails, or a production write would be required.

Fixture validation command:

```bash
PYTHONPATH=src python3 -m pytest tests/test_workflow_telemetry.py -q
```

Dry-run aggregate checks for approved maintenance windows only:

```sql
SELECT COUNT(*) FROM raw_posts;
SELECT COUNT(*) FROM posts;
SELECT COUNT(*) FROM posts_fts;
SELECT COUNT(*)
FROM posts p
LEFT JOIN posts_fts f ON f.rowid = p.id
WHERE f.rowid IS NULL;
```

The SQL above reads or rebuilds derived state only when explicitly approved for
the current maintenance task. It must not be run as a production mutation from a
planning or fixture-only PRM task.

## Learning-State Migration

PRM-15 corrects learning-state semantics in code and fixture tests only. No
production database migration was executed.

Canonical PRM-15 states:

- `indexed`
- `surfaced`
- `opened`
- `read`
- `understood`
- `explained`
- `tried`
- `applied`
- `measured`
- `rejected`
- `stale`

Migration rule:

- legacy source URL or atom presence maps only to `indexed` or `surfaced`;
- `opened`, `read`, `understood`, `explained`, `tried`, `applied`, and
  `measured` require explicit feedback, progress receipts, outcome evidence, or
  measured/test evidence;
- no feedback is displayed as `unknown`, not negative and not completion;
- legacy `reproduced`, `implemented`, `tested`, and `project-applied` aliases
  are normalized to `tried`, `applied`, `measured`, and `applied` only when
  explicit evidence exists.

Fixture validation command:

```bash
PYTHONPATH=src python3 -m pytest tests/test_learning_layer.py tests/test_ai_report_contract.py tests/test_intelligence_retrieval_items.py tests/test_split_intelligence_reports.py tests/test_dogfood_review.py -q
```

Rollback:

1. Do not rewrite or delete existing learning, feedback, archive, atom, or
   report rows to roll back PRM-15 behavior.
2. Revert the code projection/migration helper if labels are wrong.
3. If a future approved production migration writes canonical learning-state
   rows, take a SQLite backup first, record aggregate row counts by state before
   and after, and preserve the original legacy state in an audit column.
4. Rollback from a future persisted migration must restore the previous backup
   or append compensating audit rows; it must not infer read/applied/measured
   states from source presence.
