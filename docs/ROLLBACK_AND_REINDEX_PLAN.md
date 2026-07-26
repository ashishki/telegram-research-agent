# Rollback And Reindex Plan

Status: draft

## Archive Search

The canonical archive is SQLite `raw_posts` and `posts`. FTS/search indexes are
rebuildable derived state.

Rollback requirements before PRM-3:

- record index schema version;
- record source table counts;
- expose index freshness;
- provide rebuild command;
- provide integrity check;
- keep backup of SQLite file before migrations.

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
