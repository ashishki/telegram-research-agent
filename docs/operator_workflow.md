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

The systemd timer triggers the full pipeline:
1. Incremental ingestion (new posts since last run)
2. Normalization and preprocessing
3. Scoring (`score_posts`)
4. Digest generation and reader-facing signal report formatting
5. Delivery: Telegram notifications + full artifacts

Owner receives:
- Telegram message: short `Research Brief` notification + Telegraph link
- Telegram message: short `Implementation Ideas` notification + Telegraph link

Expected time to read: 10–15 minutes.

`Implementation Ideas` should be treated as a triaged surface:
- `do now` ideas are candidate implementation moves for the current working horizon
- `backlog` ideas are useful but not urgent
- `reject/defer` ideas should be remembered and suppressed from repeating unchanged

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
- guide the weekly preference judge
- influence project insights and the next study plan

The system also maintains:
- `channel_memory` derived from your tag history
- `project_context_snapshots` derived from GitHub sync and recent commit deltas

That lets the brief explain more directly in the article and reduces the need to open the original Telegram post.

---

### On-Demand Commands

```bash
# Verify system health — DB, config, last run timestamps, unscored post count
python3 src/main.py health-check

# Inspect score distribution from last run (+ trend vs previous week)
python3 src/main.py score-stats

# Check LLM cost from last run (+ 4-week weekly trend)
python3 src/main.py cost-stats

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
```

### Inline Feedback (from Telegram)

While reading the weekly brief:
```text
/mark_useful <post_id|link>   -> records acted_on feedback
/mark_skipped <post_id|link>  -> records skipped feedback
/study                        -> show the current weekly study plan
/study refresh                -> rebuild this week's study plan
/study_done [notes]           -> mark this week's plan as completed
```

The study plan now has a weekly completion loop:
1. The system sends one reminder per week
2. You complete the plan and mark it with `/study_done`
3. Completed study history is fed into future study plans and recommendations

---

## Monthly Review

Once a month, review:

1. **Scoring distribution trends** — is strong bucket growing? Check `quality_metrics` table or `score-stats`.
   - If strong > 15% of total: raise `strong.min_score` in `scoring.yaml` (currently 0.75)
   - If strong is consistently 0–1 items: lower threshold or expand boost topics

2. **Cost per run** — check `cost-stats`.
   - The output now shows actual `cost_usd`, estimated cost, weekly trend, and weekly category breakdown
   - `preference_judge` is expected to be one of the higher-cost categories because it writes the reader-facing brief

3. **Profile.yaml freshness** — are boost topics still reflecting current focus?
   - Stale interests produce phantom relevance
   - Remove topics you no longer care about

4. **Projects.yaml** — add new active projects, archive completed ones
   - Dead projects generate false positives in Project Relevance section

5. **Implementation Ideas quality** — review whether weekly ideas are operationally useful or drifting into speculative abstractions
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
| Wrong source repeatedly rated well/badly | Tag more posts from that source and let channel bias adapt | Telegram bot + `user_post_tags` |
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
2. Tag or mark signals directly from Telegram
3. The next scoring run updates explicit overrides and channel/source bias
4. The weekly preference judge uses those examples to reshape the final brief
5. `tune-suggestions` can still surface profile topic candidates, but manual tags are now the primary signal

**Design constraint:** `profile.yaml` is never auto-modified. The feedback loop surfaces suggestions only. You control your taste profile explicitly.

**Current limitations:**
- Preference bias is source-aware, but not yet a full ML ranking model
- Study completion is tracked at the weekly-plan level, not per individual block
- Project insights still benefit from stronger prompts and more labeled examples

## Project Context Maintenance

Project context is not just a static `projects.yaml` description anymore.

Current state is built from:
- `projects.yaml` baseline description and focus
- GitHub metadata from sync (`github_repo`, `last_commit_at`)
- recent commit messages folded into `project_context_snapshots`
- Telegram relevance already linked in the DB

This lets study planning, recommendations, and project insights reason from recent project changes instead of from keywords alone.

---

## Initial Setup Checklist

- [ ] Set `AGENT_DB_PATH`, `ANTHROPIC_API_KEY` in environment
- [ ] Set `TELEGRAPH_TOKEN` if you want a stable Telegraph account instead of anonymous per-publish accounts
- [ ] Fill `src/config/channels.yaml` — your curated channel list with priorities
- [ ] Fill `src/config/profile.yaml` — your boost/downrank topics
- [ ] Fill `src/config/projects.yaml` — your active projects with focus keywords
- [ ] Ensure the service user can write to `data/output/reviews`, `data/output/recommendations`, and `data/output/study_plans`
- [ ] Run `python3 src/main.py health-check` — verify DB and config presence
- [ ] Run bootstrap ingestion for initial data
- [ ] Run `python3 src/main.py score-stats` — verify scoring produces expected distribution
- [ ] Run first digest — review output quality before enabling the timer
