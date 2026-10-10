# Backup and Restore Runbook

## Current durable PA boundary — 10 October2026

The runtime now has local selected-domain backup/restore/export/import and monotone unknown/consumed fences; tests use an identified SyntheticTarget. See [current architecture](../ARCHITECTURE.md) and [cutover package](../verification/PAI-28-cutover-packet.md). Historical SQLite/service recipes below are not a production PostgreSQL command or authorization. No real host/snapshot/production RPO/RTO observed in the current work.

Status: proposed PRM-MAT runbook. This plan does not execute backup, restore or migration.

Before an approved persistent proposal, interaction-ledger or configuration migration: capture a local backup identifier/checksum, validate it without exposing private data, define rollback owner/window, and record current schema/config versions. Backups, keys and exports use permission-hardened local storage and are excluded from commits/logs.

Restore rehearsal uses an isolated copy, verifies schema/integrity plus a bounded read-only search and proposal-history query, then records result/checksum/restore duration. A failed restore blocks the corresponding migration/schedule change. Rollback restores the pre-change configuration/data copy; it never silently deletes canonical archive, saved knowledge, or private evidence. Data export/delete requests need an explicit retention-policy procedure and operator confirmation.

## Rehearsal checklist

1. Operator approves the isolated temporary-copy target and retention window.
2. Record only a local backup identifier, SHA-256 checksum, schema version and
   timestamp; never commit the copy, checksum path, keys, or private contents.
3. Restore only into the isolated copy, run integrity check plus bounded
   read-only search and proposal-history query, and record pass/fail/duration.
4. Record an explicit rollback decision: `keep_isolated_copy`,
   `restore_prechange_copy`, or `blocked_for_operator`; production restore is
   never automatic.

No rehearsal has been run by this documentation change.
