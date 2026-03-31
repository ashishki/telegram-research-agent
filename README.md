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
- a project-aware relevance engine
- a weekly review artifact generator
- a cost-aware, explainable AI workflow

---

## Core Product Thesis

The strongest design decision in this system is **deterministic scoring before any LLM call**.

Every post receives a `signal_score` computed entirely without LLMs, from five weighted dimensions: personal taste alignment, source quality, technical depth, novelty, and actionability. This score determines which model tier (if any) processes the post. The majority of posts never reach an LLM.

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
| **Project relevance** | Does this affect what I am building? | `projects.yaml` focus keywords |

A post can be globally important but personally irrelevant, or watch-tier globally but critical for a specific project. The weekly review surfaces all three layers explicitly.

---

## What You Receive

After each weekly pipeline run, you get two things:

**1. Telegram notification** (short)
> 312 posts reviewed. 7 strong, 23 watch. Top signal: LLM inference optimization emerging as structural theme. 3 items relevant to gdev-agent.

**2. Full review artifact** (10–15 min read)

A structured readable document with:

| Section | Content |
|---|---|
| Executive Summary | What ran, key numbers, dominant theme |
| What Matters Now | Up to 5 strong signals with evidence and source links |
| Decisions to Consider | Explicit action items derived from strong signals |
| Project Action Queue | Per-project relevant signals and rationale |
| Watch | Pending signals worth knowing, not urgent |
| What Changed Since Last Week | Delta from previous review |
| Ignore With Confidence | Noise count by topic — confirms nothing was missed |
| Learning Edge | Topics recurring in strong/watch, not yet in any project focus |
| Source Appendix | Full traceability — every signal linked back to its origin |

Delivered as: a Telegraph article (target) or HTML file. Readable inside Telegram. Not a message blob.

Full format specification: `docs/report_format.md`

---

## How Scoring Works

```
signal_score = Σ (dimension × weight)

personal_interest  × 0.30   (topic match with profile.yaml boost/downrank)
source_quality     × 0.20   (channel priority × relative view count)
technical_depth    × 0.20   (code presence, links, word count)
novelty            × 0.15   (how new vs. last 4 weeks)
actionability      × 0.15   (implement / pattern / awareness / noise)
```

Buckets:
- `strong` ≥ 0.75 → routed to Opus (STRONG_MODEL)
- `watch` 0.45–0.74 → routed to Sonnet (MID_MODEL)
- `cultural` — triggered by `cultural_keywords`, regardless of score → Haiku
- `noise` < 0.45, no cultural keyword → filtered, no LLM

Personalization: boost topics multiply score ×1.3 (cap 1.0), downrank ×0.5. Strong posts cannot be suppressed below watch threshold.

---

## Model Selection

| Tier | Model | When | Cost (input/output per M tokens) |
|---|---|---|---|
| CHEAP | `claude-haiku-4-5-20251001` | noise/cultural, score < 0.45 | $0.80 / $4.00 |
| MID | `claude-sonnet-4-6` | watch, score 0.45–0.74 | $3.00 / $15.00 |
| STRONG | `claude-opus-4-6` | strong, synthesis, score ≥ 0.75 | $15.00 / $75.00 |

Override via env vars:
```bash
export CHEAP_MODEL=claude-haiku-4-5-20251001
export MID_MODEL=claude-sonnet-4-6
export STRONG_MODEL=claude-opus-4-6
```

**When to adjust:**
- If cost is too high: check `cost-stats`. If STRONG > 20% of calls, raise `strong.min_score` in `scoring.yaml`.
- If quality is low: strong bucket may be too permissive — raise threshold or refine boost topics.
- For testing/development: set MID_MODEL=Haiku, STRONG_MODEL=Sonnet to reduce cost.

Recommended: leave defaults. They are optimized for a typical weekly run.

---

## Configuration

**`src/config/profile.yaml`** — personal taste layer
```yaml
boost_topics:       # topics that raise score ×1.3
  - "AI agents"
  - "FastAPI"
downrank_topics:    # topics that lower score ×0.5
  - "crypto"
  - "ChatGPT tips"
downrank_sources:   # low-signal channels
  - "@SomeNoisyChannel"
```

**`src/config/projects.yaml`** — project relevance
```yaml
projects:
  - name: my-project
    description: "What the project is"
    focus: "specific keywords, technologies, patterns"
```
Specificity matters: broader focus = more false positives.

**`src/config/scoring.yaml`** — scoring weights and thresholds. Edit to rebalance dimensions.

---

## Operator Commands

```bash
python3 src/main.py health-check      # DB connectivity + config file status
python3 src/main.py score-stats       # bucket distribution from last run
python3 src/main.py cost-stats        # LLM cost breakdown by model
python3 src/main.py report-preview    # preview current signal report from DB
```

Operator workflow: `docs/operator_workflow.md`

---

## Development Status

All 8 phases of Roadmap v2 complete (T29–T64). 83 tests. CI on every push.

Active next direction: Phase 1 of the new roadmap — weekly report redesign toward the article artifact format defined in `docs/report_format.md`.

Current roadmap: `docs/tasks.md`

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
| `src/config/projects.yaml` | Active project definitions |
| `src/config/scoring.yaml` | Scoring weights and thresholds |
