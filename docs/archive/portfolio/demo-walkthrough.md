# Demo Walkthrough — Telegram Research Agent

A step-by-step trace of one full weekly pipeline run.

---

## Setup

**Config files (edit once, never touch again unless tuning):**

`src/config/channels.yaml` — curated channel list:
```yaml
channels:
  - username: "@fastapi_official"
    priority: high
  - username: "@ainews"
    priority: high
  - username: "@mlengineering"
    priority: medium
  - username: "@crypto_daily"
    priority: low
```

`src/config/profile.yaml` — personal taste:
```yaml
boost_topics:
  - "AI agents"
  - "FastAPI"
  - "async Python"
downrank_topics:
  - "crypto"
  - "ChatGPT tips"
cultural_keywords:
  - "GPT-4o"
  - "Manus AI"
```

`src/config/projects.yaml` — active projects:
```yaml
projects:
  - name: gdev-agent
    description: "Multi-tenant AI triage service. FastAPI, PostgreSQL, Redis."
    focus: "service layer, eval pipeline, cost control"
    keywords: [fastapi, redis, webhook, classification, async]
    exclude_keywords: [film]
```

---

## Step 1 — Ingestion

The systemd timer fires Monday at 06:00. Telethon connects via MTProto.

```bash
python3 src/main.py ingest
```

What happens:
- Fetches messages from each configured channel since last run
- Writes to `raw_posts` table: `(channel_id, message_id, content, posted_at, view_count, message_url)`
- `message_url` set to `https://t.me/{username_clean}/{message_id}` for every post
- Idempotent: duplicate `(channel_id, message_id)` pairs are skipped

Result: 312 new posts in `raw_posts`.

---

## Step 2 — Preprocessing

```bash
python3 src/main.py normalize
```

For each post:
- Text normalization: strip HTML, collapse whitespace
- Structural extraction: `has_code`, `url_count`, `word_count`
- Language detection
- TF-IDF topic cluster assignment via `cluster_posts`

Result: `posts` table populated with normalized fields and topic assignments.

---

## Step 3 — Scoring (the gate)

```bash
python3 src/main.py score
```

For each post, five dimensions are computed:

**personal_interest** (weight 0.30)
- Topic labels matched against `boost_topics`/`downrank_topics` from profile.yaml
- A post about "FastAPI" gets boost multiplier; a post about "crypto" gets downrank

**source_quality** (weight 0.20)
- Channel priority weight (`high=1.0, medium=0.6, low=0.2`) × normalized view count within channel
- High-trust sources with high engagement rank above low-priority channels

**technical_depth** (weight 0.20)
- Structural proxies: code presence (0/1), link count (0→1 at ≥2), word count (0→1 at ≥80 words)
- Also incorporates silhouette_score from latest cluster_run as coherence signal

**novelty** (weight 0.15)
- How recently has this topic appeared in the last 4 weeks?
- New topics score 0.80; topics seen every week for 4 weeks score 0.30 (recurring penalty)

**actionability** (weight 0.15)
- Heuristic inference from content: `implement` / `pattern` / `awareness` / `noise`
- "Shows how to implement X" scores higher than "X exists"

Combined:
```
signal_score = 0.30 × d_interest + 0.20 × d_source + 0.20 × d_depth + 0.15 × d_novelty + 0.15 × d_action
```

Buckets:
- score ≥ 0.75 → `strong` → routed to claude-opus-4-6
- score 0.45–0.74 → `watch` → routed to claude-sonnet-4-6
- cultural keyword match → `cultural` → claude-haiku-4-5-20251001
- otherwise → `noise` → no LLM

Result: 312 posts scored. 7 strong, 23 watch, 4 cultural, 278 noise.

Check distribution:
```bash
python3 src/main.py score-stats
# strong: count=7 avg_signal_score=0.8214
# watch:  count=23 avg_signal_score=0.5871
# trend vs 2026-W12:
#   strong_count: 7 (+2)
```

---

## Step 4 — Personalization

Applied inside `format_signal_report()`:
- Boost-topic posts get score × 1.3 (capped at 1.0)
- Downrank-topic posts get score × 0.5
- Strong posts (bucket=strong) cannot fall below watch threshold (0.45)

A post about "AI agents" by a medium-priority channel that scored 0.52 gets boosted to 0.68 — stays in watch but ranks higher within it. Tagged `[personalized]` in the report.

---

## Step 5 — Project Relevance

For each strong/watch post, `score_project_relevance()` checks against all active projects:

Post: "FastAPI 0.112 drops response_model_include overhead 40% in benchmarks"
Post tokens: {fastapi, drops, response, model, include, overhead, benchmarks}

Against gdev-agent keywords: {fastapi, redis, webhook, classification, async}
Overlap: {fastapi} → score = 1/5 = 0.20

Hmm, only 0.20. But the post also has "async" in context — post tokens include {async} → overlap = {fastapi, async} → 2/5 = 0.40 → above 0.3 threshold.

exclude_keywords check: {film} — not in post → no suppression.

Result: `[relevance=0.40] Matches: async, fastapi → gdev-agent`

---

## Step 6 — Weekly Review Assembly

`format_signal_report()` assembles the full Markdown document:

```
## Strong Signals
- [score=0.87] [model=claude-opus-4-6] FastAPI 0.112 drops response_model_include overhead 40%... | Source: https://t.me/fastapi_official/2847
- [score=0.82] [model=claude-opus-4-6] [personalized] Anthropic publishes extended thinking latency benchmarks...

## Decisions to Consider
- Consider: FastAPI 0.112 async path rewrite overhead reduction benchmarks production upgrade.
- Consider: Anthropic Opus extended thinking latency benchmarks reasoning complex tasks.

## Watch
- [score=0.71] PostgreSQL 17 COPY FROM performance improvements... | Source: https://t.me/postgres_ru/441
...

## What Changed
strong: 7 (was 5, +2)
watch: 23 (was 24, -1)
noise: 278 (was 264, +14)

## Project Action Queue

**gdev-agent** (2 signals)
- [relevance=0.40] Matches: async, fastapi -> FastAPI 0.112 async path rewrite... | Source: https://t.me/fastapi_official/2847
- [relevance=0.33] Matches: webhook, service -> GitHub Copilot Workspace multi-file agent loop...

## Learn
- LLM inference optimization (seen 3 times) → recurring in strong/watch, not covered by any project focus
```

---

## Step 7 — HTML Render + Telegraph Publish

```python
# render_report.py
html = render_report_html(markdown_content)
# Converts ## → <h2>, - items → <ul><li>, **bold** → <b>

html_path = write_report_html("2026-W13", markdown_content)
# Writes to data/output/reviews/2026-W13.html
```

Then `publish_article()`:
1. Gets access token (from `TELEGRAPH_TOKEN` env var, or creates anonymous account)
2. Converts HTML → Telegraph Node objects: `<h2>` → `{"tag": "h3", "children": ["text"]}`
3. POSTs to `https://api.telegra.ph/createPage`
4. Returns: `https://telegra.ph/Research-Brief-2026-W13`

---

## Step 8 — Telegram Delivery

Notification (≤300 chars):
```
Research Brief 2026-W13 is ready.
7 strong signals, 23 watch.
https://telegra.ph/Research-Brief-2026-W13
```

If `Research Brief` Telegraph publish fails → sends HTML as Telegram document attachment.
If document send fails → sends full Markdown text.
`Implementation Ideas` is published separately as its own Telegraph article.

---

## Step 9 — Reading and Feedback

You read the Telegraph article (10–15 min).

For signals you acted on:
```
/mark_useful 847
```

Bot confirms: `Feedback recorded: acted_on for post 847`

Data stored in `signal_feedback`:
```
id=1, post_id=847, feedback=acted_on, recorded_at=2026-03-31T10:23:14Z
```

---

## Step 10 — Tune Suggestions (after several weeks)

After 3–4 weeks of feedback:
```bash
python3 src/main.py tune-suggestions

Suggested boost topics (appeared in acted-on signals but not in your profile):
  - LLM inference optimization (seen 4 times)
  - speculative decoding (seen 3 times)
```

You decide: add "LLM inference" to `boost_topics` in `profile.yaml`. Done. Next run applies it automatically.

---

## Operator Check (any time)

```bash
python3 src/main.py health-check
# db_path: /home/gdev/.../agent.db
# posts: 312
# scored_posts: 312
# last_ingestion: 2026-03-31T06:00:12Z
# last_digest: 2026-W13
# profile.yaml: present
# projects.yaml: present

python3 src/main.py cost-stats
# total_cost_usd=0.04821200
# weekly_trend (last 4 weeks):
#   2026-W13  calls=31  cost=$0.046212
#   2026-W12  calls=28  cost=$0.039840
```
