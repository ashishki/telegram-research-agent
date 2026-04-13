# Telegram Research Agent

A personal research intelligence system for signal filtering, project-aware relevance, and weekly decision support.

---

## What This Is

A private, production-ready pipeline that runs on a personal VPS and processes Telegram channels you follow. Its job is to separate signal from noise and deliver a weekly review artifact that actually supports decisions — not just a summary of what was posted.

**This is not:**
- a digest bot that summarizes channels
- a generic LLM wrapper
- a multi-user or SaaS product

**This is:**
- a personal signal filtering and scoring pipeline
- a taste-aware ranking layer driven by your explicit profile and manual post ratings
- a project-aware relevance engine that uses both deterministic scoring and LLM preference judging
- a verbatim evidence layer (`signal_evidence_items`) that preserves why each signal mattered and links it to project + week scope
- a unified decision-continuity log (`decision_journal`) covering signal feedback, insight triage, and study-plan completion
- an insight triage workflow that separates do-now ideas from backlog and reject/defer noise, with repeated-idea suppression
- persistent channel memory and project context snapshots refreshed from GitHub + linked signal counts
- dynamic channel scoring shaped by time-decayed manual feedback, not just static channel priority
- a weekly Telegraph brief plus a tracked study loop informed by acted-on evidence
- a cost-aware, explainable AI workflow with feedback capture and scope-first memory retrieval

## Memory Architecture

Four-phase memory unification is complete. The system now has a coherent, scope-first memory stack built on top of the existing SQLite canonical state:

- **Tier 1** — canonical operational state: `raw_posts`, `posts`, scoring, explicit tags, feedback, triage, rejection memory, artifact records
- **Tier 2** — derived snapshots: `channel_memory`, `project_context_snapshots` (refreshed from config + GitHub deltas + linked signal counts)
- **Tier 3** — verbatim evidence memory: `signal_evidence_items` — curated high-value post excerpts with provenance (source channel, Telegram link, selection reason, week label, project scope)
- **Tier 4** — decision continuity: `decision_journal` — acted-on / ignored / deferred / rejected / completed history unified across signal feedback, insight triage, and study-plan completion

Retrieval is scope-first: project → topic → time → source → status, never a global pool.

Design reference: `docs/memory_architecture.md` | Operator guide: `docs/memory_inspection.md`

---

## In Brief (for CV / interview)

I follow 40+ Telegram channels — 300–500 posts/week. Most digest tools summarize everything; this system filters first, then synthesizes selectively. The base layer is still deterministic scoring, but the final weekly brief is now shaped by manual tags and a preference-judge pass that learns what I treat as strong, useful, project-relevant, funny, or low-signal. Cost is measured per category and tracked in SQLite.

The output is not a summary. It's a structured decision-support brief with source traceability, project-specific ideas, and a weekly study plan that compounds over time. `Implementation Ideas` is intentionally sparse: it should produce only the strongest 2-3 moves, and fewer if the evidence is weak. Delivered as two Telegraph articles inside Telegram with short notifications.

Full case study: `docs/case-study.md` | Demo walkthrough: `docs/demo-walkthrough.md`

---

## What the System Does

### Weekly pipeline (automated, Monday morning, Asia/Tbilisi)

1. **Ingests** new Telegram posts from configured channels via Telethon (MTProto)
2. **Preprocesses** — normalizes text, extracts structure (code, links, word count), assigns TF-IDF topic clusters
3. **Scores** every post with a deterministic 5-dimension formula plus preference bias from manual tags and a dynamic `channel_score`
4. **Records evidence** — strong/watch posts and manually tagged posts are written to `signal_evidence_items` with source channel, Telegram link, excerpt, and selection reason
5. **Routes** posts to model tiers and a preference-judge layer for reader-facing selection; the judge sees scoped project evidence from the last 3 weeks
6. **Formats** a decision brief with source links, project insights, and study cues; when a signal has a project application, the source line shows the originating channel
7. **Triages** generated implementation ideas into do-now, backlog, and reject/defer buckets; duplicate source reuse is suppressed and the final list prefers 1-2 strong project improvements over filler
8. **Records decisions** — signal feedback (acted_on / skipped / marked_important), insight triage, and study-plan completion are all written to `decision_journal` as a unified continuity log
9. **Renders** the review as an HTML document
10. **Publishes** two Telegraph articles: `Research Brief` and `Implementation Ideas`
    Implementation Ideas are triaged into `do_now`, `backlog`, and `reject_or_defer` categories before publishing.
11. **Delivers** to Telegram: short notification (≤300 chars) + article URL, with HTML attachment fallback for the research brief if Telegraph is unavailable

### What you receive

**Telegram notifications (short):**
> Research Brief 2026-W13 is ready.
> 5 strong signals, 3 watch.
> https://telegra.ph/Research-Brief-2026-W13

> Implementation Ideas 2026-W13 is ready.
> https://telegra.ph/Implementation-Ideas-2026-W13

**Full review (10–15 min read):**

| Section | Always present | Content |
|---|---|---|
| What Matters This Week | yes | Highest-confidence signals for this user with source links |
| Things To Try | if present | Concrete ideas to apply in active projects |
| Keep In View | if present | Important but not yet urgent items |
| Funny / Cultural | if present | Context that is worth seeing but not acting on |
| Project Insights | yes | Project-specific angles generated from the weekly feed |
| Additional Signals | yes | High-confidence auto-selected items not yet manually tagged |
| What Changed | yes | Delta vs previous week |

---

## Core Design Decision

**Deterministic scoring first, then user-shaped synthesis.**

Every post receives a deterministic `signal_score` computed without LLMs, from five weighted dimensions:

```
signal_score = personal_interest×0.30 + source_quality×0.20 + technical_depth×0.20 + novelty×0.15 + actionability×0.15
```

Then the system adds:
- manual tag overrides on explicitly rated posts
- channel/source preference bias inferred from the user's historical tags
- a time-decayed `channel_score` blended into `source_quality`, so fresh feedback matters more than stale feedback
- a `user_adjusted_score` stored on each post
- a `preference_judge` LLM layer that writes the reader-facing "Why" and project angle for the weekly brief
- `channel_memory` and `project_context_snapshots` so the judge sees what each source tends to be good at and what each active project is currently doing

Project context is updated incrementally. The system does not need to reread the whole repo every time:
- GitHub sync refreshes repo metadata
- recent commit deltas are folded into `project_context_snapshots`
- weekly recommendations, project insights, and study planning use those snapshots

This is not a temporary hack. It is an intentional product decision:
- LLMs are reserved for posts that have already passed a quality gate
- cost scales with signal quality, not with volume
- scoring is reproducible and tunable without retraining

---

## Three Signal Value Layers

Every signal is evaluated on three independent axes:

| Layer | Question | Driven by |
|---|---|---|
| **Global signal strength** | Is this objectively useful/novel content? | `scoring.yaml`, `channels.yaml` |
| **Personal taste relevance** | Does this align with my current focus? | `profile.yaml` boost/downrank |
| **Project relevance** | Does this affect what I am building? | `projects.yaml` keywords + exclude_keywords |

A post can be globally important but personally irrelevant, or watch-tier globally but critical for a specific project.

---

## Model Selection

| Tier | Model | When | Approx cost |
|---|---|---|---|
| CHEAP | `claude-haiku-4-5-20251001` | noise/cultural, score < 0.45 | $0.80/$4.00 per M tokens |
| MID | `claude-sonnet-4-6` | watch, score 0.45–0.74 | $3.00/$15.00 per M tokens |
| STRONG | `claude-opus-4-6` | strong + synthesis, score ≥ 0.75 | $15.00/$75.00 per M tokens |

Override via env vars: `CHEAP_MODEL`, `MID_MODEL`, `STRONG_MODEL`.

---

## Configuration

**`src/config/profile.yaml`** — personal taste layer
```yaml
boost_topics:       # topics that raise score ×1.3
  - "AI agents"
  - "FastAPI"
downrank_topics:    # topics that lower score ×0.5
  - "crypto"
cultural_keywords:  # trigger cultural bucket regardless of score
  - "GPT-4o"
```

**`src/config/projects.yaml`** — project relevance
```yaml
projects:
  - name: my-project
    description: "What the project does"
    focus: "service layer, async FastAPI, cost control"
    keywords:           # explicit match list (preferred over focus text)
      - fastapi
      - redis
      - webhook
    exclude_keywords:   # suppress relevance even if focus matches
      - film
```

`keywords` takes precedence over `focus` text. `exclude_keywords` suppresses any match to score 0.05.

**`src/config/scoring.yaml`** — scoring weights and thresholds. Edit to rebalance dimensions.

**`src/config/channels.yaml`** — your curated channel list with priorities (`high` / `medium` / `low`).

---

## Feedback Loop

Mark signals inline from Telegram:
```
/mark_useful <post_id>    # records acted_on feedback
/mark_skipped <post_id>   # records skipped feedback
/tag <post_id|link> <strong|interesting|try|funny|low|later>
/mark_strong <post_id|link>
/mark_interesting <post_id|link>
/mark_try <post_id|link>
/mark_funny <post_id|link>
/mark_low <post_id|link>
/mark_later <post_id|link>
```

Manual tags are not just annotations. They are used to:
- override explicit post ranking where needed
- shift learned channel/source bias over time
- update per-channel memory and a dynamic `channel_score` with time decay
- seed the weekly preference judge
- shape the study plan and future recommendations

`channels.yaml` still defines the static baseline (`high` / `medium` / `low`), but it is no longer the only channel-quality signal. Recent `strong` / `try` / `interesting` / `low_signal` tags now move channel preference dynamically.

Analyze your feedback to get boost topic suggestions:
```bash
python3 src/main.py tune-suggestions
```
Output: topics appearing ≥2 times in acted-on signals but absent from your `profile.yaml` boost list.
Feedback is stored in `signal_feedback` table. `profile.yaml` is never auto-modified — you apply suggestions manually.

---

## Delivery

The weekly output is published as two **Telegraph articles** by default:
- `Research Brief`
- `Implementation Ideas`

Delivery behavior:
- `Research Brief`: Telegraph first, fallback to HTML attachment, then fallback to plain text if attachment send fails
- `Implementation Ideas`: Telegraph first, fallback to short Telegram notification if publish fails

Operational requirement: the service user must be able to write under `data/output/reviews`, `data/output/recommendations`, and `data/output/study_plans`, otherwise delivery can fail before Telegraph publish.

Set `TELEGRAPH_TOKEN` env var to reuse an existing Telegraph access token. If not set, a new anonymous account is created on each publish.

```bash
export TELEGRAPH_TOKEN=your_token_here
```

---

## Operator Commands

```bash
python3 src/main.py health-check      # DB connectivity, config status, last run timestamps, stuck queues
python3 src/main.py score-stats       # bucket distribution + trend vs previous week
python3 src/main.py cost-stats        # actual and estimated LLM cost breakdown by model/category/week
python3 src/main.py report-preview    # legacy operator preview of scored posts (not identical to the reader-facing Telegraph brief)
python3 src/main.py study             # generate the current weekly study plan
python3 src/main.py study --force     # rebuild the current weekly study plan from scratch
python3 src/main.py study --remind    # send the weekly study reminder once
python3 src/main.py tune-suggestions  # boost topic suggestions from acted-on feedback
python3 src/main.py insight-triage-stats  # triage summary: counts by category, recent records, rejection memory

# Memory inspection (scope-first, requires AGENT_DB_PATH)
python -m src.main memory inspect-evidence [--project NAME] [--week LABEL] [--kind KIND] [--limit N]
python -m src.main memory inspect-decisions [--scope SCOPE] [--status STATUS] [--project NAME] [--limit N]
python -m src.main memory inspect-snapshots [--stale-only]
python -m src.main memory inspect-suppression --title "TITLE"
```

Full operator guide: `docs/operator_workflow.md` | Memory inspection guide: `docs/memory_inspection.md`

---

## Development Status

Roadmap v3 complete (Phases 1v3–6v3) + Memory Unification complete (Phases 1–4, M1–M17). 167 tests. CI on every push.

System capabilities summary:
- deterministic scoring pipeline with actual cluster coherence (silhouette_score from cluster_runs)
- three-tier model routing with full cost logging
- 9-section weekly review artifact with source traceability and per-signal channel attribution
- HTML render + Telegraph publish (fallback: file attachment)
- project relevance with explicit keyword lists and exclusion suppression
- manual tagging (`/tag`, `/mark_strong`, `/mark_try`, etc.) plus acted_on/skipped feedback
- time-decayed channel scoring blended into source quality and exposed through `channel_memory`
- preference judge for reader-facing ranking and project-aware rationale, now seeded with scoped evidence from `signal_evidence_items`
- completion-aware weekly study plan with `/study_done`, now incorporating acted-on evidence from `decision_journal`
- incremental project context snapshots derived from GitHub sync, recent commits, and linked signal counts
- observability: cost trends, score distribution trends, enriched health-check
- insight triage layer: deterministic do_now / backlog / reject_or_defer classification with 4-week rejection memory, unique-source filtering, and a stronger preference for current-project improvements
- **Tier 3 — verbatim evidence memory**: `signal_evidence_items` records curated strong/manual-tag signals with provenance per week and project
- **Tier 4 — decision continuity**: `decision_journal` unifies all acted-on, ignored, deferred, rejected, and completed decisions in one append-only log
- **memory CLI**: `inspect-evidence`, `inspect-decisions`, `inspect-snapshots`, `inspect-suppression` subcommands for operator debugging

---

## Documentation

| File | Role |
|---|---|
| `docs/architecture.md` | Component map, layer contracts, data model |
| `docs/memory_architecture.md` | Four-tier memory design: canonical, snapshots, evidence, decisions |
| `docs/memory_inspection.md` | Operator guide for memory CLI subcommands and weekly troubleshooting |
| `docs/spec.md` | Technical decisions, runtime environment, data schema |
| `docs/tasks.md` | Phased development roadmap |
| `docs/report_format.md` | Weekly artifact structure and delivery spec |
| `docs/operator_workflow.md` | Week-to-week operating guide, tuning reference |
| `docs/IMPLEMENTATION_CONTRACT.md` | Rules for codex/implementer |
| `src/config/profile.yaml` | Personal taste configuration |
| `src/config/projects.yaml` | Active project definitions with keywords |
| `src/config/scoring.yaml` | Scoring weights and thresholds |
