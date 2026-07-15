# Release Notes

## 2026-07-15

### Report V2 Implementation Queue Closed

- IRX-1 through IRX-14 are implemented and verified as additive Report V2
  corrections: completed-period semantics, same-run manifests/Radar binding,
  reaction receipts, canonical thread lifecycle, editorial intelligence,
  shared visuals, Project Intelligence V2, Radar reader hardening, Brief V2,
  reader-value gates, Atlas V2, report-specific feedback, regression fixtures,
  and rollout receipts.
- `weekly-intelligence-v2` is the explicit additive Report V2 package command.
  It preserves V1 compatibility artifacts while producing manifest-bound V2
  outputs.
- `report-v2-rollout-gate` is the read-only dogfood start gate. It exits `0`
  only when a real current private weekly package is eligible and exits `2`
  with blocking evidence when dogfood must remain paused.
- `telegram-ai-split-report.service` now runs
  `weekly-intelligence-v2 --deliver --threads-limit 24 --atoms-limit 8`; the
  timer runs Monday at 09:00 Asia/Tbilisi.
- The weekly service writes a non-blocking post-run rollout receipt to
  `data/output/report_v2_rollout_receipts/latest.json`.
- The timer no longer uses catch-up activation on restart; reports should run
  at the scheduled 09:00 Asia/Tbilisi window rather than immediately after a
  timer restart.
- No dogfood, live operator value, screenshot approval, or portfolio evidence
  is claimed by this release note.

## 2026-07-09

### Weekly Split HTML Delivery

- `ai-split-report --deliver` now sends the Weekly Intelligence Brief and
  Knowledge Atlas HTML files to Telegram as documents after generating both
  sidecars.
- `telegram-ai-split-report.service` and `telegram-ai-split-report.timer` are
  the production weekly report schedule. The timer runs Monday at 09:00
  Europe/Berlin.
- The service refreshes ingestion first, then runs
  `src/main.py ai-split-report --deliver --threads-limit 24 --atoms-limit 8`.
- Reminder and legacy weekly timers are disabled in the current dogfood
  baseline: `reminder.timer`, `telegram-reminders.timer`,
  `telegram-study-reminder-*.timer`, `telegram-ingest.timer`,
  `telegram-digest.timer`, `telegram-mvp-weekly.timer`, and
  `telegram-cleanup.timer`.
- `health-check` now validates the split report timer and current-week
  Weekly Brief / Knowledge Atlas HTML presence after the Monday 09:00
  Europe/Berlin window.

### Radar Validation Surface

- RVE-7 is shipped: Weekly Brief preserves the MVP Radar gate card, validation
  query pack, matched evidence, missing evidence checklist, context-only market
  labels, and the exact next validation action.
