# Manual PRM runtime migration and restart — 2026-08-14

Operator explicitly approved production migration, provider-enabled manual
runtime, and controlled restart; PRM-19 dogfood remains excluded.

- Preflight integrity check: `ok`.
- A local pre-migration SQLite backup was created outside git; SHA-256:
  `9a60a21e90011e4871d42f4428389aa67a78cbeeb4e2a4b1b4112425e005964b`.
- Canonical migration completed; `personal_memory_events`,
  `prm_interaction_ledger`, and `prm_post_answer_proposals` are present and
  post-migration integrity check is `ok`.
- `telegram-prm-assistant.service` was restarted and is active. Its prior poll
  cycle received SIGTERM, stopped cleanly, and the new unit instance started.

No dogfood was started or claimed. No private Telegram content, secret, source
payload, or backup file was committed. A pre-restart polling timeout remains an
external Telegram transport observation, not a migration failure.
