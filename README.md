# Telegram Research Agent

Personal research intelligence for Telegram channels: ingest posts, filter noise, preserve evidence, and produce weekly project-aware decisions instead of a generic digest.

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
- Scope-first memory:
  - canonical operational state
  - derived channel/project snapshots
  - verbatim evidence
  - decision journal
- Telegraph delivery with HTML/file fallback.
- Cost, score, health, triage, and memory inspection commands.
- Empty/low-signal weekly alerts so pipeline failures do not look like normal empty digests.

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

python3 src/main.py memory inspect-evidence --project gdev-agent --limit 10
python3 src/main.py memory inspect-decisions --scope insight --limit 10
python3 src/main.py memory inspect-suppression --title "TITLE"
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

## Documentation

Start here:

- [docs/README.md](docs/README.md) — documentation map
- [docs/operator_workflow.md](docs/operator_workflow.md) — weekly operating workflow
- [docs/architecture.md](docs/architecture.md) — current system shape
- [docs/spec.md](docs/spec.md) — implementation-facing system specification
- [docs/report_format.md](docs/report_format.md) — weekly artifact contract
- [docs/memory_architecture.md](docs/memory_architecture.md) — memory model
- [docs/memory_inspection.md](docs/memory_inspection.md) — memory debugging commands

Historical material lives under [docs/archive/](docs/archive/README.md).

## Development State

The main product architecture is implemented. Current work is maintenance and quality improvement: better feedback capture, stronger project context, digest health checks, and keeping documentation aligned with runtime behavior.
