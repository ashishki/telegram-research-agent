# Telegram Research Agent

Private, single-operator Telegram research memory and grounded assistant.

The project used to be centered on weekly Telegram intelligence reports. The
current product direction is different:

```text
Personal Telegram Research Memory + Grounded Assistant
```

The operator asks questions in Telegram or CLI, the system searches the local
Telegram archive, builds a citation-safe context pack, and returns a grounded
answer or editor-style brief with source boundaries.

This is not a public SaaS product and not a released/dogfooded system yet. It is
currently running as a manual operator test environment.

## Current State

As of 2026-08-12:

- local archive RAG is implemented over SQLite FTS plus an approved local SQLite
  vector sidecar;
- Telegram `prm-assistant` runtime is installed, enabled, and active for manual
  testing only;
- ordinary Telegram text and voice transcripts route through the PRM auto path;
- Telegram `/research` and `/brief` return packaged topic reports with sources;
- Telegram `/chat` and model-based auto routing are separately provider-egress
  gated;
- a weekly PRM archive refresh timer is installed and waiting;
- legacy weekly-report automation remains frozen;
- PRM-19 dogfood has not started;
- release readiness is not claimed.

Current local archive snapshot on the active host:

| Item | Value |
| --- | --- |
| `raw_posts` | 4166 |
| `posts` | 4166 |
| `posts_fts` | 4166 |
| latest `posts.posted_at` | `2026-08-11T21:47:37+00:00` |

Current installed runtime state:

| Unit | State | Purpose |
| --- | --- | --- |
| `telegram-prm-assistant.service` | enabled, active | manual Telegram assistant testing |
| `telegram-prm-archive-refresh.timer` | enabled, active/waiting | weekly local archive freshness |
| `telegram-prm-archive-refresh.service` | inactive until timer fires | bounded archive refresh job |
| `telegram-bot.service` | disabled/inactive | legacy bot, do not use as PRM dogfood |
| `telegram-ai-split-report.timer` | disabled/inactive | legacy weekly report timer |

The next scheduled archive refresh is handled by systemd and runs the bounded
PRM refresh command once per week.

## What The Product Does Now

The working product slice is a private research assistant over retained
Telegram reading history.

It can:

- search the retained Telegram archive by natural-language question;
- combine SQLite FTS retrieval with the local vector sidecar for hybrid recall;
- enforce date windows for freshness-scoped questions such as "last two weeks";
- reject stale evidence instead of answering from old related posts;
- cite Telegram channels/posts from the local archive;
- synthesize Telegram answers into readable report-like messages;
- produce source-backed editor briefs for post-writing workflows;
- keep short Telegram follow-up context in memory for the current chat session;
- route ordinary Telegram messages to research, brief, or chat paths;
- provide local-only CLI answers without LLM calls;
- run LLM-backed chat only behind explicit provider-egress approval;
- refresh the archive weekly without restarting legacy report automation.

It does not currently:

- claim PRM-19 dogfood evidence;
- run live web research;
- run external embeddings or a hosted vector database;
- run production migrations automatically;
- sync reactions automatically in the PRM refresh timer;
- download media or run vision LLMs in the PRM refresh timer;
- generate weekly reports as the main product;
- save durable memory without explicit confirmation;
- commit private Telegram source text or generated private reports.

## How It Works

Current PRM path:

```text
Telegram channels
  -> local SQLite raw_posts
  -> normalized posts + posts_fts
  -> optional local SQLite vector sidecar
  -> bounded retrieval
  -> citation-safe context pack
  -> deterministic answer gate
  -> optional bounded LLM synthesis
  -> Telegram/CLI answer with sources and boundaries
```

Key storage:

- `data/agent.db` — private local SQLite database, gitignored;
- `raw_posts` — retained Telegram source rows;
- `posts` / `posts_fts` — normalized searchable archive;
- `data/vector/archive_vector.sqlite` — local vector sidecar, gitignored;
- `data/backups/` — SQLite backups created before bounded refreshes, gitignored;
- `data/output/**` — private generated outputs, gitignored.

The vector sidecar is local-only. It does not use external embeddings and does
not mutate the canonical database.

## Telegram Usage

The intended manual-test interface is Telegram.

In the running `prm-assistant` mode, send a normal message such as:

```text
Что было интересного по моделям за последние две недели?
Что мои каналы писали про AI transformation в компаниях?
Кто нанимает, а кто увольняет из-за AI?
Собери мне редакторский бриф по агентам и enterprise adoption.
```

The assistant should choose the right mode automatically:

- archive/source questions go to local research;
- writing/source-packet questions go to editor brief;
- short follow-ups reuse recent chat context;
- generic chat is only allowed when provider-egress gates are enabled.

Manual fallback commands:

```text
/research <question>
/brief <question>
/chat <question>
```

Expected Telegram answer style for `/research`, `/brief`, and auto-routed
research/brief:

- packaged topical report, not raw retrieval debug output;
- clear sections;
- source list;
- freshness and evidence boundaries in plain language;
- no visible retrieval metrics, costs, tool-call counts, or debug footer.

## CLI Usage

Use `PYTHONPATH=src` for local commands.

Safe status:

```bash
PYTHONPATH=src python3 src/main.py memory status
```

Local-only evidence answer, no LLM/provider egress:

```bash
PYTHONPATH=src python3 src/main.py memory ask "что есть по eval gates?"
```

Bounded local research over archive, linked-source cache, and project context:

```bash
PYTHONPATH=src python3 src/main.py memory research --hybrid \
  "Что было интересного по моделям за последние две недели?"
```

Debug/audit rendering:

```bash
PYTHONPATH=src python3 src/main.py memory research --hybrid --debug \
  "что мои каналы писали про AI transformation?"
```

LLM-backed CLI chat requires explicit approval:

```bash
PYTHONPATH=src python3 src/main.py memory chat --allow-provider-egress
```

Build or refresh the local vector sidecar:

```bash
PYTHONPATH=src python3 src/main.py memory vector-index --force
```

Manual bounded archive refresh:

```bash
set -a
source /srv/openclaw-you/.env
set +a
PYTHONPATH=src python3 src/main.py memory refresh-archive \
  --days 21 \
  --confirm-canonical-write \
  --json
```

The refresh command deliberately avoids migrations, reaction sync, media
download, vision LLM, provider egress, source-event writes, report generation,
dogfood evidence, and release claims.

Private editor source packet workflow:

```bash
PYTHONPATH=src python3 src/main.py memory ai-transformation-source-packet \
  --days 92 \
  --top-channels 8 \
  --max-posts 120
```

Generated private files remain under ignored `data/output/**`.

## Weekly Archive Refresh Timer

The dedicated PRM archive freshness timer is separate from legacy ingestion and
report timers.

Repo templates:

- `systemd/telegram-prm-archive-refresh.service`
- `systemd/telegram-prm-archive-refresh.timer`

Installed command:

```bash
/srv/openclaw-you/venv/bin/python3 src/main.py memory refresh-archive \
  --days 21 \
  --confirm-canonical-write \
  --json
```

Schedule:

```text
Mon *-*-* 08:10:00 Europe/Berlin
AccuracySec=5m
RandomizedDelaySec=15m
Persistent=false
```

`Persistent=false` is intentional: installing the timer must not immediately
repeat a canonical DB write if the archive is already fresh.

Status commands:

```bash
systemctl list-timers --all telegram-prm-archive-refresh.timer --no-pager
systemctl status telegram-prm-archive-refresh.timer --no-pager
systemctl status telegram-prm-archive-refresh.service --no-pager
```

Install/update:

```bash
systemd-analyze verify \
  systemd/telegram-prm-archive-refresh.service \
  systemd/telegram-prm-archive-refresh.timer

sudo install -m 0644 systemd/telegram-prm-archive-refresh.service \
  /etc/systemd/system/telegram-prm-archive-refresh.service
sudo install -m 0644 systemd/telegram-prm-archive-refresh.timer \
  /etc/systemd/system/telegram-prm-archive-refresh.timer
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-prm-archive-refresh.timer
```

Rollback:

```bash
sudo systemctl disable --now telegram-prm-archive-refresh.timer
sudo rm -f /etc/systemd/system/telegram-prm-archive-refresh.service
sudo rm -f /etc/systemd/system/telegram-prm-archive-refresh.timer
sudo systemctl daemon-reload
```

## Telegram Assistant Runtime

Repo template:

- `systemd/telegram-prm-assistant.service`

Start manually:

```bash
PYTHONPATH=src python3 src/main.py prm-assistant
```

Systemd install/update:

```bash
systemd-analyze verify systemd/telegram-prm-assistant.service
sudo install -m 0644 systemd/telegram-prm-assistant.service \
  /etc/systemd/system/telegram-prm-assistant.service
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-prm-assistant.service
```

Status/logs:

```bash
systemctl status telegram-prm-assistant.service --no-pager
journalctl -u telegram-prm-assistant.service -n 100 --no-pager
```

Provider-egress gates used by the Telegram runtime:

```text
PRM_ARCHIVE_HYBRID_RETRIEVAL=approved
PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1
PRM_TELEGRAM_AUTO_LLM_ROUTER=1
PRM_TELEGRAM_RAG_LLM_SYNTHESIS=1
```

These flags allow bounded cited snippets/context to be sent to the configured
LLM provider for synthesis. They do not allow raw corpus egress.

The archive-refresh timer explicitly overrides Telegram LLM/router flags to
`0` for its own unit.

## Development And Validation

Fast PRM-focused validation:

```bash
python3 tools/test_tiers.py focused-prm
```

Playbook/governance validation:

```bash
python3 tools/playbook_validate.py --root . \
  --check tasks \
  --check placeholders \
  --check readiness \
  --check delivery \
  --check references
```

Full verifier:

```bash
python3 tools/verify_project.py --root .
```

Generic test run:

```bash
PYTHONPATH=src python3 -m pytest tests/ -q
```

Before committing:

```bash
git diff --check
git status --short
```

## Privacy And Safety Boundaries

Private Telegram data must stay local unless the operator explicitly approves a
bounded egress path.

Do not commit:

- `data/agent.db`;
- `data/vector/**`;
- `data/backups/**`;
- `data/output/**`;
- generated private Telegram source packets;
- full private Telegram post text.

Do not start or enable as PRM dogfood:

- `telegram-bot.service`;
- `telegram-ai-split-report.timer`;
- legacy report/digest/MVP timers.

Do not run without explicit task approval:

- live web research;
- reaction sync;
- media download or vision LLM;
- external embeddings;
- hosted vector services;
- production migrations;
- full archive LLM backfill;
- Radar/Frontier/report generation;
- compatibility file deletion/archive/move.

## Current Gates

Implemented PRM slices include:

- bounded SQLite FTS archive search;
- grounded assistant answer contracts;
- confirmation-gated saved-memory proposals;
- deterministic Knowledge Library topic page renderer;
- project context and decision-support routing;
- Weekly Brief V3 deterministic secondary projection;
- safe runtime workflow contracts;
- PRM-18 release/dogfood gate;
- PRM-18A through PRM-18C LLM chat UX;
- PRM-24 generated seed gold eval set;
- PRM-27 local vector sidecar;
- PRM-28 product RAG answer gate.

Still gated:

- PRM-19 dogfood start requires explicit human dogfood-start approval;
- PRM-20 cleanup/archive requires real PRM-19 dogfood evidence and explicit
  compatibility archive/delete/move approval;
- generated PRM-24 labels are operator-approved seed evidence, not independent
  human-reviewed gold evidence;
- the product is not released and public value is not proven.

## Legacy Surfaces

The repository still contains report-centered commands and systemd templates
for historical compatibility:

```bash
python3 src/main.py ingest
python3 src/main.py sync-reactions --days 14
python3 src/main.py weekly-intelligence-v2 --week 2026-W28
python3 src/main.py report-v2-rollout-gate --week 2026-W28 --json
python3 src/main.py mvp-weekly
```

They are not the current product path. Do not use their outputs as PRM dogfood
or release evidence.

## Canonical Docs

- [Product Operating Model](docs/PRODUCT_OPERATING_MODEL.md)
- [Operator Workflow](docs/operator_workflow.md)
- [Project Brief](docs/PROJECT_BRIEF.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation Contract](docs/IMPLEMENTATION_CONTRACT.md)
- [Personal Research Memory Product Contract](docs/personal_research_memory_product_contract.md)
- [Privacy Threat Model](docs/PRIVACY_THREAT_MODEL.md)
- [Cost Budget](docs/COST_BUDGET.md)
- [Active Tasks](docs/tasks.md)
- [Evidence Index](docs/EVIDENCE_INDEX.md)
- [Codex Handoff](docs/CODEX_PROMPT.md)

Key receipts:

- [Manual Telegram Assistant Activation](docs/audit/PRM_MANUAL_TELEGRAM_ASSISTANT_ACTIVATION_2026-08-11.md)
- [Manual Archive Refresh](docs/audit/PRM_MANUAL_ARCHIVE_REFRESH_2026-08-12.md)
- [Weekly Archive Refresh Timer](docs/audit/PRM_WEEKLY_ARCHIVE_REFRESH_TIMER_2026-08-12.md)
