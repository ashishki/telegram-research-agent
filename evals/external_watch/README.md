# External-watch eval inventory

The manifest is a public, sanitized P0 inventory, not an evidence set for a
running collector. Every row starts pending until a human reviews a real,
sanitized UTD fixture and adds its expected `notify`, `ignore`, or `ambiguous`
outcome. The 15 blind rows must not be used to tune a later policy.

Do not put raw UTD payloads, personal data, cookies, tokens, inbox content, or
private Telegram data here. Store only minimized sanitized fixtures under
`tests/fixtures/external_watch/` once they have been reviewed.
