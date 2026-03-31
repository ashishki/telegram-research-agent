# Operator Workflow

**Version:** 2.0
**Audience:** System owner (single user, personal use)

---

## Weekly Routine

The system runs automatically via systemd timers. The owner's weekly interaction is minimal by design.

### Monday Morning — Pipeline Runs

The systemd timer triggers the full pipeline:
1. Incremental ingestion (new posts since last run)
2. Normalization and preprocessing
3. Scoring (`score_posts`)
4. Digest generation and signal report formatting
5. Delivery: Telegram notification + full artifact

Owner receives:
- Telegram message: executive summary + bucket counts + top signals
- Link to full review artifact (HTML file or Telegraph article)

Expected time to read: 10–15 minutes.

---

### After Reading — Optional Tuning

If the review contained false positives (noise in strong tier) or missed signals (important post in watch):

**Adjust profile.yaml:**
```yaml
boost_topics:
  - "topic that was important but in watch"
downrank_topics:
  - "topic that polluted strong tier"
```

**Adjust channels.yaml:**
```yaml
- username: "@channel"
  priority: high   # was: medium
```

Changes take effect on next scoring run. No restart required.

---

### On-Demand Commands

```bash
# Verify system health — DB, config, last run timestamps, unscored post count
python3 src/main.py health-check

# Inspect score distribution from last run (+ trend vs previous week)
python3 src/main.py score-stats

# Check LLM cost from last run (+ 4-week weekly trend)
python3 src/main.py cost-stats

# Preview the report without re-running the full pipeline
python3 src/main.py report-preview

# Get boost topic suggestions based on acted-on feedback
python3 src/main.py tune-suggestions
```

### Inline Feedback (from Telegram)

While reading the weekly review, mark signals directly:
```
/mark_useful <post_id>    → records acted_on feedback
/mark_skipped <post_id>   → records skipped feedback
```

Post IDs are visible in the review source appendix. Feedback is stored in `signal_feedback` table.
After several weeks of feedback, run `tune-suggestions` to see recommended boost topic additions.

---

## Monthly Review

Once a month, review:

1. **Scoring distribution trends** — is strong bucket growing? Check `quality_metrics` table or `score-stats`.
   - If strong > 15% of total: raise `strong.min_score` in `scoring.yaml` (currently 0.75)
   - If strong is consistently 0–1 items: lower threshold or expand boost topics

2. **Cost per run** — check `cost-stats`. Is STRONG model usage proportionate?
   - Typical healthy split: 80%+ of calls on Haiku (noise filtering), <5% on Opus (strong signals only)

3. **Profile.yaml freshness** — are boost topics still reflecting current focus?
   - Stale interests produce phantom relevance
   - Remove topics you no longer care about

4. **Projects.yaml** — add new active projects, archive completed ones
   - Dead projects generate false positives in Project Relevance section

---

## Three Signal Value Layers

Every post is evaluated on three independent axes:

| Layer | Question | Config |
|---|---|---|
| **Global signal strength** | Is this objectively useful/novel content? | `scoring.yaml` weights, `channels.yaml` priority |
| **Personal taste relevance** | Does this align with my current focus? | `profile.yaml` boost/downrank topics |
| **Project relevance** | Does this affect what I am building? | `projects.yaml` name + focus |

A post can score high on one layer and low on others:
- High global signal, low taste relevance: appears in Watch but not boosted
- High taste relevance, low global signal: boosted but still capped — strong floor protects against fabricated relevance
- High project relevance: appears in Project Action Queue even if Watch-tier globally

All three scores are stored (`signal_score`, personalized adjustments, `project_relevance_score`) and visible in the report.

---

## Tuning Without Retraining

The system has no ML model to retrain. Tuning is config-file editing:

| Problem | Solution | File |
|---|---|---|
| Too much noise in strong | Raise `strong.min_score` | `scoring.yaml` |
| Missing relevant posts | Add topics to `boost_topics` | `profile.yaml` |
| Wrong source getting boosted | Change channel priority | `channels.yaml` |
| Topic showing up despite downrank | Check if topic label matches exactly | `profile.yaml` |
| Project relevance too broad | Make `focus` field more specific | `projects.yaml` |
| Project relevance too narrow | Add more keyword variants to `focus` | `projects.yaml` |
| Week-old topics recycled | Adjust novelty weights | `scoring.yaml` |

The scoring engine re-reads YAML config on every run. Changes apply without restarting any service.

---

## Feedback Loop

The system captures lightweight feedback without automatic profile changes.

**How it works:**
1. You read the weekly review (Telegraph article or HTML file)
2. For signals you acted on: send `/mark_useful <post_id>` to the bot
3. For signals you skipped: send `/mark_skipped <post_id>`
4. After a few weeks: `python3 src/main.py tune-suggestions` surfaces topics appearing ≥2 times in acted-on signals that are not yet in your `boost_topics`
5. You decide which suggestions to add to `profile.yaml` manually

**Design constraint:** `profile.yaml` is never auto-modified. The feedback loop surfaces suggestions only. You control your taste profile explicitly.

**Current limitations:**
- Feedback is stored but not yet used to adjust scoring weights
- No week-over-week "I acted on this theme" tracking beyond per-post marking
- Suggestions require at least 2 acted-on signals per topic to surface

---

## Initial Setup Checklist

- [ ] Set `AGENT_DB_PATH`, `ANTHROPIC_API_KEY` in environment
- [ ] Fill `src/config/channels.yaml` — your curated channel list with priorities
- [ ] Fill `src/config/profile.yaml` — your boost/downrank topics
- [ ] Fill `src/config/projects.yaml` — your active projects with focus keywords
- [ ] Run `python3 src/main.py health-check` — verify DB and config presence
- [ ] Run bootstrap ingestion for initial data
- [ ] Run `python3 src/main.py score-stats` — verify scoring produces expected distribution
- [ ] Run first digest — review output quality before enabling the timer
