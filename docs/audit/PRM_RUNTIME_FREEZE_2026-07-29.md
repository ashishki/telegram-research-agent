# PRM Runtime Freeze - 2026-07-29

Status: runtime evidence
Scope: freeze legacy runtime before PRM dogfood planning

## Action

The operator approved freezing the old runtime after PRM-18 showed dogfood was
blocked. Runtime changes were limited to stopping/disabling systemd entrypoints.
No production database contents were modified. No compatibility files were
deleted, archived, or moved.

Commands executed:

```text
systemctl stop telegram-ai-split-report.timer
systemctl disable telegram-ai-split-report.timer
systemctl reset-failed telegram-ai-split-report.service
systemctl stop telegram-bot.service
systemctl disable telegram-bot.service
```

## Result

`telegram-ai-split-report.timer`:

```text
Loaded: loaded (/etc/systemd/system/telegram-ai-split-report.timer; disabled; vendor preset: enabled)
Active: inactive (dead)
Trigger: n/a
```

`telegram-ai-split-report.service`:

```text
Loaded: loaded (/etc/systemd/system/telegram-ai-split-report.service; disabled; vendor preset: enabled)
Active: inactive (dead)
```

`telegram-bot.service`:

```text
Loaded: loaded (/etc/systemd/system/telegram-bot.service; disabled; vendor preset: enabled)
Active: inactive (dead)
```

Post-freeze checks:

```text
systemctl list-units --type=service --state=running --no-pager | rg -i 'telegram-research-agent|telegram-bot|telegram-ai-split-report|telegram-(ingest|digest|mvp|cleanup|reminders|study)' || true
<no output>
```

```text
systemctl list-timers --all --no-pager | rg -i 'telegram-research-agent|telegram-bot|telegram-ai-split-report|telegram-(ingest|digest|mvp|cleanup|reminders|study)' || true
<no output>
```

```text
systemctl list-unit-files --no-pager | rg '^telegram-(bot|ai-split-report|ingest|digest|mvp-weekly|cleanup|study-reminder|reminders)\.(service|timer)' || true
telegram-ai-split-report.service       disabled        enabled
telegram-bot.service                   disabled        enabled
telegram-cleanup.service               disabled        enabled
telegram-digest.service                disabled        enabled
telegram-ingest.service                disabled        enabled
telegram-mvp-weekly.service            disabled        enabled
telegram-reminders.service             disabled        enabled
telegram-study-reminder.service        disabled        enabled
telegram-ai-split-report.timer         disabled        enabled
telegram-cleanup.timer                 disabled        enabled
telegram-digest.timer                  disabled        enabled
telegram-ingest.timer                  disabled        enabled
telegram-mvp-weekly.timer              disabled        enabled
telegram-reminders.timer               disabled        enabled
```

Cron checks:

```text
crontab -u oc_you -l
no crontab for oc_you
```

System cron did not contain Telegram Research Agent jobs.

## Historical Runtime Footprints

The old report timer previously ran on 2026-07-27 and produced a W30 partial
weekly intelligence package under:

```text
data/output/weekly_intelligence_runs/tra-weekly-2026-W30-20260727T050201109582Z-4803fa25204b/
```

Observed artifact categories by filename only:

- `weekly_brief/`
- `knowledge_atlas/`
- `radar/`
- `reaction_sync/`
- `manifest.json`

Those generated artifacts remain private historical outputs and were not read
for content, committed, deleted, moved, or promoted to PRM dogfood evidence.

## Boundary Evidence

- No live Telegram ingestion was started.
- No reaction sync was started.
- No LLM extraction, LLM judge, Frontier, Radar, report generation, full archive
  indexing, embeddings, external web research, or external skill execution was
  started.
- No production DB migration was run.
- No generated private reports were committed.
- No compatibility files were deleted, archived, or moved.
- PRM-19 remains blocked until explicit dogfood-start approval and accepted or
  cleared PRM-18 blockers.
