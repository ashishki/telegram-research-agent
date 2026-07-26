# Rollback And Reindex Plan

Status: draft; PRM-2 archive document rollback recorded
Last updated: 2026-07-26

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

## Vector/Hybrid Future

If PRM-7 approves vector/hybrid retrieval:

- keep SQLite archive canonical;
- record embedding provider/model/version;
- record corpus/index version;
- keep rebuild script;
- support disabling vector path and falling back to FTS;
- document backup/restore before dogfood.

## Report/Library Projections

Weekly Brief and Knowledge Library pages are derived. Regenerate or discard
them without changing canonical archive records.
