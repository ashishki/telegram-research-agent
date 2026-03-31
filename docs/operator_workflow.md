# Operator Workflow

**Version:** 1.0
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
# Verify system health before the week
python3 src/main.py health-check

# Inspect score distribution from last run
python3 src/main.py score-stats

# Check LLM cost from last run
python3 src/main.py cost-stats

# Preview the report without re-running the full pipeline
python3 src/main.py report-preview
```

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

## Feedback Loop (Current Limitations)

The system does not currently:
- Learn from which signals you actually acted on
- Remember "this was useful" across weeks
- Adjust weights based on reading behavior

These are intentional deferments, not design failures.

The current taste model is explicit rules in `profile.yaml`. This is auditable, predictable, and sufficient for weekly use.

Future evolution (Phase 3): introduce a lightweight feedback capture — marking signals as "acted on" or "skipped" — to inform future boost/downrank suggestions.

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
