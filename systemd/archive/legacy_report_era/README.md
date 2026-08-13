# Legacy Report-Era systemd Templates

These templates are preserved for compatibility history only:

- `telegram-ai-split-report.service`
- `telegram-ai-split-report.timer`
- `telegram-bot.service`
- `telegram-cleanup.service` and `telegram-cleanup.timer`
- `telegram-digest.service` and `telegram-digest.timer`
- `telegram-ingest.service` and `telegram-ingest.timer`
- `telegram-mvp-weekly.service` and `telegram-mvp-weekly.timer`
- `telegram-reminders.service` and `telegram-reminders.timer`
- `telegram-study-reminder.service` and `telegram-study-reminder.timer`

They run legacy ingestion and weekly report delivery. Do not install, enable,
or start them as part of the active PRM workflow. The active repo template is
`systemd/telegram-prm-assistant.service`; archive refresh has its separately
approved bounded templates.
