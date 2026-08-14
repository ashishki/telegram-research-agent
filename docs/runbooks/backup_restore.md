# Backup and Restore Runbook

Status: proposed PRM-MAT runbook. This plan does not execute backup, restore or migration.

Before an approved persistent proposal, interaction-ledger or configuration migration: capture a local backup identifier/checksum, validate it without exposing private data, define rollback owner/window, and record current schema/config versions. Backups, keys and exports use permission-hardened local storage and are excluded from commits/logs.

Restore rehearsal uses an isolated copy, verifies schema/integrity plus a bounded read-only search and proposal-history query, then records result/checksum/restore duration. A failed restore blocks the corresponding migration/schedule change. Rollback restores the pre-change configuration/data copy; it never silently deletes canonical archive, saved knowledge, or private evidence. Data export/delete requests need an explicit retention-policy procedure and operator confirmation.
