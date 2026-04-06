# Weekly Review Artifact — Format Specification

**Version:** 3.0
**Status:** Implemented — preference-shaped weekly brief

---

## Purpose

This document defines the structure and content contract for the weekly review artifact — the primary output of the system.

The artifact is not a summary. It is a decision-support review designed for a 10–15 minute weekly reading session. It answers the question: *what should I think about and act on this week, given what I am building?*

---

## Delivery Model

Two-tier delivery:

**Tier 1 — Telegram notification**
Sent to the owner's Telegram immediately after the pipeline completes.
Contains: short status text and direct link to the full artifact.
Format: plain text or minimal HTML.

**Tier 2 — Full review artifacts**
A well-structured, readable long-form document.
Delivered as:
- a `Research Brief` Telegraph article
- an `Implementation Ideas` Telegraph article
- fallback HTML attachment for `Research Brief` if Telegraph is unavailable
Readable inside Telegram without opening an external app.
Scannable — section headers, bullet points, source links inline per signal.

---

## Artifact Structure

`Research Brief` sections stay in this order when populated. Reader-facing sections may be omitted if empty. Noise and operator-only metrics do not belong in the main brief.

---

### 1. What Matters This Week

Up to 5 highest-confidence signals.
For each:
- One-sentence summary of the signal
- Why it matters (1–2 sentences: specifically for this user and current projects)
- Source link

`signal_score`, `post_id`, and internal tags are operator-only and should not appear here.

Format:
```
**Title or summary**
Key takeaway: ...
Why now: ...
Source: https://t.me/channel/message_id
```

---

### 2. Things To Try

Concrete ideas to test in active projects.

---

### 3. Project Insights

One sub-section per active project with at least one relevant signal.
Skip projects with no matches above relevance threshold (0.3).

For each project:
```
**project-name**
- Signal summary → rationale for why it's relevant
  Source: https://t.me/...
```

Project relevance may come from deterministic matching or the preference judge. Reader-facing "why" text should be written by the model, not copied from manual notes.

---

### 4. Keep In View

Signals worth tracking but not acting on yet.

---

### 5. Funny / Cultural

Optional. Only include if the user explicitly tagged cultural/funny items or the preference judge found clear context value.

---

### 6. Additional Signals

Auto-selected, high-confidence signals that were not manually tagged yet.

---

### 7. What Changed Since Last Week

Delta from the previous week's review. Automatic, no LLM required.
Shows:
- Bucket shifts
- notable deltas in signal volume
- any meaningful change worth scanning quickly

If no prior week in DB: "No comparison baseline available."

---

## Implementation Notes

`format_signal_report(..., reader_mode=True)` in `src/output/signal_report.py` produces the delivered `Research Brief`.
`format_signal_report()` without `reader_mode` is the operator-facing legacy preview used by `report-preview`.
Telegraph is the primary reading surface.
Source links: `https://t.me/{channel_username}/{message_id}` — already stored in `raw_posts.message_url`.
The report is informed by:
- deterministic scoring
- manual tags in `user_post_tags`
- preference-shaped `user_adjusted_score`
- `preference_judge.py` for reader-facing titles, why text, and project angle
- `channel_memory` and `project_context_snapshots` so important context can be pulled into the brief instead of outsourced to the source link

**Constraints:**
- Telegram message hard limit: 4096 chars — notification should stay short
- Telegraph article limit: ~65 KB — full review must fit
- Source links must be real `t.me` deep links, not channel root links

---

## Anti-Patterns to Avoid

- Sending the full review as a Telegram message blob
- Omitting source links (traceability is non-negotiable)
- Rendering the report as raw Markdown in Telegram (use HTML parse_mode or Telegraph)
- Showing operator-only fields like `post_id`, raw scores, or manual notes in the reader-facing brief
- Writing prose summaries per-item instead of evidence-forward bullets
- Assuming `report-preview` is identical to the delivered Telegraph brief
