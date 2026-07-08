# Telegram Research Agent

Personal research intelligence for Telegram channels: ingest posts, preserve evidence, extract AI knowledge atoms, track evolving idea threads, and produce weekly decision reports instead of a generic digest.

Status: active AI Knowledge Intelligence Desk with a safe HPI dogfood
foundation. The legacy Research Brief / Implementation Ideas loop still works,
but the newer knowledge-atom, idea-thread, Weekly AI Intelligence Workbook,
feedback, Strategy Reviewer, MVP Radar bridge, generated Obsidian, read-only PI
facade/tool catalog, Hermes concierge commands, action-status projection, and
dogfood review layers are the primary direction. Current work is tracked in
`docs/tasks.md`.

Current next work: Hermes Telegram UX cleanup (`Asia/Tbilisi` reminders and no
MarkdownV2 escape artifacts), Opus-class feedback strategy, a bounded
market/business channel pack for MVP Radar, a split between Knowledge Atlas and
Weekly Intelligence Brief HTML surfaces, and a curated-only semantic RAG
decision/prototype. Raw Telegram firehose RAG and full-year archive processing
remain deferred.

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
6. **Extract Knowledge Atoms** from recent posts with cheap bounded LLM batches.
7. **Refresh Idea Threads** with 7/30/90 day momentum, source counts, and stale/superseded status.
8. **Run Frontier Analysis** over compressed thread/atom context for the current week.
9. **Generate weekly artifacts**:
   - `Weekly AI Intelligence Workbook` visual HTML report
   - standalone `AI Intelligence` HTML report and JSON sidecar
   - generated Obsidian vault projection
   - legacy `Research Brief`, `Implementation Ideas`, `Study Plan`
   - `MVP of the Week` from Demand-to-MVP Radar
10. **Record decisions and confirmed feedback** so read, tried, useful, missed, wrong-priority, trust-correction, and project-application signals shape future output.

## Current Capabilities

- Deterministic scoring pipeline with strong/watch/cultural/noise buckets.
- Project relevance based on `src/config/projects.yaml`.
- Manual tags and feedback commands.
- Telegram reaction sync for original channel posts: any visible personal reaction records an `interesting` tag plus `operator_marked_interesting` feedback; aggregate channel reaction counts are ignored as personal feedback and the raw emoji is preserved only as metadata.
- Inline Telegram feedback cards for `Implementation Ideas`:
  - `✅ сделал`
  - `🕒 позже`
  - `⛔ отказал`
  - `🧠 интересно`
- AI workbook feedback intake through `/feedback`, `/feedback_voice`, `/feedback_confirm`, and `/feedback_discard`; parsed feedback is stored only after confirmation.
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
- Knowledge Atom extraction via `knowledge-extract`: bounded, resumable JSON extraction from raw Telegram posts with source citations.
- Temporal Idea Threads via `idea-threads`: deterministic grouping of atoms into evolving AI ideas with momentum and status.
- Frontier-model synthesis via `frontier-analysis`: top-model weekly interpretation over compressed 12-week context.
- Stakeholder-facing Weekly AI Intelligence Workbook via `ai-visual-report`: Russian decision brief, strong signals, deep explanation cards, claim evidence cards with quote verification/evidence tiers, concept diagrams, project implementation suggestions, MVP Radar section, feedback prompts, JSON sidecar, and embedded Archify/local diagrams when available.
- Strategy Reviewer via `strategy-reviewer`: advisory-only keep/change/demote/test-next-week suggestions and Codex-ready tasks from confirmed workbook feedback; it does not mutate source code, prompts, thresholds, profile, or projects.
- HPI read-only foundation: `PersonalIntelligenceFacade`, deterministic curated retrieval items, and bounded PI tools expose workbook, thread, action, MVP, feedback, marked-post, Strategy Reviewer, and action-status DTOs without raw DB sessions, vector search, or mutation methods.
- Hermes Telegram concierge commands: `/weekly`, `/actions`, `/explain`, `/projects`, `/mvp`, `/strategy`, and `/codex` provide short operator routing; `/codex` prepares prompt text only and never executes Codex.
- Dogfood review helper: compact private weekly dogfood JSON/Markdown artifacts can track time-to-understand, sections read, completed actions, feedback counts, MVP status, decisions changed, user value, and friction before HPI-9/HPI-10 decisions.
- Generated Obsidian projection via `obsidian-export`: bounded weekly, thread, tool/model, practice, channel, read-queue, try/build, experiment, project-watch, feedback-summary, and strategy-review notes with generated-file markers and source links.
- Honest project implications: the visual report suppresses broad keyword overlaps like `AI`, `workflow`, and `evidence`; a zero project-lead count means the current atom/thread evidence was too weak for a user-facing project claim.

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

# AI Knowledge Intelligence loop over the last 12 weeks
python3 src/main.py knowledge-extract --weeks 12 --model cheap
python3 src/main.py idea-threads --weeks 12
python3 src/main.py frontier-analysis --week 2026-W28 --lookback-weeks 12 --model strong
python3 src/main.py ai-intelligence-report --week 2026-W28 --skip-refresh
python3 src/main.py ai-visual-report --week 2026-W28 --skip-refresh --threads-limit 12 --atoms-limit 8
python3 src/main.py obsidian-export --week 2026-W28
python3 src/main.py strategy-reviewer --week 2026-W28 --output-path data/output/reviews/2026-W28-strategy-review.json

# Send the visual HTML to Telegram as a document when bot credentials are configured
python3 src/main.py ai-visual-report --week 2026-W28 --skip-refresh --deliver
```

## Production Readiness

On the single-user VPS, the operational baseline is:

- `telegram-bot.service` runs Hermes command polling with restart-on-failure.
- `telegram-ingest.timer` refreshes Telegram data, reactions, clustering, and
  scoring weekly.
- `telegram-digest.timer` delivers the legacy weekly brief package.
- `telegram-mvp-weekly.timer` runs the Radar bridge after the weekly digest.
- `telegram-cleanup.timer` strips raw JSON and old posts after the weekly
  processing window.
- `telegram-study-reminder-tue.timer` and
  `telegram-study-reminder-fri.timer` send study reminders.
- `telegram-reminders.timer` sends one daily operator reminder check-in with
  inline `сделал` / `не сделал` buttons.

Quick checks:

```bash
systemctl is-active telegram-bot.service telegram-ingest.timer telegram-digest.timer telegram-mvp-weekly.timer telegram-cleanup.timer telegram-reminders.timer
systemctl list-timers 'telegram-*' --all --no-pager
bash scripts/healthcheck.sh
PYTHONPATH=src python3 src/main.py ops-validate
```

Current Hermes scope is deliberately bounded. It supports both short Telegram
commands and a normal chat path: send plain text, `/chat <message>`,
`/hermes <message>`, or `/ask <message>`. Plain text and voice transcripts are
first classified as chat, feedback, or reminder. For chat, the LLM may plan
calls only to the read-only PI tool catalog, then answer from curated
workbook/atom/thread/action evidence. `/codex` prepares prompt text only.
Hermes does not run Codex, does not mutate config/code/profile/project files,
and does not replace the workbook as the primary reading surface.

Voice input is supported when `OPENAI_API_KEY` is configured. The bot
downloads the Telegram `.ogg` voice file to temporary storage, sends it to the
OpenAI audio transcription endpoint with `VOICE_TRANSCRIPTION_MODEL`
defaulting to `whisper-1`, routes the transcript through the Hermes intent
classifier, and deletes the local audio file. If the transcript is feedback,
it enters the confirmation-gated `/feedback_voice` flow. If it is a reminder,
it creates a local reminder for the daily check-in. If `OPENAI_API_KEY` is
missing, voice messages return a clear text fallback.

Current retrieval is deterministic curated retrieval over workbook sidecars,
claim cards, Knowledge Atoms, Idea Threads, action cards, MVP/Strategy
Reviewer/feedback projections, and related DTOs. There is no raw Telegram
firehose RAG, no vector DB, and no assistant access to raw SQLite sessions.

Telethon reaction sync uses the configured user session to inspect original
channel posts. Any visible personal reaction is treated as interesting; no
reaction is unknown, not negative. Before dogfood, validate it with a live
reaction on a recent source post, then run:

```bash
PYTHONPATH=src python3 src/main.py sync-reactions --days 14 --limit 30
PYTHONPATH=src python3 src/main.py ops-validate
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
| `OPENAI_API_KEY` | Optional OpenAI audio transcription key for Telegram voice input |
| `VOICE_TRANSCRIPTION_MODEL` | Optional transcription model override; defaults to `whisper-1` |
| `TELEGRAM_VOICE_MEDIA_DIR` | Optional temporary directory for downloaded Telegram voice files |
| `REMINDER_TIMEZONE` | Optional local timezone for daily operator reminders; defaults to `Europe/Berlin` |
| `TELEGRAPH_TOKEN` | Stable Telegraph publishing account |
| `RADAR_REPO_PATH` / `RADAR_PYTHON` | Demand-to-MVP Radar repo and local venv Python |
| `DMR_MVP_SOURCE_CONFIG` | Radar weekly live-source config |
| `DMR_LLM_PROVIDER` / `DMR_LLM_MODEL_MVP_WEEKLY` | Radar MVP synthesis provider/model |
| `ARCHIFY_ROOT` | Optional path to an installed Archify skill directory for `ai-visual-report`; otherwise a deterministic fallback diagram is embedded |

Radar live-source credentials are loaded separately by `systemd/telegram-mvp-weekly.service` from `/etc/demand-mvp-radar.env` when present. That file may contain `SERPAPI_API_KEY`, `GITHUB_TOKEN`, `YOUTUBE_API_KEY`, `PRODUCT_HUNT_TOKEN`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, and `STACK_EXCHANGE_KEY`.

`projects.yaml` is the curated active-project registry for scoped outputs. Older GitHub-synced DB rows may remain active in SQLite; project diagnostics and snapshots prefer the curated entries.

## Documentation

Start here:

- [docs/README.md](docs/README.md) — documentation map
- [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) — strategic project plan
- [docs/next_development_roadmap.md](docs/next_development_roadmap.md) — next development roadmap and AI-ready tasks
- [docs/report_quality_roadmap.md](docs/report_quality_roadmap.md) — report-quality, artifact feedback, internal cost guardrail, and Demand-to-MVP Radar handoff tasks
- [docs/ai_knowledge_intelligence_roadmap.md](docs/ai_knowledge_intelligence_roadmap.md) — AI Knowledge Intelligence Desk architecture, phases, visual report, and Obsidian projection
- [docs/ai_intelligence_workbook_roadmap.md](docs/ai_intelligence_workbook_roadmap.md) — completed KIR-Q0..KIR-Q13 workbook, feedback, Radar contract, Strategy Reviewer, and Obsidian projection roadmap
- [docs/hermes_pi_assistant_roadmap.md](docs/hermes_pi_assistant_roadmap.md) — HPI roadmap for Hermes concierge, PI Assistant bounded tools, dogfood, and deferred vector/post-dogfood gates
- [docs/dogfood_4_week_plan.md](docs/dogfood_4_week_plan.md) — four-week dogfood metrics, weekly checklist, success criteria, and simplification triggers
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

The AI Knowledge Intelligence path is implemented end-to-end for local operation: raw posts can be atomized, atoms can be grouped into temporal threads, a frontier analysis can be persisted, the user-facing workbook HTML can be generated and delivered, feedback can be confirmed into memory, Strategy Reviewer can produce advisory improvement tasks, bounded Obsidian notes can be regenerated from the same knowledge layer, and Hermes/PI can read curated intelligence through bounded read-only interfaces.

The honest limitation is quality of interpretation and dogfood proof, not missing plumbing: project implications are conservative keyword/evidence leads, not full project-priority decisions; empty project leads are allowed when evidence is too broad. User value is not proven until the four-week dogfood protocol produces real feedback, actions, decisions changed, and friction scores. HPI-9 vector retrieval and HPI-10 post-dogfood product decisions stay deferred until then.
