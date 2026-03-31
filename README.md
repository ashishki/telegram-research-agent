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
- a taste-aware ranking layer driven by your explicit profile
- a project-aware relevance engine with keyword precision and suppression
- a weekly review artifact generator (Telegraph article or HTML file)
- a cost-aware, explainable AI workflow with feedback capture

---

## What the System Does

### Weekly pipeline (automated, Monday morning)

1. **Ingests** new Telegram posts from configured channels via Telethon (MTProto)
2. **Preprocesses** — normalizes text, extracts structure (code, links, word count), assigns TF-IDF topic clusters
3. **Scores** every post with a deterministic 5-dimension formula — no LLM
4. **Routes** posts to model tiers: Haiku (noise/cultural), Sonnet (watch), Opus (strong/synthesis)
5. **Formats** a 9-section weekly review with source links, delta vs last week, and project relevance
6. **Renders** the review as an HTML document
7. **Publishes** to Telegraph (with fallback to HTML file attachment)
8. **Delivers** to Telegram: short notification (≤300 chars) + article URL or file

### What you receive

**Telegram notification (short):**
> Research Review 2026-W13: 7 strong signals, 23 watch. Analyzing FastAPI 0.112 release for potential impact on gdev-agent service layer.
> https://telegra.ph/Research-Review-2026-W13

**Full review (10–15 min read):**

| Section | Content |
|---|---|
| Strong Signals | Up to 5 strong signals with score, model tier, and source link |
| Decisions to Consider | Explicit action items from strong signals (≤3) |
| Watch | Pending signals worth tracking, not urgent |
| Cultural | Low-signal items that carry contextual value |
| Ignored | Noise count by topic — confirms nothing important was missed |
| Think Layer | Theme synthesis |
| Stats | Bucket counts, avg score |
| What Changed | Delta vs previous week's bucket distribution |
| Project Action Queue | Per-project relevant signals with matched keywords |
| Learn | Topics recurring in strong/watch not yet in any project focus |

---

## Core Design Decision

**Deterministic scoring before any LLM call.**

Every post receives a `signal_score` computed entirely without LLMs, from five weighted dimensions:

```
signal_score = personal_interest×0.30 + source_quality×0.20 + technical_depth×0.20 + novelty×0.15 + actionability×0.15
```

This score determines which model tier (if any) processes the post. The majority of posts never reach an LLM.

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
```

Analyze your feedback to get boost topic suggestions:
```bash
python3 src/main.py tune-suggestions
```
Output: topics appearing ≥2 times in acted-on signals but absent from your `profile.yaml` boost list.
Feedback is stored in `signal_feedback` table. `profile.yaml` is never auto-modified — you apply suggestions manually.

---

## Delivery

The weekly review is published as a **Telegraph article** (primary) or attached as an **HTML file** (fallback).

Set `TELEGRAPH_TOKEN` env var to reuse an existing Telegraph access token. If not set, a new anonymous account is created on each publish.

```bash
export TELEGRAPH_TOKEN=your_token_here
```

---

## Operator Commands

```bash
python3 src/main.py health-check      # DB connectivity, config status, last run timestamps, stuck queues
python3 src/main.py score-stats       # bucket distribution + trend vs previous week
python3 src/main.py cost-stats        # LLM cost breakdown by model + 4-week weekly trend
python3 src/main.py report-preview    # preview current signal report from scored posts
python3 src/main.py tune-suggestions  # boost topic suggestions from acted-on feedback
```

Full operator guide: `docs/operator_workflow.md`

---

## Development Status

Roadmap v3 complete (Phases 1v3–5v3, tasks T65–T79+). 106 tests. CI on every push.

System capabilities summary:
- deterministic scoring pipeline with actual cluster coherence (silhouette_score from cluster_runs)
- three-tier model routing with full cost logging
- 9-section weekly review artifact with source traceability
- HTML render + Telegraph publish (fallback: file attachment)
- project relevance with explicit keyword lists and exclusion suppression
- feedback capture (`/mark_useful`, `/mark_skipped`) + `tune-suggestions` CLI
- observability: cost trends, score distribution trends, enriched health-check

---

## Documentation

| File | Role |
|---|---|
| `docs/architecture.md` | Component map, layer contracts, data model |
| `docs/spec.md` | Technical decisions, runtime environment, data schema |
| `docs/tasks.md` | Phased development roadmap |
| `docs/report_format.md` | Weekly artifact structure and delivery spec |
| `docs/operator_workflow.md` | Week-to-week operating guide, tuning reference |
| `docs/IMPLEMENTATION_CONTRACT.md` | Rules for codex/implementer |
| `src/config/profile.yaml` | Personal taste configuration |
| `src/config/projects.yaml` | Active project definitions with keywords |
| `src/config/scoring.yaml` | Scoring weights and thresholds |
