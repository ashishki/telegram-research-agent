# PRM Safe Assistant Runtime Receipt - 2026-07-29

Status: implemented but not activated

## Scope

This change adds an explicit safe Telegram runtime for the Personal Telegram
Research Memory + Grounded Assistant product shape.

Implemented entrypoints:

- CLI: `PYTHONPATH=src python3 src/main.py prm-assistant`;
- repo unit template: `systemd/telegram-prm-assistant.service`.

The entrypoints were added for future approved dogfood. They were not started,
enabled, installed, or used to collect dogfood evidence.

## Runtime Boundary

Safe mode uses `BOT_RUNTIME_PRM_ASSISTANT`.

Allowed command surface:

- `/research`;
- `/chat`, `/hermes`, `/ask`;
- `/weekly`, `/actions`, `/explain`, `/projects`, `/mvp`, `/strategy`;
- `/codex`, `/costs`, `/status`;
- `/start`, `/help`.

Blocked command surface:

- legacy generation and delivery: `/run_digest`, `/run_mvp_weekly`, `/digest`,
  `/study`, `/study_done`, old report delivery paths;
- direct durable writes: `/feedback`, `/feedback_voice`, `/feedback_confirm`,
  `/feedback_discard`, `/tag`, `/mark_*`, `/remind`, `/reminders`,
  `/remind_cancel`;
- legacy `/message` and `/voice` intent routing because it can classify text as
  reminder or feedback and write local DB rows;
- legacy inline callbacks because they can write decision, reminder, or
  artifact-feedback rows.

Ordinary Telegram text and voice transcripts were initially dispatched as
`/chat` in safe mode. On 2026-08-11 this was amended after the local UX trial:
ordinary text, voice transcripts, and explicit `/research <question>` now route
to the local-only compact `memory research` renderer. `/chat` remains a
separate LLM-backed command requiring provider-egress approval and
`PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1`. Voice fallback copy hides legacy
feedback commands.

The safe CLI entrypoint does not run automatic startup migrations. Production
DB migration remains a separate approved maintenance action.

## Product Boundary

MVP Radar remains a decision-evidence card, not a product center or build
approval path. Safe mode does not run Radar, Frontier, report generation,
ingestion, reaction sync, full archive indexing, embeddings, external web
research, or LLM extraction jobs.

The only PRM write path intended for safe assistant use is the existing
confirmation-gated `confirm_save_proposal` tool inside `/chat`, which requires
an exact proposal object and confirmation token. Legacy feedback confirmation
commands are blocked in the bot surface.

## Activation Boundary

`telegram-bot.service` and `telegram-ai-split-report.timer` remain legacy and
must not be restarted as PRM dogfood.

Starting `src/main.py prm-assistant` or
`systemd/telegram-prm-assistant.service` is a dogfood-start action. It requires
explicit human dogfood approval and accepted or cleared PRM-18 blockers.

## Evidence

Commands run:

```text
PYTHONPATH=src python3 src/main.py --help | rg -n "prm-assistant|bot"
prm-assistant listed in CLI help; polling was not started
```

```text
PYTHONPATH=src python3 -m pytest tests/test_cli.py tests/test_handlers.py tests/test_callbacks.py -q
52 passed, 3 subtests passed in 18.79s
```

```text
python3 tools/test_tiers.py fast-contract
204 passed, 9 subtests passed in 59.91s
```

```text
systemd-analyze verify systemd/telegram-prm-assistant.service
exit=0; unrelated host warning: /lib/systemd/system/snapd.service unknown RestartMode key
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
pass, no output
```

No live Telegram ingestion, reaction sync, Radar, Frontier, report generation,
full archive indexing, embeddings, external web research jobs, systemd starts,
or production database writes were performed.
