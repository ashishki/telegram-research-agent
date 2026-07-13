# Telegram Research Agent

Personal research intelligence for Telegram channels: ingest posts, preserve evidence, extract AI knowledge atoms, track evolving idea threads, and produce weekly decision reports instead of a generic digest.

State: portfolio-grade Personal AI / Knowledge Intelligence System in progress;
Report V2 product correction active after the W29 reader-value audit.
The legacy Research Brief / Implementation Ideas loop still works, but the
product direction is now a private decision and learning intelligence system
centered on the Weekly Intelligence Brief, Knowledge Atlas, bounded Hermes/PI
assistant, Project Intelligence, Learning Intelligence, and a parallel MVP
Radar validation track.

Active Report V2 roadmap: `docs/intelligence_report_v2_roadmap.md`.
Broader product roadmap: `docs/portfolio_grade_intelligence_roadmap.md`.
Canonical active backlog: `docs/tasks.md`.
Current implementation gate:
`IRX-3 - Reaction-To-Ranking Personalization And Effect Receipt`; IRX-1
completed-week semantics and the additive IRX-2 manifest/same-run Radar
orchestration are implemented and focused-test verified. `PGI-007` dogfood is
superseded as the next action and remains blocked until the `IRX-14` start gate
passes.

Current baseline: knowledge atoms, idea threads, canonical report contracts,
split Brief / Atlas artifacts, Brief cockpit plumbing, Atlas audit navigation,
durable Project/Learning Intelligence projections, weekly scorecard fixtures,
Hermes/PI read-only foundation, artifact freshness awareness, feedback
provenance helpers, Strategy Reviewer, and Radar RVE bridge exist in code with
focused tests. The honest gap is four-week dogfood evidence and portfolio-ready
evaluation proof from real operator runs. The W29 artifacts are technically
valid but not reader-ready: they expose wrong-period, Radar-handoff,
personalization, editorial, thread-curation, and visualization failures. The
shared Report V2 period foundation and technical manifest package are
implemented. Reaction personalization, canonical curation, editorial synthesis,
and the reader V2 surfaces remain planned, and dogfood has not started. Raw
Telegram firehose RAG, assistant
mutations, full-year archive processing, and build-ready Radar decisions from
context-only evidence remain out of scope.

## Dogfood Stabilization Note

Dogfood-blocking repo hygiene was stabilized on 2026-07-08 in commit
`3ac2515`:

- market context lens output is isolated for non-default seed exports, so tests
  and one-off exports no longer reuse stale `data/output/market_context_lens`
  state;
- Telegram bot dispatch logs record command names and text lengths instead of
  raw operator messages or feedback text;
- generated `data/output/**` artifacts are ignored by default;
- feedback docs now distinguish pending feedback drafts from confirmed feedback
  memory events;
- the dogfood plan includes a concrete Week 1 command checklist and smoke
  checks.

Remaining hygiene is intentionally separate: older tracked `data/output`
reports still need a fixture-vs-private-artifact decision before any
`git rm --cached` cleanup, and ad-hoc manual review artifacts under
`docs/artifacts/` should be committed only when explicitly intended.

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
8. **Run Frontier Analysis** over compressed thread/atom context for the resolved reporting period (the last completed ISO week by default).
9. **Generate weekly artifacts**:
   - `Weekly AI Intelligence Workbook` visual HTML report
   - split `Knowledge Atlas` and `Weekly Intelligence Brief` HTML/JSON surfaces
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
- AI workbook feedback intake through `/feedback`, `/feedback_voice`, `/feedback_confirm`, and `/feedback_discard`; text and voice transcripts are interpreted by an Opus-class feedback strategist with deterministic fallback, and confirmed feedback memory is stored only after confirmation.
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
- Market/business analyst context for MVP Radar: selected market channels produce a bounded, cited, deterministic sidecar from curated Knowledge Atoms and Idea Threads, with raw fallback only for channels not yet extracted; the export adds context-only analyst notes without consuming the ordinary seed limit.
- Knowledge Atom extraction via `knowledge-extract`: bounded, resumable JSON extraction from raw Telegram posts with source citations.
- Temporal Idea Threads via `idea-threads`: deterministic grouping of atoms into evolving AI ideas with momentum and status.
- Frontier-model synthesis via `frontier-analysis`: top-model weekly interpretation over compressed 12-week context.
- Stakeholder-facing Weekly AI Intelligence Workbook via `ai-visual-report`: Russian decision brief, strong signals, deep explanation cards, claim evidence cards with quote verification/evidence tiers, concept diagrams, project implementation suggestions, MVP Radar section, feedback prompts, JSON sidecar, and embedded Archify/local diagrams when available.
- Split V1 HTML via `ai-split-report`: a detailed Atlas/audit surface and a
  short Brief shell. Both write distinct HTML/JSON sidecars and can be
  delivered to Telegram, but the W29 audit found that they do not yet satisfy
  the Report V2 reader contract.
- Project and Learning Intelligence projections: Brief/Atlas sidecars and HTML expose external project signals, confirmed implications, weak watches, rejected broad overlaps, tiny PR ideas, stale decisions, research debt, repeated themes without action, learning objectives, and learning stage counts without treating passive reading as mastery.
- Strategy Reviewer via `strategy-reviewer`: advisory-only keep/change/demote/test-next-week suggestions and Codex-ready tasks from confirmed workbook feedback; it does not mutate source code, prompts, thresholds, profile, or projects.
- HPI read-only foundation: `PersonalIntelligenceFacade`, curated retrieval items, transient SQLite FTS ranking, and bounded PI tools expose workbook, thread, action, MVP, feedback, marked-post, Strategy Reviewer, and action-status DTOs without raw DB sessions, vector search, or mutation methods.
- Hermes Telegram concierge commands: `/weekly`, `/actions`, `/explain`, `/projects`, `/mvp`, `/strategy`, and `/codex` provide short operator routing; `/codex` prepares prompt text only and never executes Codex.
- Dogfood review and scorecard helper: compact private weekly dogfood JSON/Markdown artifacts plus `weekly-intelligence-scorecard.v1` can track correctness, relevance, decisions/actions, learning, UX, Radar honesty, operations, time-to-understand, sections read, completed actions, feedback counts, MVP status, decisions changed, user value, friction, and false-confidence incidents before portfolio claims.
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
# Replace 2026-W28 with the target ISO week.
python3 src/main.py knowledge-extract --weeks 12 --model cheap
python3 src/main.py idea-threads --weeks 12
python3 src/main.py frontier-analysis --week 2026-W28 --lookback-weeks 12 --model strong
python3 src/main.py ai-intelligence-report --week 2026-W28 --skip-refresh
python3 src/main.py ai-visual-report --week 2026-W28 --skip-refresh --threads-limit 12 --atoms-limit 8
python3 src/main.py ai-split-report --week 2026-W28 --skip-refresh --threads-limit 24 --atoms-limit 8
python3 src/main.py obsidian-export --week 2026-W28
python3 src/main.py strategy-reviewer --week 2026-W28 --output-path data/output/reviews/2026-W28-strategy-review.json

# Send the visual HTML to Telegram as a document when bot credentials are configured
python3 src/main.py ai-visual-report --week 2026-W28 --skip-refresh --deliver

# Send the two split HTML reports to Telegram as documents
python3 src/main.py ai-split-report --week 2026-W28 --skip-refresh --deliver
```

## Production Readiness

The services below describe the current diagnostic V1 deployment. Scheduled
HTML success is not Report V2 readiness, and the four-week dogfood is paused
until IRX-14.

On the single-user VPS, the operational baseline is:

- `weekly-intelligence-v2` is the explicit additive IRX-2 package command. It
  creates a new immutable run directory, binds same-run artifacts by identity
  and checksum, and leaves the deployed V1 timer/commands intact. Inspect its
  bounded options with
  `PYTHONPATH=src python3 src/main.py weekly-intelligence-v2 --help`.

- `telegram-bot.service` runs Hermes command polling with restart-on-failure.
- `telegram-ai-split-report.timer` is the only project weekly report timer. It
  runs every Monday at 09:00 Europe/Berlin and triggers
  `telegram-ai-split-report.service`.
- `telegram-ai-split-report.service` refreshes Telegram ingestion first, then
  runs `ai-split-report --deliver --threads-limit 24 --atoms-limit 8` so the
  Weekly Intelligence Brief and Knowledge Atlas HTML files are delivered to
  Telegram as documents.
- Legacy `telegram-ingest.timer`, `telegram-digest.timer`,
  `telegram-mvp-weekly.timer`, `telegram-cleanup.timer`,
  `telegram-study-reminder-*.timer`, `telegram-reminders.timer`, and
  `reminder.timer` are disabled in the current V1 deployment baseline.
  Re-enable them only with an explicit schedule decision.

Quick checks:

```bash
systemctl is-active telegram-bot.service telegram-ai-split-report.timer
systemctl is-enabled telegram-ai-split-report.timer
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

Current retrieval is curated retrieval over workbook sidecars, claim cards,
Knowledge Atoms, Idea Threads, action cards, MVP/Strategy Reviewer/feedback
projections, and related DTOs. PI search applies filters first, then ranks with
deterministic scoring plus transient SQLite FTS5. There is no raw Telegram
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
| `LLM_MODEL_FEEDBACK_INTAKE_STRATEGIST` | Optional override for Opus-class feedback interpretation; defaults to `claude-opus-4-8` |
| `OPENAI_API_KEY` | Optional OpenAI audio transcription key for Telegram voice input |
| `VOICE_TRANSCRIPTION_MODEL` | Optional transcription model override; defaults to `whisper-1` |
| `TELEGRAM_VOICE_MEDIA_DIR` | Optional temporary directory for downloaded Telegram voice files |
| `REMINDER_TIMEZONE` | Optional local timezone for daily operator reminders; defaults to `Asia/Tbilisi` |
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
- [docs/intelligence_report_v2_audit.md](docs/intelligence_report_v2_audit.md) — W29 current-state audit
- [docs/intelligence_report_v2_roadmap.md](docs/intelligence_report_v2_roadmap.md) — active IRX-0..IRX-14 queue
- [docs/intelligence_report_v2_contract.md](docs/intelligence_report_v2_contract.md) — Brief V2, Atlas V2, and Audit Explorer product contract
- [docs/weekly_run_manifest.md](docs/weekly_run_manifest.md) — completed-period and same-run artifact contract
- [docs/reaction_personalization_contract.md](docs/reaction_personalization_contract.md) — reaction influence and effect receipt contract
- [docs/static_visualization_system.md](docs/static_visualization_system.md) — offline visualization component contract
- [docs/portfolio_grade_intelligence_roadmap.md](docs/portfolio_grade_intelligence_roadmap.md) — canonical product, architecture, evaluation, and portfolio roadmap
- [docs/tasks.md](docs/tasks.md) — compact active IRX backlog and historical PGI record
- [docs/intelligence_evaluation_framework.md](docs/intelligence_evaluation_framework.md) — evaluation layers and weekly scorecard
- [docs/portfolio_evidence_plan.md](docs/portfolio_evidence_plan.md) — portfolio readiness gate and evidence plan
- [docs/mvp_radar_integration_contract.md](docs/mvp_radar_integration_contract.md) — cross-repo Radar contract
- [docs/operator_ai_systems_learning_roadmap.md](docs/operator_ai_systems_learning_roadmap.md) — AI Systems learning roadmap tied to implementation tasks
- [docs/report_quality_roadmap.md](docs/report_quality_roadmap.md) — historical report-quality, artifact feedback, internal cost guardrail, and Demand-to-MVP Radar handoff tasks
- [docs/ai_knowledge_intelligence_roadmap.md](docs/ai_knowledge_intelligence_roadmap.md) — component/historical AI Knowledge Intelligence roadmap
- [docs/ai_intelligence_workbook_roadmap.md](docs/ai_intelligence_workbook_roadmap.md) — historical KIR-Q0..KIR-Q13 workbook, feedback, Radar contract, Strategy Reviewer, and Obsidian projection roadmap
- [docs/hermes_pi_assistant_roadmap.md](docs/hermes_pi_assistant_roadmap.md) — Hermes/PI component roadmap and implementation record
- [docs/dogfood_4_week_plan.md](docs/dogfood_4_week_plan.md) — supporting dogfood protocol
- [docs/release_notes.md](docs/release_notes.md) — operator-facing release notes for shipped changes
- [docs/operator_workflow.md](docs/operator_workflow.md) — weekly operating workflow
- [docs/architecture.md](docs/architecture.md) — current system shape
- [docs/spec.md](docs/spec.md) — implementation-facing system specification
- [docs/report_format.md](docs/report_format.md) — weekly artifact contract
- [docs/mvp_weekly_radar.md](docs/mvp_weekly_radar.md) — MVP Radar bridge, market-context sidecar, evidence gates, and credentials
- [docs/mvp_skill_research_sources.md](docs/mvp_skill_research_sources.md) — installed auxiliary research skills for gate-safe MVP source discovery
- [docs/research_brief_receipt.md](docs/research_brief_receipt.md) — Research Brief receipt audit contract with implemented SQLite schema/storage helpers, generation-time receipt creation, delivery ref updates, deterministic verification checks, CLI inspection, operator review, and optional operator-only audit notes
- [docs/telegram_channel_intelligence.md](docs/telegram_channel_intelligence.md) — Channel Intelligence design, implemented schema migrations, deterministic repeated-claim extraction, source-observation refresh, active-project links, narrative candidates, inspection CLI, and optional Markdown report surface
- [docs/memory_architecture.md](docs/memory_architecture.md) — memory model
- [docs/memory_inspection.md](docs/memory_inspection.md) — memory debugging commands

Historical material lives under [docs/archive/](docs/archive/README.md).

## Development State

The AI Knowledge Intelligence path has substantial local plumbing: raw posts can
be atomized, atoms can be grouped into temporal threads, a frontier analysis can
be persisted, report HTML/JSON can be generated, feedback can be confirmed into
memory, Strategy Reviewer can produce advisory improvement tasks, bounded
Obsidian notes can be regenerated, and Hermes/PI can read curated intelligence
through read-only interfaces.

The honest limitation is not missing plumbing; it is portfolio-grade
correctness, personalization, dogfood proof, and presentation. Project and
learning projections remain conservative evidence leads, not full
project-priority or mastery claims. User value is not proven until the dogfood
protocol produces real feedback, actions, decisions changed, experiments,
learning outcomes, friction scores, scorecards, and false-confidence review.
