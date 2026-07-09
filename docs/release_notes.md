# Release Notes

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
