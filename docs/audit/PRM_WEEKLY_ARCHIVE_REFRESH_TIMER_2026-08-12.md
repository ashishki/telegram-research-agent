# PRM Weekly Archive Refresh Timer - 2026-08-12

Status: manual-test freshness timer, not PRM-19 dogfood

## Boundary

The operator asked whether fresh archive runs existed and requested a
once-weekly timer.

The current fresh pass already existed before timer installation:

```text
manual refresh date=2026-08-12
raw_posts/posts/posts_fts: 3709 -> 4166
max posts.posted_at: 2026-08-11T21:47:37+00:00
freshness smoke: last-two-weeks model query found fresh local Telegram citations
```

The scheduled job is limited to the same bounded archive-refresh path. It is
not the legacy `telegram-ingest.timer`, not the legacy weekly report timer, and
not PRM-19 dogfood evidence.

The timer must not run migrations, reaction sync, media download, vision LLM,
provider egress, source-event writes, live web research, external embeddings,
hosted vector service, report generation, release claim, compatibility cleanup,
or dogfood start.

## Implementation

Added:

- `systemd/telegram-prm-archive-refresh.service`
- `systemd/telegram-prm-archive-refresh.timer`

The service command is:

```text
/srv/openclaw-you/venv/bin/python3 src/main.py memory refresh-archive --days 21 --confirm-canonical-write --json
```

The 21-day lookback is intentional for a weekly timer: duplicate posts are
skipped, while one missed run should not create a freshness gap.

The service sets provider-egress Telegram flags to `0` for this unit:

```text
PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=0
PRM_TELEGRAM_AUTO_LLM_ROUTER=0
PRM_TELEGRAM_RAG_LLM_SYNTHESIS=0
```

The timer schedule is:

```text
OnCalendar=Mon *-*-* 08:10:00 Europe/Berlin
AccuracySec=5m
RandomizedDelaySec=15m
Persistent=false
```

`Persistent=false` is deliberate: the archive was already fresh when the timer
was installed, so installation should not immediately catch up and repeat a
canonical DB write.

The timer intentionally does not declare `Requires=` on the service. `Unit=...`
is enough for calendar activation; adding `Requires=` starts the service during
`systemctl enable --now` and defeats the no-install-time-run boundary.

## Runtime installation receipt

Commands:

```text
systemd-analyze verify systemd/telegram-prm-archive-refresh.service systemd/telegram-prm-archive-refresh.timer
install -m 0644 systemd/telegram-prm-archive-refresh.service /etc/systemd/system/telegram-prm-archive-refresh.service
install -m 0644 systemd/telegram-prm-archive-refresh.timer /etc/systemd/system/telegram-prm-archive-refresh.timer
systemctl daemon-reload
systemctl enable --now telegram-prm-archive-refresh.timer
systemctl list-timers --all telegram-prm-archive-refresh.timer --no-pager
```

Actual final state:

```text
telegram-prm-archive-refresh.timer enabled=true active=active/waiting
next run=Mon 2026-08-17 08:14:28 CEST
telegram-prm-archive-refresh.service active=inactive
archive counts after timer install check: raw_posts=4166 posts=4166 posts_fts=4166 max_posted_at=2026-08-11T21:47:37+00:00
```

Installation note:

```text
An initial timer template with Requires=telegram-prm-archive-refresh.service
started the service immediately during enable --now. That immediate service run
failed before archive mutation because gitignored runtime backup/vector
directories were root-owned from the prior manual root refresh. The timer was
corrected by removing Requires=, runtime ownership for data/backups and
data/vector was restored to oc_you:oc_you, and systemd failed state was reset.
```

## Validation

```text
systemd-analyze verify systemd/telegram-prm-archive-refresh.service systemd/telegram-prm-archive-refresh.timer
pass; only unrelated host warning: /lib/systemd/system/snapd.service unknown RestartMode key
```

```text
PYTHONPATH=src python3 -m pytest tests/test_prm_archive_refresh_systemd.py tests/test_cli.py tests/test_ingestion.py -q
33 passed in 6.22s
```

```text
python3 tools/test_tiers.py focused-prm
199 passed in 24.22s
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
errors=0 warnings=0
```

```text
git diff --check
pass
```
