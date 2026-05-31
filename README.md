# Telegram Research Agent

Personal research intelligence for Telegram channels: ingest posts, filter noise, preserve evidence, and produce weekly project-aware decisions instead of a generic digest.

Status: active observation. Evidence discipline, decision feedback, Research Brief usefulness capture, and low-signal health alerts are implemented. Current work is tracked in `docs/tasks.md`.

Reference integration: `docs/entropy_core_gensyn_integration.md`.

## What It Is

This is a private, single-user pipeline that runs on a VPS and processes curated Telegram channels. It is designed for one operator who follows too many technical channels and wants a weekly brief that answers:

- what mattered this week
- why it matters for active projects
- what is worth trying now, deferring, or rejecting
- which sources and topics are earning trust over time

It is not a public bot, SaaS product, or generic summarizer.

## Core Loop

1. **Ingest** Telegram channel posts through Telethon.
2. **Normalize and cluster** posts into structured records and topics.
3. **Score deterministically** before any LLM call using personal interest, source quality, technical depth, novelty, and actionability.
4. **Apply preference feedback** from commands, Telegram reactions, and implementation-idea buttons.
5. **Record evidence** in `signal_evidence_items` with source channel, Telegram link, week, project scope, and selection reason.
6. **Generate weekly artifacts**:
   - `Research Brief`
   - `Implementation Ideas`
   - `Study Plan`
   - `MVP of the Week` from Demand-to-MVP Radar
7. **Record decisions** in `decision_journal` so acted-on, deferred, rejected, and completed items shape future output.

## Current Capabilities

- Deterministic scoring pipeline with strong/watch/cultural/noise buckets.
- Project relevance based on `src/config/projects.yaml`.
- Manual tags and feedback commands.
- Telegram reaction sync for original channel posts:
  - `🔥`, `⭐`, `❤️` -> `strong`
  - `👍`, `👏` -> `interesting`
  - `👀`, `🤔` -> `read_later`
  - `⚡`, `🛠️` -> `try_in_project`
  - `✅` -> `try_in_project` + `acted_on`
  - `👎`, `💩`, `❌` -> `low_signal` + `skipped`
- Inline Telegram feedback cards for `Implementation Ideas`:
  - `✅ сделал`
  - `🕒 позже`
  - `⛔ отказал`
  - `🧠 интересно`
- Implementation Ideas cards are compact enough to decide from Telegram without opening Telegraph for every item.
- Source-disciplined `Implementation Ideas`: actionable `[Implement]` and `[Build]` ideas require concrete Telegram message links and otherwise render an insufficient-evidence note.
- Operator-authored Research Brief usefulness capture into `weekly_usefulness_logs`.
- Scope-first memory:
  - canonical operational state
  - derived channel/project snapshots
  - verbatim evidence
  - decision journal
- Project signal diagnostics for explaining linked, candidate, and dropped digest topics.
- Telegraph delivery with HTML/file fallback.
- Cost, score, health, triage, and memory inspection commands.
- Health-check counters for project matches, links, scoped evidence, and zero-signal snapshots.
- Empty/low-signal weekly alerts so pipeline failures do not look like normal empty digests.
- `score-stats` includes recent Research Brief receipt health trends for empty and low-signal weeks.
- `health-check` warns when `src/config/projects.yaml` needs monthly review.
- Weekly MVP Radar bridge: Telegram exports opportunity seeds, Radar collects configured demand sources, Opus-class synthesis writes a separate MVP-of-week report, and the bot delivers it as a Telegraph article plus a copyable Markdown document.

## Main Commands

```bash
python3 src/main.py ingest
python3 src/main.py digest
python3 src/main.py sync-reactions --days 14
python3 src/main.py study
python3 src/main.py health-check
python3 src/main.py score-stats
python3 src/main.py cost-stats
python3 src/main.py insight-triage-stats
python3 src/main.py log-usefulness --week 2026-W22 --useful-section "Project Relevance" --decision "Prioritized callback validation"

python3 src/main.py memory inspect-evidence --project gdev-agent --limit 10
python3 src/main.py memory inspect-decisions --scope insight --limit 10
python3 src/main.py memory inspect-snapshots --stale-only
python3 src/main.py memory inspect-suppression --title "TITLE"
python3 src/main.py memory inspect-receipts --week 2026-W22
python3 src/main.py memory inspect-core-receipt --week 2026-W22
python3 src/main.py memory review-receipt --receipt-id rbr_... --status waived --notes "Accepted after manual read"
python3 src/main.py memory diagnose-project-signals --week 2026-W20
python3 src/main.py memory inspect-channel-intelligence --week 2026-W22 --project telegram-research-agent
python3 src/main.py channel-intelligence-report --week 2026-W22 --project telegram-research-agent
```

## Configuration

| File | Purpose |
|---|---|
| `src/config/channels.yaml` | Curated Telegram channels and baseline source priority |
| `src/config/profile.yaml` | Personal boost/downrank topics and taste rules |
| `src/config/projects.yaml` | Active projects, keywords, focus areas, and exclusions |
| `src/config/scoring.yaml` | Scoring weights, thresholds, routing rules |

Environment:

| Variable | Purpose |
|---|---|
| `AGENT_DB_PATH` | SQLite database path |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | Telethon MTProto ingestion |
| `TELEGRAM_SESSION_PATH` | Stored user session file |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_OWNER_CHAT_ID` | Telegram delivery and command bot |
| `LLM_API_KEY` | LLM provider key |
| `TELEGRAPH_TOKEN` | Stable Telegraph publishing account |
| `RADAR_REPO_PATH` / `RADAR_PYTHON` | Demand-to-MVP Radar repo and local venv Python |
| `DMR_MVP_SOURCE_CONFIG` | Radar weekly live-source config |
| `DMR_LLM_PROVIDER` / `DMR_LLM_MODEL_MVP_WEEKLY` | Radar MVP synthesis provider/model |

Radar live-source credentials are loaded separately by `systemd/telegram-mvp-weekly.service` from `/etc/demand-mvp-radar.env` when present. That file may contain `SERPAPI_API_KEY`, `GITHUB_TOKEN`, `YOUTUBE_API_KEY`, `PRODUCT_HUNT_TOKEN`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, and `STACK_EXCHANGE_KEY`.

`projects.yaml` is the curated active-project registry for scoped outputs. Older GitHub-synced DB rows may remain active in SQLite; project diagnostics and snapshots prefer the curated entries.

## Documentation

Start here:

- [docs/README.md](docs/README.md) — documentation map
- [docs/operator_workflow.md](docs/operator_workflow.md) — weekly operating workflow
- [docs/architecture.md](docs/architecture.md) — current system shape
- [docs/spec.md](docs/spec.md) — implementation-facing system specification
- [docs/report_format.md](docs/report_format.md) — weekly artifact contract
- [docs/mvp_weekly_radar.md](docs/mvp_weekly_radar.md) — MVP of the Week Radar bridge and credentials
- [docs/research_brief_receipt.md](docs/research_brief_receipt.md) — Research Brief receipt audit contract with implemented SQLite schema/storage helpers, generation-time receipt creation, delivery ref updates, deterministic verification checks, CLI inspection, operator review, and optional operator-only audit notes
- [docs/telegram_channel_intelligence.md](docs/telegram_channel_intelligence.md) — Channel Intelligence design, implemented schema migrations, deterministic repeated-claim extraction, source-observation refresh, active-project links, narrative candidates, inspection CLI, and optional Markdown report surface
- [docs/memory_architecture.md](docs/memory_architecture.md) — memory model
- [docs/memory_inspection.md](docs/memory_inspection.md) — memory debugging commands

Historical material lives under [docs/archive/](docs/archive/README.md).

## Development State

The main product architecture is implemented, Research Brief receipts are auditable, and Channel Intelligence schema plus claim/source/link/narrative refresh, inspection, and optional reporting groundwork is in place. Current work is maintenance and quality improvement: production validation, quality trends, and operator-experience refinements.
