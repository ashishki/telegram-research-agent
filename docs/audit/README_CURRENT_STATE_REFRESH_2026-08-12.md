# README Current State Refresh - 2026-08-12

Status: documentation refresh

## Scope

The README was rewritten to describe the current project state after the PRM
manual Telegram assistant activation, manual archive refresh, and weekly
archive-refresh timer work.

This task did not run Telegram ingestion, live web research, provider egress,
reaction sync, migrations, media download, vision LLM, report generation,
dogfood start, release claim, or compatibility cleanup.

## Updated README Coverage

The README now describes:

- the current product direction: Personal Telegram Research Memory + Grounded
  Assistant;
- the active manual-test runtime state;
- the current local archive aggregate snapshot;
- Telegram user workflow for ordinary messages, `/research`, `/brief`, and
  `/chat`;
- CLI workflows for `memory status`, `memory ask`, `memory research`,
  `memory chat`, `memory vector-index`, `memory refresh-archive`, and the
  private source-packet workflow;
- weekly archive-refresh timer purpose, command, schedule, install/status, and
  rollback commands;
- Telegram assistant service install/status commands;
- provider-egress gates and privacy boundaries;
- current PRM implementation/gate status;
- legacy surfaces that remain compatibility-only;
- canonical docs and key audit receipts.

## Evidence Used

Read:

```text
AGENTS.md
docs/CODEX_PROMPT.md
docs/tasks.md
README.md
docs/PRODUCT_OPERATING_MODEL.md
docs/EVIDENCE_INDEX.md
docs/operator_workflow.md
systemd/telegram-prm-assistant.service
systemd/telegram-prm-archive-refresh.service
systemd/telegram-prm-archive-refresh.timer
```

Local aggregate/runtime checks:

```text
archive counts: raw_posts=4166 posts=4166 posts_fts=4166
latest posts.posted_at=2026-08-11T21:47:37+00:00
telegram-prm-assistant.service=enabled/active
telegram-prm-archive-refresh.timer=enabled/active
telegram-prm-archive-refresh.service=inactive
```

## Validation

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
errors=0 warnings=0
```

```text
python3 tools/test_tiers.py focused-prm
199 passed in 29.26s
```

```text
git diff --check
pass
```

```text
README required marker check
pass
```
