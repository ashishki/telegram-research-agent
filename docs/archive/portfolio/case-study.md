# Case Study: Personal Research Intelligence Pipeline

## The Problem

I follow 40+ Telegram channels covering AI/ML, backend engineering, and developer tooling. Weekly, that's 300–500 posts. Reading everything takes 3–4 hours. Skimming wastes signal. Most digest tools just summarize what was posted — they don't help me decide what to act on.

The core problem is not volume. It's prioritization under uncertainty:
- Which of these 300 posts matters for what I'm building *right now*?
- What's genuinely novel vs. what's noise dressed as signal?
- Which channels have earned trust vs. which amplify hype?

A bot that summarizes 300 posts into 30 bullet points doesn't solve this.

---

## Why a Digest Bot Doesn't Work

Standard digest bots have a fundamental architectural flaw: they apply expensive LLM reasoning to everything indiscriminately.

The result:
- High cost scales with volume, not with signal quality
- LLM outputs are non-deterministic — same post gets different summaries each run
- No auditability: you can't trace why something was included or excluded
- No taste: the bot doesn't know what *I* care about vs. generic "interesting AI content"
- No project awareness: "useful" is context-dependent — useful for what?

---

## The Architectural Decision: Deterministic Scoring as a Gate

The core design principle: **no LLM call until a post has cleared a deterministic quality gate**.

Every post receives a `signal_score` computed from five weighted dimensions — no LLM involved:

```
signal_score = personal_interest × 0.30
             + source_quality    × 0.20
             + technical_depth   × 0.20
             + novelty           × 0.15
             + actionability     × 0.15
```

This score determines which model tier (if any) sees the post:
- score ≥ 0.75 → Opus (strong signal)
- score 0.45–0.74 → Sonnet (watch)
- score < 0.45 → no LLM (noise)
- cultural keywords match → Haiku (context-only)

**~90% of posts never reach an LLM.** Cost scales with signal density, not channel volume.

Why this matters:
- Scoring is reproducible: same post, same config → same score, always
- Tunable without retraining: edit `scoring.yaml`, next run reflects changes
- Auditable: every post has a `score_breakdown` JSON field — you can see exactly why it scored 0.82 vs. 0.31
- Cheap: a typical weekly run costs $0.04–0.07 regardless of post volume

---

## Three Independent Relevance Axes

A key insight: "relevant" is not one-dimensional.

A post can be globally high-quality (fascinating ML research) but personally irrelevant (I'm not working on ML infra this week). Or watch-tier globally but critical for a specific project.

The system evaluates three independent axes:

| Axis | Question | Config |
|---|---|---|
| Global signal strength | Is this objectively useful content? | `scoring.yaml`, `channels.yaml` |
| Personal taste | Does this match my current focus? | `profile.yaml` boost/downrank |
| Project relevance | Does this affect what I'm building? | `projects.yaml` keywords |

These are stored and surfaced separately. You get the full picture, not a collapsed rank.

---

## The Report Artifact

The weekly output is not a summary. It's a structured decision-support review designed for a 10–15 minute reading session.

**Eight mandatory sections:**

1. **Strong Signals** — up to 5 posts with score, model tier, source link, personalization tag
2. **Decisions to Consider** — explicit action items derived from strong signals
3. **Watch** — signals worth tracking, not yet urgent
4. **Cultural** — low-signal context items
5. **Ignored** — noise count by topic (proves coverage, not just filtering)
6. **Think Layer** — themes and patterns
7. **Stats** — bucket distribution
8. **What Changed** — delta vs previous week (are strong signals increasing? decreasing?)

**Two conditional sections** (require projects config):
9. **Project Action Queue** — per-project sub-sections, matched keywords shown
10. **Learn** — recurring strong/watch topics not covered by any project focus

Every signal links back to its source (`https://t.me/{channel}/{message_id}`). Nothing is anonymous.

---

## Delivery

The weekly output is published as two Telegraph articles — `Research Brief` and `Implementation Ideas`. Both are full-screen, scrollable, and readable inside Telegram without leaving the app. Short notifications (≤300 chars) with article URLs are sent to Telegram immediately.

Fallback chain for `Research Brief` if Telegraph is unavailable:
1. HTML file attachment (generated to `data/output/reviews/YYYY-Www.html`)
2. Full Markdown text (last resort)

---

## Feedback Loop

After reading, you can mark signals inline:
```
/mark_useful <post_id>
/mark_skipped <post_id>
```

After several weeks, `tune-suggestions` surfaces topics that appear frequently in your acted-on signals but aren't in your boost list. You review the suggestions and edit `profile.yaml` manually.

**profile.yaml is never auto-modified.** The feedback loop surfaces evidence — you make the decision.

---

## What Makes It Production-Ready (for Personal Use)

- Runs on a personal VPS via systemd timer — no manual intervention
- Idempotent ingestion (no duplicate posts on re-run)
- All config in YAML — no database schema changes needed for tuning
- Full observability: cost trends, score distribution trends, health-check with stuck queue detection
- 106 tests, CI on every push
- Fallback at every external dependency (Telegraph, Telegram Bot API, DB)

---

## Trade-offs and Limitations

**What it intentionally doesn't do:**
- It doesn't learn automatically — preferences require manual profile.yaml edits (after `tune-suggestions` hints)
- It doesn't support multiple users — single-user design throughout
- It doesn't replace reading — it filters down to what deserves reading

**Known constraints:**
- Project relevance is keyword-based, not semantic — "fastapi" matches "FastAPI" but not "the web framework"
- Cultural bucket is keyword-triggered — cultural signal detection is heuristic
- Learning gaps require topic clusters — needs clustering step to run first

---

## Lessons Learned

1. **Determinism before intelligence.** The scoring layer is the system's most valuable component. It's cheap, fast, reproducible, and tunable. LLMs are enhancement, not infrastructure.

2. **Auditability is a feature.** Every filtering decision is traceable. `score_breakdown` JSON shows exactly which dimension drove the score. This makes tuning mechanical rather than guesswork.

3. **Three relevance axes beat one.** Global signal + personal taste + project relevance are genuinely independent. Collapsing them loses information.

4. **The report format matters as much as the content.** A well-structured artifact that fits a 15-minute reading session is more useful than a comprehensive but exhausting document.

5. **Build the gate before the intelligence.** Getting the signal/noise separation right enables everything downstream. Adding features before scoring is stable means building on shifting sand.

---

## System Stats (Baseline v1.0, 2026-03-31)

- 106 automated tests
- Roadmap v2 (T29–T64) + Roadmap v3 (T65–T79) complete
- Pipeline: 10 layers from ingestion to feedback
- Config files: 4 YAML files, zero code changes needed for weekly tuning
- Typical weekly cost: $0.04–0.07
- Typical weekly read time: 10–15 minutes
