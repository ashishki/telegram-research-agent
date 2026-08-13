# Legacy And Compatibility Surfaces

Status: compatibility history
Last updated: 2026-08-12

The active product is Personal Telegram Research Memory + Grounded Assistant.
The following surfaces are retained for history or compatibility and are not
daily operator entrypoints: Report V2, Atlas, Radar, Frontier, the legacy
`telegram-bot.service`, and the legacy weekly report timer.

Full report-era architecture, IRX V2 roadmap, contract, and audit content is
preserved in `docs/archive/legacy_report_era/`. The old paths are short
compatibility redirects only.

The historical Hermes PI, Portfolio Grade Intelligence, Report Quality, and
Weekly Radar roadmaps are also preserved in that archive with redirect stubs.

The historical Project Plan, Next Development Roadmap, and Development Cycle
are likewise archive-only with redirect stubs at their former paths.

Legacy weekly split-report systemd templates are preserved in
`systemd/archive/legacy_report_era/`; they are not installable from active
operator runbooks.

All remaining legacy bot, ingest, digest, MVP, cleanup, reminder, and study
systemd templates are preserved in the same archive. The only active repo
templates are `telegram-prm-assistant` and bounded PRM archive refresh.

Do not restart, delete, move, or rename these surfaces as part of PRM-UX.
Any compatibility cleanup requires real operator production-test evidence and
explicit human approval.
