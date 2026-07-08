# Operator Workflow

**Version:** 2.0
**Audience:** System owner (single user, personal use)

---

## Weekly Routine

The system runs automatically via systemd timers. The owner's weekly interaction is minimal by design.

### Monday Morning — Pipeline Runs

Schedule:
- ingestion: Monday 07:00 `Asia/Tbilisi`
- weekly delivery: Monday 09:00 `Asia/Tbilisi`
- MVP of the Week delivery: Monday 09:20 `Asia/Tbilisi`

The systemd timer triggers the full pipeline:
1. Incremental ingestion (new posts since last run)
2. Normalization and preprocessing
3. Scoring (`score_posts`)
4. Digest generation and reader-facing signal report formatting
5. Delivery: Telegram notifications + full artifacts
6. Opportunity seed export to Demand-to-MVP Radar and `MVP of the Week` delivery

Owner receives:
- Telegram message: short `Research Brief` notification + Telegraph link
- Telegram message: short `Implementation Ideas` notification + Telegraph link
- Telegram message: short `MVP of the Week` notification + Telegraph link + source-mix summary
- Telegram document: copyable `MVP of the Week` Markdown fallback with one candidate, evidence, missing evidence, risks, and next experiment
- When run on demand, Telegram document: `AI Decision Intelligence` HTML report with a first-screen decision brief, actions, conservative project implications, trend board, source links, and an embedded Archify knowledge-flow diagram

Expected time to read: 10–15 minutes.

### AI Knowledge Intelligence Run

The current AI Knowledge layer is an on-demand pipeline over the raw Telegram
archive. Use it when you want the richer 12-week view: what ideas changed,
which actions matter now, how current signals connect to the long-running
knowledge base, and what should be browsed later in Obsidian.

```bash
python3 src/main.py knowledge-extract --weeks 12 --model cheap
python3 src/main.py idea-threads --weeks 12
python3 src/main.py frontier-analysis --week 2026-W28 --lookback-weeks 12 --model strong
python3 src/main.py ai-visual-report --week 2026-W28 --skip-refresh --threads-limit 12 --atoms-limit 8
python3 src/main.py obsidian-export --week 2026-W28
```

Add `--deliver` to `ai-visual-report` to send the HTML file to the configured
Telegram owner chat/channel. The report is allowed to show zero project leads:
that means the evidence was not specific enough after broad terms like `AI`,
`workflow`, and `evidence` were filtered out. Treat this as honest uncertainty,
not as a pipeline failure.

### Weekly Intelligence Workbook Routine

The new target artifact is the Weekly AI Intelligence Workbook: a concise
first-screen decision brief plus deeper study, evidence, implementation, MVP
Radar, and feedback sections. Treat Telegram as delivery/feedback, not as the
main reading surface.

Monday:

- open the workbook HTML;
- read Decision Brief first;
- scan Strong Signals;
- inspect Project Implementation and MVP Radar sections;
- choose the week's read/try/build targets.

During the week:

- read 3-5 selected source items;
- run 1-2 try items;
- complete one experiment, project PR, or backlog item when the evidence
  supports it;
- react to original Telegram posts that caught your interest; any visible
  personal reaction should mean "interesting", not a specific emoji taxonomy.

End of week:

- send text or voice feedback to the bot after reading or trying items;
- confirm the parsed feedback before it affects memory;
- review Strategy Reviewer suggestions;
- decide which Codex-ready tasks to run next;
- approve code/config/prompt/profile changes manually, never implicitly through
  voice feedback.

Suggested voice feedback prompt:

```text
Что было полезно? Что было мимо? Что попробовал? Что применил к проекту? Что нужно изменить в следующем отчете?
```

Voice input requires `OPENAI_API_KEY` on the bot host. When configured, the
bot downloads the Telegram voice `.ogg` file to temporary storage, transcribes
it with the OpenAI audio transcription endpoint (`VOICE_TRANSCRIPTION_MODEL`,
default `whisper-1`), routes the transcript through Hermes intent
classification, and deletes the local audio file. The transcript may become a
chat question, a feedback draft, or a reminder. Feedback drafts still require
confirmation. If transcription is not configured or fails, send the same text
manually:

```text
/feedback_voice Что было полезно... Что было мимо... Что применил...
```

The confirmation rule is unchanged: the bot only drafts feedback first; memory
changes happen after `/feedback_confirm <id>`.
Feedback interpretation uses the `feedback_intake_strategist` LLM category
(`claude-opus-4-8` by default, override with
`LLM_MODEL_FEEDBACK_INTAKE_STRATEGIST`) to separate proposed memory events,
report changes, Codex task drafts, clarifying questions, and risk notes. If the
model is unavailable, Hermes falls back to deterministic parsing and still
requires confirmation.

Daily reminders are local operator prompts in `Asia/Tbilisi`, not a 30-minute
notification loop. Create one with text or voice, or explicitly:

```text
/remind завтра 18:00 дать feedback по Workbook
/reminders
```

`telegram-reminders.timer` sends one daily `Asia/Tbilisi` check-in with `сделал` /
`не сделал` buttons. Button clicks record the reminder outcome in SQLite; they
do not change report scoring or code/config.

### Hermes / PI Assistant Dogfood Routine

Hermes is the Telegram-facing concierge for the workbook workflow. It is a
bounded LLM chat and command router, not a source of truth. The Weekly AI
Intelligence Workbook remains the main reading artifact, and PI Assistant
answers source-grounded questions by calling read-only tools over curated
intelligence objects.

Hermes commands and chat:

- `/weekly` - current workbook status and three main conclusions;
- `/actions` - one to three actions for the week;
- `/explain` - explain a selected signal or ask what to explain;
- plain text, `/chat`, `/hermes`, or `/ask` - bounded LLM chat that can choose
  read-only PI tools from context;
- `/remind` / `/reminders` - local daily reminder check-in workflow;
- `/projects` - project actions and watch items;
- `/mvp` - MVP Radar candidate status, source mix, missing evidence, and why
  build/focused_experiment is or is not allowed;
- `/feedback` - text or voice feedback intake;
- `/strategy` - Strategy Reviewer suggestions;
- `/codex` - prepared Codex task suggestions for manual approval.

Dogfood Monday flow:

1. Generate or locate the current workbook.
2. Ask Hermes for `/weekly`.
3. Read Decision Brief, two Deep Explanation cards, Project Actions, and MVP
   Radar.
4. Pick one read/try/project/MVP validation/reject-defer action.

During-week flow:

1. Ask plain-language questions directly in the bot, or use `/explain` for
   narrower workbook signals.
2. Use `/projects` when choosing project work.
3. Use `/mvp` before treating any candidate as a build opportunity.
4. React to original Telegram posts that were interesting for any reason.

End-week flow:

1. Send voice feedback through `/feedback`.
2. Review Hermes parsed summary.
3. Confirm only the memory writes that are correct.
4. Review `/strategy`.
5. Optionally run one `/codex` task if it has clear acceptance criteria and
   verification commands.

Voice feedback confirmation rule:

- Hermes may show what will be written to memory;
- Hermes may show config/code/Codex suggestions;
- only confirmed feedback becomes memory;
- config/code changes require manual approval and a separate Codex task;
- no reaction still means unknown, not negative.

Codex task selection rule:

- run at most one optional Codex task per week during dogfood;
- prefer fixes that improve feedback/action usefulness, evidence clarity, or
  workflow friction;
- defer visual polish, multi-profile Hermes, vector retrieval, and extra
  gateways until the four-week review;
- never run a task that weakens evidence gates, makes Radar build from
  Telegram-only evidence, or turns Hermes into source of truth.

Track the weekly dogfood metrics from `docs/dogfood_4_week_plan.md`, especially
time to understand the week, confirmed feedback count, completed real actions,
decisions changed, value score, and friction score.

### Production Readiness Checklist

Before starting dogfood on the VPS, verify the running baseline:

```bash
systemctl is-active telegram-bot.service telegram-ingest.timer telegram-digest.timer telegram-mvp-weekly.timer telegram-cleanup.timer telegram-reminders.timer
systemctl list-timers 'telegram-*' --all --no-pager
bash scripts/healthcheck.sh
PYTHONPATH=src python3 src/main.py score-stats
PYTHONPATH=src python3 src/main.py ops-validate
```

Expected interpretation:

- `telegram-bot.service` should be `active`; it powers Hermes command polling.
- The weekly timers should be `active`; they are the production schedule.
- `healthcheck.sh` should end with `Healthcheck OK`.
- `ops-validate` may return `needs_live_event` until a real Telegram reaction
  or inline callback is observed in production.

Hermes readiness means the command concierge, bounded LLM chat, voice router,
and daily reminder check-in are live:
plain text, `/chat`, `/hermes`, `/ask`, `/weekly`, `/actions`, `/explain`,
`/projects`, `/mvp`, `/strategy`, `/remind`, `/reminders`, and `/codex`.
`/codex` prepares prompt text for manual approval and never executes Codex.

RAG readiness is intentionally limited. The assistant layer reads deterministic
curated retrieval items from workbook/claim/atom/thread/action/MVP/feedback
and Strategy Reviewer projections. It does not run raw Telegram firehose RAG,
does not use vector search, and does not expose raw SQLite sessions.

Next implementation queue before deeper dogfood:

- add a bounded market/business channel pack for MVP Radar from
  `its_capitan`, `exitsexist`, `leadgenvalley`, `cryptoEssay`, and
  `huntermikevolkov`;
- split the HTML surface into a cumulative Knowledge Atlas and a short Weekly
  Intelligence Brief;
- evaluate curated-only semantic RAG using Dream Motif retrieval patterns as
  reference. Obsidian remains a generated human navigation/audit projection,
  not runtime assistant memory.

Implemented HPI-11 cleanup: plain Telegram messages are sent without MarkdownV2
backslash artifacts when `parse_mode=None`; `/help` now starts with "just write
or send voice"; reminders parse, display, and run in `Asia/Tbilisi`.
Implemented HPI-12 feedback strategist: text and voice feedback drafts use an
Opus-class interpretation path with deterministic fallback; memory writes
remain gated by `/feedback_confirm`.

Reaction readiness requires a live operator event. Put any personal reaction on
a recent original channel post, then run:

```bash
PYTHONPATH=src python3 src/main.py sync-reactions --days 14 --limit 30
PYTHONPATH=src python3 src/main.py ops-validate
```

The rule remains: any visible personal reaction means interesting; no reaction
means unknown, not negative.

### Reader-Facing Quality Contract

The weekly package should behave like a decision brief, not a raw digest.

The first screen should answer:

- what was evaluated;
- what changed versus the previous week;
- what should be applied, investigated, deferred, or rejected;
- why the evidence is believable;
- where the source mix is weak.

If the report instead starts with a long topic list, exposes internal matching
traces such as `Matches: claude, git`, or contradicts another artifact, treat it
as a report-quality bug and record artifact feedback.

Active AI-development tasks for this quality layer live in
`docs/report_quality_roadmap.md`.

`Implementation Ideas` should be treated as a triaged surface:
- `Built Ideas` are the stronger synthesized moves: they can combine several Telegram signals, project context, and recurring patterns into one clearer recommendation
- `Fresh Signals` are separate new ideas worth seeing even if they have not matured into a larger thesis yet
- `do now` ideas are candidate implementation moves for the current working horizon
- `backlog` ideas are useful but not urgent
- `reject/defer` ideas should be remembered and suppressed from repeating unchanged
- the list should stay sparse: prefer 1-2 strong project improvements and at most 1 new build idea
- if the week is weak, fewer ideas is the correct outcome

---

### After Reading — Tag What Actually Mattered

Mark posts directly from Telegram with either a numeric `post_id` or a full Telegram link:

```text
/mark_strong https://t.me/channel/123
/mark_try https://t.me/channel/456
/mark_interesting https://t.me/channel/789
/mark_low https://t.me/channel/111
/tag https://t.me/channel/222 funny
```

These tags are used to:
- override explicitly rated posts
- shift learned channel/source bias over time
- update dynamic per-channel preference with time decay, so recent signals matter more than old ones
- guide the weekly preference judge
- influence project insights and the next study plan

The system also maintains:
- `channel_memory` derived from your tag history, including a dynamic `channel_score`
- `project_context_snapshots` derived from GitHub sync, recent commit deltas, linked signals, and recent project-scoped decisions

That lets the brief explain more directly in the article and reduces the need to open the original Telegram post.

---

### On-Demand Commands

```bash
# Verify system health — DB, config, last run timestamps, unscored post count
# Also prints project-link counters and non-curated active project rows.
python3 src/main.py health-check

# Inspect score distribution from last run (+ trend vs previous week)
python3 src/main.py score-stats

# Check LLM cost from last run (+ 4-week weekly trend)
python3 src/main.py cost-stats

# Dry-run the weekly MVP artifact without Telegram delivery
python3 src/main.py mvp-weekly --no-deliver

# Export only the Radar input contract
python3 src/main.py export-opportunity-seeds --days 7 --limit 80

# Preview scored posts without re-running the full pipeline
# Note: this is a legacy operator preview, not an exact copy of the delivered Telegraph brief
python3 src/main.py report-preview

# Generate or refresh the current study plan
python3 src/main.py study
python3 src/main.py study --force

# Send the weekly study reminder once
python3 src/main.py study --remind

# Get boost topic suggestions based on acted-on feedback
python3 src/main.py tune-suggestions

# Inspect insight triage summary — counts by category, recent records, rejection memory
python3 src/main.py insight-triage-stats

# Monthly operator report — feedback, inline decisions, costs, receipt health, editorial memory
python3 src/main.py operator-report --month 2026-05

# Source down-rank reasons from observed local behavior
python3 src/main.py memory explain-source-downrank --days 30 --limit 10

# Build a local weekly editorial memory sidecar from operator/system telemetry
python3 src/main.py memory inspect-editorial-memory --week 2026-W22

# Product split gate for Telegram Channel Intelligence
python3 src/main.py product-split-gate

# Production validation evidence for Telegram reactions and inline callbacks
python3 src/main.py ops-validate all --days 14

# Debug why digest topics did not become project-linked Telegram signals
python3 src/main.py memory diagnose-project-signals --week 2026-W20

# Refresh the AI Knowledge Intelligence layer over 12 weeks
python3 src/main.py knowledge-extract --weeks 12 --model cheap
python3 src/main.py idea-threads --weeks 12
python3 src/main.py frontier-analysis --week 2026-W28 --lookback-weeks 12 --model strong

# Generate the stakeholder-facing HTML report and optional Obsidian projection
python3 src/main.py ai-visual-report --week 2026-W28 --skip-refresh
python3 src/main.py ai-visual-report --week 2026-W28 --skip-refresh --deliver
python3 src/main.py obsidian-export --week 2026-W28
```

`mvp-weekly` is not Telegram-only idea generation. It exports Telegram seeds to
Demand-to-MVP Radar, then Radar collects the configured external demand bundle
before synthesis. The delivered notification includes a `Source mix` line so a
weak external run is visible immediately.

Radar output should be read as a candidate dossier unless the source gate is
clearly passed. A Telegram seed plus weak external evidence is an
`investigate` result, not a build-ready product decision.

### Weekly Brief Usefulness Log

After reading the Research Brief, record what was actually useful:

```bash
python3 src/main.py log-usefulness \
  --week 2026-W22 \
  --useful-section "Project Relevance" \
  --not-useful-section "Study Plan" \
  --decision "Prioritized callback validation" \
  --weak-evidence "Recommendation lacked source links" \
  --trust-up "@source_a" \
  --trust-down "@source_b" \
  --notes "Brief was useful but evidence citations need work"
```

All list fields can be repeated. The command writes append-only operator-authored
state to `weekly_usefulness_logs` in the configured `AGENT_DB_PATH` database and
prints the inserted row id plus per-field counts. It does not mutate
`profile.yaml`, `channels.yaml`, project config, channel scores, or future brief
generation logic yet.

### Artifact Feedback

Record feedback for a specific artifact section, item, or evidence group when a
whole-week usefulness log is too broad:

```bash
python3 src/main.py log-artifact-feedback \
  --week 2026-W22 \
  --artifact-type research_brief \
  --artifact-path data/output/digests/2026-W22.md \
  --section "Evidence" \
  --item-ref "claim-7" \
  --feedback weak \
  --evidence-id 101 \
  --notes "Source was too thin"
```

Inspect stored artifact feedback:

```bash
python3 src/main.py memory inspect-artifact-feedback --week 2026-W22
```

This remains operator-authored local state. It does not become model-authored
source trust by itself.

Build the weekly editorial memory sidecar after logging feedback or reviewing
quality findings:

```bash
python3 src/main.py memory inspect-editorial-memory --week 2026-W22
```

The command writes `data/output/editorial_memory/2026-W22.md` with
operator/system-authored keep/change/demote/test-next-week notes from artifact
feedback, weekly usefulness logs, report-quality findings, receipt warnings,
and source down-rank explanations. Future report-generation prompts should read
this only when explicitly wired to do so.

Prefer using Telegram artifact feedback buttons for low-friction feedback. Use
`log-artifact-feedback` for specific failures that need more context, such as:

- unclear first screen;
- useful decision;
- noisy source;
- weak evidence;
- Radar source gate contradiction;
- Study Plan contradicting the Research Brief.

### Inline Feedback (from Telegram)

While reading the weekly brief:
```text
/mark_useful <post_id|link>   -> records acted_on feedback
/mark_skipped <post_id|link>  -> records skipped feedback
/study                        -> show the current weekly study plan
/study refresh                -> rebuild this week's study plan
/study_done [notes]           -> mark this week's plan as completed
```

For lower-friction source-post feedback, react to the original Telegram channel post and run:

```bash
python3 src/main.py sync-reactions --days 14
```

The weekly `ingest` command also runs this sync unless `--skip-reactions` is passed.

Reaction feedback rule:
- any visible personal reaction on a Telegram source post records
  `operator_marked_interesting`;
- the raw emoji is kept for audit;
- no reaction means unknown, not negative;
- aggregate channel reaction counts are never treated as personal feedback.

The study plan now has a weekly completion loop:
1. The system sends one reminder per week
2. You complete the plan and mark it with `/study_done`
3. Completed study history is fed into future study plans and recommendations

Implementation Ideas are also sent as compact Telegram feedback cards after the Telegraph link.
Use the inline buttons to record the decision without typing commands:
- `✅ сделал` -> `acted_on`
- `🕒 позже` -> `deferred`
- `⛔ отказал` -> `rejected`
- `🧠 интересно` -> `deferred` with an "interesting" note

---

## Monthly Review

Once a month, review:

1. **Scoring distribution trends** — is strong bucket growing? Check `quality_metrics` table or `score-stats`; `score-stats` also shows recent empty/low-signal Research Brief receipt alerts.
   - If strong > 15% of total: raise `strong.min_score` in `scoring.yaml` (currently 0.75)
   - If strong is consistently 0–1 items: lower threshold or expand boost topics

2. **Cost per run** — check `cost-stats`.
   - The output now shows actual `cost_usd`, estimated cost, weekly trend, weekly category breakdown, and guardrail status
   - Configure guardrails with `LLM_WEEKLY_COST_BUDGET_USD` and `LLM_WEEKLY_COST_SPIKE_RATIO`
   - `preference_judge` is expected to be one of the higher-cost categories because it writes the reader-facing brief

3. **Profile.yaml freshness** — are boost topics still reflecting current focus?
   - Stale interests produce phantom relevance
   - Remove topics you no longer care about

4. **Projects.yaml** — add new active projects, archive completed ones; `health-check` warns when `projects.yaml` has not changed in over 31 days
   - Dead projects generate false positives in Project Relevance section

5. **Implementation Ideas quality** — review whether weekly ideas are operationally useful or drifting into speculative abstractions
   - The target shape is small and strong: usually 2 project improvements, sometimes 1 extra build idea, never filler
   - If too many ideas feel like premature SDK/product extraction, they should move to backlog or reject/defer memory
   - Repeated weak ideas should not resurface every week without new evidence

---

## Three Signal Value Layers

Every post is evaluated on three independent axes:

| Layer | Question | Config |
|---|---|---|
| **Global signal strength** | Is this objectively useful/novel content? | `scoring.yaml` weights, `channels.yaml` priority |
| **Personal taste relevance** | Does this align with my current focus? | `profile.yaml` boost/downrank topics |
| **Project relevance** | Does this affect what I am building? | `projects.yaml` name + focus |

A post can score high on one layer and low on others:
- High global signal, low taste relevance: may stay out of the main brief
- High taste relevance, low global signal: may still surface through `user_adjusted_score` or explicit manual tags
- High project relevance: can surface in Project Insights even if not globally strong

All three scores are stored (`signal_score`, `user_adjusted_score`, `project_relevance_score`), but only reader-appropriate text is shown in the final brief.

---

## Tuning Without Retraining

The system has no ML model to retrain. Tuning is explicit and auditable:

| Problem | Solution | File |
|---|---|---|
| Too much noise in strong | Raise `strong.min_score` | `scoring.yaml` |
| Missing relevant posts | Add topics to `boost_topics` | `profile.yaml` |
| Wrong source getting boosted | Change channel priority | `channels.yaml` |
| Wrong source repeatedly rated well/badly | Tag more posts from that source and let channel bias + channel_score adapt | Telegram bot + `user_post_tags` |
| Topic showing up despite downrank | Check if topic label matches exactly | `profile.yaml` |
| Project relevance too broad | Make `focus` field more specific | `projects.yaml` |
| Project relevance too narrow | Add more keyword variants to `focus` | `projects.yaml` |
| Week-old topics recycled | Adjust novelty weights | `scoring.yaml` |

The scoring engine re-reads YAML config on every run. Changes apply without restarting any service.

---

## Feedback Loop

The system captures lightweight feedback and explicit tags without automatic profile-file edits.

**How it works:**
1. You read the weekly `Research Brief` and `Implementation Ideas` (Telegraph articles, or HTML file for the research brief fallback)
2. Record brief-level usefulness with `log-usefulness` when the artifact affected decisions or exposed weak evidence
3. Tag or mark signals directly from Telegram
4. The next scoring run updates explicit overrides, channel/source bias, and a time-decayed `channel_score`
5. The weekly preference judge uses signal-level examples to reshape the final brief
6. `tune-suggestions` can still surface profile topic candidates, but manual tags are now the primary signal

**Design constraint:** `profile.yaml` is never auto-modified. The feedback loop surfaces suggestions only. You control your taste profile explicitly.

**Current limitations:**
- Preference bias is source-aware, but not yet a full ML ranking model
- Study completion is tracked at the weekly-plan level, not per individual block
- Project relevance still depends on good project context and evidence quality; low-signal weeks should produce fewer ideas, not forced ones

## Project Context Maintenance

Project context is not just a static `projects.yaml` description anymore.

Current state is built from:
- `projects.yaml` baseline description and focus
- `projects.yaml` as the curated active-project registry for scoped outputs
- GitHub metadata from sync (`github_repo`, `last_commit_at`)
- recent commit messages folded into `project_context_snapshots`
- Telegram relevance already linked in the DB
- recent project-scoped decisions from `decision_journal` (implemented, deferred, rejected)

This lets study planning, recommendations, and project insights reason from recent project changes instead of from keywords alone. In practice, project context is now refreshed from the current database state even when GitHub metadata itself did not change.

---

## Initial Setup Checklist

- [ ] Set `AGENT_DB_PATH`, `LLM_API_KEY` in environment
- [ ] Set `TELEGRAPH_TOKEN` if you want a stable Telegraph account instead of anonymous per-publish accounts
- [ ] Set `ARCHIFY_ROOT` if you want `ai-visual-report` to use an installed Archify renderer instead of the deterministic fallback diagram
- [ ] Fill `src/config/channels.yaml` — your curated channel list with priorities
- [ ] Fill `src/config/profile.yaml` — your boost/downrank topics
- [ ] Fill `src/config/projects.yaml` — your active projects with focus keywords
- [ ] Ensure the service user can write to `data/output/reviews`, `data/output/recommendations`, and `data/output/study_plans`
- [ ] Ensure `Demand-to-MVP-Radar` is present beside this repo, has a local `.venv`, and is writable at `data/` and `reports/`
- [ ] Ensure `Demand-to-MVP-Radar/config/mvp_weekly_sources.json` reflects the source surfaces Radar should collect before the weekly MVP synthesis
- [ ] Create `/etc/demand-mvp-radar.env` from `Demand-to-MVP-Radar/config/live_sources.env.example` when external source credentials are available
- [ ] Add at least `SERPAPI_API_KEY`, `YOUTUBE_API_KEY`, `PRODUCT_HUNT_TOKEN`, and Reddit credentials for the full broad-source weekly run; `GITHUB_TOKEN` and `STACK_EXCHANGE_KEY` improve quota but are optional
- [ ] Set `DMR_LLM_PROVIDER=anthropic` and `DMR_LLM_MODEL_MVP_WEEKLY=claude-opus-4-7` for the weekly MVP report if LLM synthesis should run
- [ ] Confirm `systemd/telegram-mvp-weekly.service` loads both `/srv/openclaw-you/.env` and optional `/etc/demand-mvp-radar.env`
- [ ] Run `python3 src/main.py health-check` — verify DB and config presence
- [ ] Run bootstrap ingestion for initial data
- [ ] Run `python3 src/main.py score-stats` — verify scoring produces expected distribution
- [ ] Run first digest — review output quality before enabling the timer
- [ ] Run `python3 src/main.py mvp-weekly --no-deliver` — verify Radar artifact quality before enabling `telegram-mvp-weekly.timer`

For the complete MVP Radar bridge contract, see `docs/mvp_weekly_radar.md`.
