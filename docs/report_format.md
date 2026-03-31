# Weekly Review Artifact — Format Specification

**Version:** 2.0
**Status:** Implemented — Roadmap v3 complete

---

## Purpose

This document defines the structure and content contract for the weekly review artifact — the primary output of the system.

The artifact is not a summary. It is a decision-support review designed for a 10–15 minute weekly reading session. It answers the question: *what should I think about and act on this week, given what I am building?*

---

## Delivery Model

Two-tier delivery:

**Tier 1 — Telegram notification**
Sent to the owner's Telegram immediately after the pipeline completes.
Contains: brief executive summary (3–5 lines), bucket counts, top 2–3 strong signals, direct link to the full artifact.
Format: plain text or minimal HTML.

**Tier 2 — Full review artifact**
A well-structured, readable long-form document.
Delivered as: a Telegraph article (primary), an attached HTML file (fallback if Telegraph unavailable), or a full Markdown text (final fallback).
Readable inside Telegram without opening an external app.
Scannable — section headers, bullet points, source links inline per signal.

---

## Artifact Structure

Sections in order. All sections are required. If a section has no content, render a brief "nothing to report" note — never silently omit a section.

---

### 1. Executive Summary

2–4 sentences. Answers:
- How many posts were reviewed this week?
- How many reached strong/watch tier?
- What was the dominant theme?
- Any notable delta from last week?

Example:
> 312 posts reviewed. 7 strong signals, 23 watch. Main themes: LLM inference optimization, agent evaluation frameworks. Notable shift: three independent posts on structured output reliability — first time this topic reached strong tier.

---

### 2. What Matters Now

Up to 5 strong-tier signals.
For each:
- One-sentence summary of the signal
- Why it matters (1–2 sentences: global significance, not just summary)
- Source link
- `signal_score`, `routed_model`
- Optional: `[personalized]` tag if boost/downrank changed its position

Format:
```
**[score=0.87] Title or summary**
Why it matters: ...
Source: https://t.me/channel/message_id
```

---

### 3. Decisions to Consider

Explicit, opinionated section. 1–4 items.
Only populated if strong signals suggest a concrete action or decision.
Written as imperatives:
- "Consider switching to structured output for the eval pipeline in gdev-agent."
- "Re-read the RAG latency paper before the next sprint."

This section may be empty if no strong signal has a clear decision implication. In that case: "No decision-forcing signals this week."

---

### 4. Project Action Queue

One sub-section per active project with at least one relevant signal.
Skip projects with no matches above relevance threshold (0.3).

For each project:
```
**project-name**
- [relevance=0.71] Signal summary → rationale for why it's relevant
  Source: https://t.me/...
```

---

### 5. Watch — Pending Signals

Watch-tier posts (score 0.45–0.74) that did not reach strong threshold.
These are worth knowing; not urgent.
Compact format — one line per item with source link.

Cap at 10 items. If more: "and N more — run report-preview to see full list."

---

### 6. What Changed Since Last Week

Delta from the previous week's review. Automatic, no LLM required.
Shows:
- Topics that entered or left strong tier
- Projects that gained or lost relevant signals
- Any routing distribution shifts (e.g., "strong bucket grew from 3 to 8 — check scoring thresholds")

If no prior week in DB: "No comparison baseline available."

---

### 7. Ignore With Confidence

Noise summary. Shows that the system processed and consciously discarded low-value content.
Format:
```
X posts filtered as noise.
Top noise topics: ChatGPT tips (14), funding rounds (9), image generation (8)
```
No content from noise posts. Count and topic distribution only.

---

### 8. Learning Edge

Up to 3 learning gap items from `extract_learning_gaps()`.
Only topics with frequency ≥ 2 in strong/watch tier, not covered by any project focus.

Format:
```
- langchain (seen 4 times this week) — not in any active project focus
  Suggested: review if this belongs in gdev-agent's focus or can stay on watch
```

Cultural section (if any):
1–2 cultural items. Context/mood of the community, not requiring action.

---

### 9. Evidence / Source Appendix

Full list of strong + watch posts with:
- Source link (`https://t.me/channel/id`)
- Channel name
- Post date
- signal_score
- bucket
- project_relevance_score (if > 0)

This section enables traceability — every claim in the review can be traced back to a source.

---

## Implementation Notes

**Immediate (Phase 1):**
- `format_signal_report()` in `src/output/signal_report.py` produces the structured content
- Delivery: generate as HTML file (`data/output/reviews/YYYY-Www.html`) + send via Telegram
- Telegram notification: extract executive summary + link to file
- Source links: `https://t.me/{channel_username}/{message_id}` — already stored in `raw_posts.message_url`

**Target (Phase 4):**
- Telegraph article via Telegraph API (`https://telegra.ph`)
- Telegraph supports HTML input; the review HTML maps directly
- Link sent via Telegram bot message
- Instant View compatible if structured with standard Telegraph article format

**Constraints:**
- Telegram message hard limit: 4096 chars — executive summary must fit
- Telegraph article limit: ~65 KB — full review must fit
- Source links must be real `t.me` deep links, not channel root links

---

## Anti-Patterns to Avoid

- Sending the full review as a Telegram message blob
- Omitting source links (traceability is non-negotiable)
- Rendering the report as raw Markdown in Telegram (use HTML parse_mode or Telegraph)
- Skipping the Ignore section (users must trust that noise was seen and discarded)
- Writing prose summaries per-item instead of evidence-forward bullets
