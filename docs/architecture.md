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
  → Insight Triage Layer     (do-now / backlog / reject-or-defer judgment)
  → Output Layer             (reader-facing Research Brief + triaged Implementation Ideas)
  → Render Layer             (HTML generation: render_report.py)
  → Delivery Layer           (Telegraph publish → Telegram URL; Research Brief fallback: HTML file)
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

### Insight Triage Layer

Sits between raw idea generation and the final `Implementation Ideas` surface.

Its purpose is to stop technically plausible but low-priority ideas from being presented as if they are equally ready for implementation now.

Expected outputs:
- `do_now`
- `backlog`
- `reject_or_defer`

Expected judgment dimensions:
- direct improvement vs abstraction
- extract vs rebuild
- current-project value vs portfolio-only value
- evidence strength from code / commits
- main implementation risk

This layer should also preserve rejection/defer memory so the same weak insight does not reappear unchanged every week.

Source: `src/output/insight_triage.py`
Config: `REJECTION_MEMORY_WEEKS = 4` (constant in module)

---

### Output Layer

Assembles the weekly decision brief from all upstream layers.

`format_signal_report(..., reader_mode=True)` produces the reader-facing `Research Brief` used by digest delivery.
`format_signal_report()` without `reader_mode` is still used by `report-preview` as a legacy operator preview.

The reader-facing brief is built around:

1. What Matters This Week
2. Things To Try
3. Keep In View
4. Funny / Cultural
5. Project Insights
6. Additional Signals
7. What Changed

Reader-facing rationale comes from `preference_judge.py`, not from raw operator notes. Manual low-signal items are excluded from the main brief.

`Implementation Ideas` should prefer ideas that passed the triage layer as action-worthy now, while keeping speculative ideas explicitly marked as deferred/backlog rather than presenting them as equivalent execution candidates.

Source: `src/output/signal_report.py`, `src/output/preference_judge.py`, `src/output/project_relevance.py`, `src/output/personalize.py`

### Render Layer

Converts reader-facing `Research Brief` Markdown output to HTML.
Writes to `data/output/reviews/YYYY-Www.html`.
Zero LLM usage.

Source: `src/output/render_report.py`

### Delivery Layer

`run_digest()` owns delivery orchestration:
- publishes `Research Brief` HTML to Telegraph
- publishes `Implementation Ideas` HTML to Telegraph through `run_recommendations()`
- stores `telegraph_url` and `telegram_sent_at` on both artifacts

Fallback behavior is asymmetric by design:
- `Research Brief`: Telegraph → HTML document attachment → full Markdown text
- `Implementation Ideas`: Telegraph → short Telegram notification without article body

Operational constraint: the service user must be able to write to `data/output/reviews`, `data/output/recommendations`, and `data/output/study_plans`, or delivery can fail before Telegraph publish.

Supports `TELEGRAPH_TOKEN` env var to reuse existing account (skip createAccount step).

Source: `src/delivery/telegraph.py`, `src/output/generate_digest.py`

### Feedback Layer

Captures inline signal feedback from the owner via Telegram bot commands.
Stores in `signal_feedback` table. Never auto-modifies `profile.yaml`.
`tune-suggestions` CLI analyzes acted-on feedback and surfaces boost topic candidates.

Source: `src/db/migrate.py` (record_feedback), `src/bot/handlers.py` (handle_mark_useful, handle_mark_skipped), `src/main.py` (handle_tune_suggestions)

### Preference Memory Layer

Stores explicit user tags (`strong`, `interesting`, `try_in_project`, `funny`, `low_signal`, `read_later`) in `user_post_tags`.

This layer affects the system in three ways:
- explicit post override via `posts.user_override_tag`
- learned per-channel/source bias reflected in `posts.user_preference_score`
- final ranking via `posts.user_adjusted_score` plus `preference_judge.py`

This keeps preference learning auditable: the ground truth is still explicit user input, not a hidden model state.

### Context Memory Layer

Stores two lightweight, persistent context surfaces:

- `channel_memory`: what each Telegram source tends to be good or bad at for this user, based on explicit tags
- `project_context_snapshots`: current project description, focus, recent commit deltas, and relevance gaps

`channel_memory` is refreshed from tagged history.
`project_context_snapshots` is updated incrementally during GitHub sync using current metadata and recent commit messages.

These memories are fed into `preference_judge.py` and project-insight generation so the reader-facing brief can explain what matters without forcing the user to open every source link.

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
| `user_post_tags` | Explicit per-post tags used for preference learning and report shaping |
| `channel_memory` | Source-level memory derived from manual tags |
| `project_context_snapshots` | Incremental project context used by project-aware synthesis |
| `insight_triage_records` | Per-week triage classification of each generated insight |
| `insight_rejection_memory` | Fingerprint-based suppression store for repeat low-value ideas |

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
| `user_preference_score` | REAL | `score_posts()` from historical manual tags |
| `user_adjusted_score` | REAL | `score_posts()` deterministic score + preference bias |
| `user_override_tag` | TEXT | `score_posts()` from explicit tag on that post |

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
- Every discarded post must still be auditable even if not shown in the reader-facing brief
- Personalization must be auditable — no opaque learned preferences
- Project relevance must be separable from general importance
- Source traceability is required — every signal in the report must link back to its origin
- Scoring must remain deterministic in the pre-filter stage; LLM judging happens only after shortlist creation
