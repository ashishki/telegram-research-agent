# Reaction Sync Runbook

Status: proposed PRM-MAT runbook. Do not run or schedule reaction sync from this document.

Reaction sync is a separate failure domain from archive refresh. It resolves only personal reactions, proves retained-archive/FTS searchability, records emoji as audit metadata, applies at most a temporary weak boost, then queues selective enrichment and a confirmation-gated preference proposal. Absence is unknown; failed sync never rolls back a successful archive refresh.

Before any live routine: exact operator approval for credentials, schedule, timezone, rate limits, retention and receipts; read-only/preflight validation; backup-aware plan; bounded retry; and owner-visible outcome. The receipt reports detected/resolved/searchable/enrichment counts and independent failure, never raw post text. On failure retain archive state, emit a safe failure receipt, and inspect credentials/API visibility without retry storm.
