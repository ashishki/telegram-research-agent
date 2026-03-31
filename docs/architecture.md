# Architecture

**Version:** 4.0
**Date:** 2026-03-31

---

## System Role

This is a personal research intelligence pipeline. It is not a digest bot, not a summarizer, not a generic AI agent.

Its role is to do one thing well: process a high-volume noisy Telegram stream and produce a compact, evidence-forward weekly review that directly supports the owner's decisions.

The system is built for single-user personal use. It is production-ready in the sense that it runs reliably on a private VPS, is fully automated, and its outputs are trustworthy enough to act on. It is not production-ready in the sense of handling multiple users, high availability, or external traffic.

---

## Core Design Decision

**Deterministic scoring before any LLM call.**

Every post is scored without LLMs, using a weighted formula across five dimensions. This score controls which model tier (if any) processes the post. Most posts never reach an LLM.

This is an intentional product decision, not a cost hack:
- LLMs are expensive and add non-determinism. They should be reserved for material that has already passed a quality gate.
- Scoring is reproducible and tunable through configuration files. No retraining, no labeled datasets.
- The system's behavior is auditable: you can trace exactly why a post was filtered or promoted.

---

## Pipeline

```text
Telegram Channels
  → Ingestion Layer          (Telethon, MTProto, raw storage, message_url)
  → Preprocessing Layer      (normalize, detect language, extract metadata)
  → Scoring Layer            (deterministic signal_score, bucket assignment, silhouette coherence)
  → Routing Layer            (select model tier: CHEAP / MID / STRONG / skip)
  → Interpretation Layer     (LLM runs only on routed subsets)
  → Project Lens             (explicit keyword lists, exclude_keywords suppression)
  → Personalization Layer    (boost/downrank adjustments, floor protection)
  → Learning Layer           (recurring topics not covered by any project)
  → Output Layer             (9-section weekly review artifact with source traceability)
  → Render Layer             (HTML generation: render_report.py)
  → Delivery Layer           (Telegraph publish → Telegram URL; fallback: HTML file)
  → Feedback Layer           (signal_feedback table, /mark_useful, /mark_skipped, tune-suggestions)

Cross-cutting:
  Observability Layer        (cost tracking + 4-week trend, routing distribution + delta, health-check)
```

---

## Three Signal Value Layers

Every signal carries three independent relevance estimates:

| Layer | Stored as | Driven by |
|---|---|---|
| Global signal strength | `signal_score` | `scoring.yaml` weights + `channels.yaml` priority |
| Personal taste relevance | boost/downrank applied to `personalized_score` | `profile.yaml` boost/downrank topics |
| Project relevance | `project_relevance_score` | `projects.yaml` keyword matching |

These three axes are independent. A post can be globally strong but personally irrelevant, or watch-tier globally but project-critical. The output layer surfaces all three explicitly.

---

## Layer Contracts

### Ingestion Layer

Retrieves raw Telegram messages via Telethon (MTProto user client).
Writes immutable records to `raw_posts`. Idempotent on `(channel_id, message_id)`.
Never modifies existing records.
Zero LLM usage.
Source: `src/ingestion/`

---

### Preprocessing Layer

Normalizes text, extracts structural metadata (has_code, url_count, word_count), detects language.
Prepares posts for scoring. Assigns topics via TF-IDF clustering.
Zero LLM usage (topic labels are cluster-derived, not LLM-generated per post).
Source: `src/processing/normalize.py`, `src/processing/cluster.py`

---

### Scoring Layer

Computes `signal_score` for each post. Fully deterministic. No LLM.

Formula:
```
signal_score = personal_interest×0.30 + source_quality×0.20 + technical_depth×0.20 + novelty×0.15 + actionability×0.15
```

Dimensions:
- `personal_interest`: topic label match against `profile.yaml` boost/downrank lists
- `source_quality`: channel priority weight × normalized view count within channel
- `technical_depth`: structural proxies — code presence, link count, word count
- `novelty`: recency of topic relative to 4-week history
- `actionability`: heuristic inference — implement / pattern / awareness / noise

Bucket assignment:
- `strong` ≥ 0.75
- `watch` 0.45–0.74
- `cultural` — triggered by `cultural_keywords` in profile.yaml, regardless of score
- `noise` — everything else

Also computes and stores: `score_breakdown` (JSON, per-dimension), `scored_at`, `score_run_id`, `routed_model`, `project_relevance_score`.

Source: `src/processing/score_posts.py`
Config: `src/config/scoring.yaml`, `src/config/profile.yaml`

---

### Routing Layer

Maps scored posts to model tiers. Called by the scoring layer (per-post) and output layer (synthesis).

```
task_type="synthesis"        → STRONG_MODEL (always)
signal_score >= 0.75         → STRONG_MODEL
signal_score 0.45–0.74       → MID_MODEL
signal_score < 0.45          → CHEAP_MODEL
signal_score = None          → CHEAP_MODEL + warning logged
```

Default models:
- `CHEAP_MODEL`: `claude-haiku-4-5-20251001`
- `MID_MODEL`: `claude-sonnet-4-6`
- `STRONG_MODEL`: `claude-opus-4-6`

Overridable via env vars. Cost estimates per call written to `llm_usage` table.

Source: `src/llm/router.py`, `src/llm/client.py`

---

### Interpretation Layer

LLM interpretation runs only on posts routed to MID or STRONG tier.
Never runs on full corpus. Budget: strong+watch bucket posts only.
Source: `src/output/generate_digest.py`, `src/output/generate_answer.py`

---

### Project Lens

Keyword-based relevance scoring between post content and active projects.
Zero LLM usage.
Threshold for inclusion in report: score ≥ 0.3.
Each match returns: `{name, score, rationale}` (rationale = matching keywords).

Uses explicit `keywords` list per project if present; falls back to tokenizing `focus` + `description`.
`exclude_keywords`: if any exclude keyword appears in post content AND there is a focus match, score is suppressed to 0.05.

Source: `src/output/project_relevance.py`
Config: `src/config/projects.yaml`

---

### Personalization Layer

Applies boost/downrank multipliers to `signal_score`:
- boost topic match: score × 1.3 (cap 1.0)
- downrank topic match: score × 0.5
- strong posts (score ≥ 0.75): personalized_score cannot fall below 0.45 (watch floor)

Strong posts are protected from suppression. Personalization modulates ranking but cannot override objective signal quality.

Source: `src/output/personalize.py`
Config: `src/config/profile.yaml`

---

### Learning Layer

Identifies recurring topics in strong/watch posts that are not covered by any project focus.
Minimum frequency threshold: 2 occurrences.
Returns up to 5 learning gap candidates.
Zero LLM usage.

Source: `src/output/learning_layer.py`

---

### Output Layer

Assembles the weekly review artifact from all upstream layers.

`format_signal_report()` produces a 9-section Markdown document:
1. Strong Signals (with source URLs, model tier, personalization tag)
2. Decisions to Consider (action items from strong signals)
3. Watch
4. Cultural
5. Ignored (noise count + top topics)
6. Think Layer
7. Stats
8. What Changed (delta vs previous quality_metrics row)
9. Project Action Queue (per-project sub-sections with matched keywords)
10. Learn (recurring topics not in any project focus)

Source: `src/output/signal_report.py`, `src/output/learning_layer.py`, `src/output/project_relevance.py`, `src/output/personalize.py`

### Render Layer

Converts `format_signal_report()` Markdown output to HTML.
Writes to `data/output/reviews/YYYY-Www.html`.
Zero LLM usage.

Source: `src/output/render_report.py`

### Delivery Layer

Primary: publishes HTML to Telegraph via the Telegraph API.
Returns article URL → appended to Telegram notification.
Fallback 1: if Telegraph fails → sends HTML file as Telegram document attachment.
Fallback 2: if document send fails → sends full Markdown text.

Supports `TELEGRAPH_TOKEN` env var to reuse existing account (skip createAccount step).

Source: `src/delivery/telegraph.py`, `src/output/generate_digest.py`

### Feedback Layer

Captures inline signal feedback from the owner via Telegram bot commands.
Stores in `signal_feedback` table. Never auto-modifies `profile.yaml`.
`tune-suggestions` CLI analyzes acted-on feedback and surfaces boost topic candidates.

Source: `src/db/migrate.py` (record_feedback), `src/bot/handlers.py` (handle_mark_useful, handle_mark_skipped), `src/main.py` (handle_tune_suggestions)

---

### Observability Layer

Tracks:
- LLM cost per call → `llm_usage` table
- Bucket distribution per run → `quality_metrics` table
- Routing model selection per post → `posts.routed_model`

CLI access: `score-stats`, `cost-stats`, `health-check`

Source: `src/llm/client.py:_record_usage()`, `src/output/generate_digest.py:_store_quality_metrics()`

---

## Data Model

### Core tables

| Table | Purpose |
|---|---|
| `raw_posts` | Immutable ingestion records from Telegram (includes `message_url`) |
| `posts` | Normalized, scored, routed view of raw_posts |
| `topics` | Cluster-derived topic labels |
| `post_topics` | Post ↔ topic membership with confidence |
| `llm_usage` | Per-call LLM cost and token tracking |
| `quality_metrics` | Per-run scoring distribution snapshots (used for What Changed delta) |
| `cluster_runs` | Clustering run metadata (silhouette_score used for cluster_coherence) |
| `study_plans` | Generated study plan artifacts |
| `signal_feedback` | Owner feedback per post: `acted_on / skipped / marked_important` |

### Key columns on `posts`

| Column | Type | Set by |
|---|---|---|
| `signal_score` | REAL | `score_posts()` |
| `bucket` | TEXT | `score_posts()` |
| `score_breakdown` | TEXT (JSON) | `score_posts()` |
| `score_run_id` | TEXT | `score_posts()` |
| `scored_at` | TEXT | `score_posts()` |
| `routed_model` | TEXT | `score_posts()` via `route()` |
| `project_relevance_score` | REAL | `score_posts()` via `score_project_relevance()` |

---

## Build Order Constraint

The implementation sequence is not arbitrary. Dependencies are real:

1. **Scoring** must be stable before routing can be calibrated
2. **Routing** must exist before per-post model selection is meaningful
3. **Project relevance** depends on stable scoring (avoid drowning projects in false positives)
4. **Personalization** depends on both scoring and routing (must modulate real signals, not noise)
5. **Output redesign** depends on all upstream layers being stable
6. **Delivery surface** is the last layer — polishing delivery before output quality is proven is waste

---

## Design Constraints

These do not change without explicit reconsideration:

- Expensive models only see filtered subsets — never the full corpus
- Every discarded post must be accounted for (noise section in output)
- Personalization must be auditable — no opaque learned preferences
- Project relevance must be separable from general importance
- Source traceability is required — every signal in the report must link back to its origin
- Scoring must remain deterministic — no stochastic elements in the filter stage
