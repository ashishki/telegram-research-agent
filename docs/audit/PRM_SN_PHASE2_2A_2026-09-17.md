# PRM-SN-2A implementation checkpoint — 2026-09-17

Implemented typed volatile follow-up routing only; this is not DR-2 or a runtime/pilot claim. The context remains process-local, bounded and expires after 20 minutes; no durable memory is created by ordinary follow-ups.

- A new explicit archive topic remains a fresh query, so a subsequent short follow-up is composed from topic B rather than stale topic A.
- Follow-up requests for `за прошлую неделю` retain the active topic and the archive planner resolves the phrase as the completed UTC Monday–Sunday window. It is therefore a strict actual retrieval filter, not display text.
- The DST fixture fixes 2026-03-30 to `2026-03-23T00:00:00Z` through `2026-03-30T00:00:00Z`.

Verification: focused volatile-dialogue and archive-research tests pass: `40 passed in 5.05s`; `git diff --check` passes.

Remaining phase work: exact selected-item confirmation semantics (2B), read-only refresh/index health projection (2C), immediate review of altered confirmation/write semantics, then DR-2. No production database, Telegram send, refresh, migration, egress or service action was run.
