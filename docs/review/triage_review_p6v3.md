# Phase 6v3 Deep Review — Insight Triage Layer

Date: 2026-04-06
Reviewer: Claude
Phase: 6v3 — Insight Triage and Backlog Memory
Tasks covered: T80–T87
Tests: 136 passing (up from 111)

---

## Review Structure

Each section covers one validation criterion from docs/tasks.md Phase 6v3.
Verdict scale: **Met** / **Partial** / **Not met**

---

## VC-1 — System distinguishes do_now / backlog / reject_or_defer

### Spec

The system classifies each generated insight into at least three categories with an explicit reason.

### Evidence

`src/output/insight_triage.py:classify_insight()`:
- `[Implement]` + non-rebuild mode → `do_now` with reason "Direct improvement to existing project with cited evidence"
- `[Build]` + non-speculative → `backlog` with reason "New project concept — useful but not urgent"
- `rebuild` mode or speculative signal → `reject_or_defer` with reason
- Unknown type → `backlog` (safe default)

Tests: `TestClassifyInsight` — 7 assertions covering all branches. ✅

### Findings

None.

### Verdict: **Met**

---

## VC-2 — Speculative ideas do not surface as equal to actionable ones

### Spec

Portfolio-candy and rebuild ideas appear in `reject_or_defer` section, not alongside `do_now` items.

### Evidence

`_is_speculative()` checks for: portfolio, портфолио, showcase, generic framework, completely rewrite (5 signals).
`_detect_implementation_mode()` returns `rebuild` for: rebuild, rewrite, переписать, полностью переделать.
Both paths route to `reject_or_defer`.

`render_triaged_insights_html()` renders in fixed order: `do_now` → `backlog` → `reject_or_defer`.
Section headers are explicit: `✅ Сделать сейчас` / `📋 Бэклог` / `⏸ Отложить / отклонить`.

Tests: `test_rebuild_mode_classified_reject`, `test_speculative_build_classified_reject`, `test_do_now_before_backlog`. ✅

### Findings

| ID | Sev | Description |
|----|-----|-------------|
| F1 | LOW | Speculative keyword list is English+Russian but not exhaustive. Edge cases like "showcase project" or "educational demo" are not caught. Acceptable for v1 — list can be extended without schema changes. |

### Verdict: **Met**

---

## VC-3 — Repeated rejected ideas are suppressed

### Spec

Rejected ideas do not resurface unchanged until a revisit condition or timeout is met.
Timeout: 4 weeks (`REJECTION_MEMORY_WEEKS = 4`).

### Evidence

`update_rejection_memory()`: upserts `insight_rejection_memory` on `title_fingerprint` UNIQUE key for every `reject_or_defer` insight.
`load_rejection_fingerprints()`: loads fingerprints where `rejected_at >= cutoff` (4 weeks).
`classify_insight()`: if fingerprint in rejection set → `reject_or_defer` with `suppressed=True`.
`_normalize_fingerprint()`: lowercases, strips punctuation, sorts tokens — stable across minor wording variations.

Tests: `test_store_and_load_rejection_fingerprints`, `test_rejection_memory_suppresses_idea`, `test_do_now_not_stored_in_rejection_memory`. ✅

### Findings

| ID | Sev | Description |
|----|-----|-------------|
| F2 | LOW | Token-sort fingerprint (`sorted(tokens)`) handles word-order variation but not synonym variation. "Add retry logic" and "Add retries" produce different fingerprints. Acceptable for v1 — same headline from the LLM across weeks will match. |
| F3 | LOW | `suppressed_until` column exists in schema but is never populated. Currently suppression is purely time-based (rejected_at cutoff). Column reserved for future explicit override. |

### Verdict: **Met**

---

## VC-4 — Output explains why each idea is actionable or not

### Spec

Every classified insight has a human-readable reason. Delivered HTML shows the reason inline.

### Evidence

Every `TriagedInsight` has a `reason: str` field. All classification paths set a non-empty reason.
`render_triaged_insights_html()` appends `<i>(reason)</i>` after each idea block.

Tests: `test_reason_annotation_present`. ✅

### Findings

| ID | Sev | Description |
|----|-----|-------------|
| F4 | LOW | `<i>` tag appended to raw HTML block. On strict Telegraph parsers this is valid but visually the note sits on the same line as the last link. Minor cosmetic issue, no behavioral impact. |

### Verdict: **Met**

---

## VC-5 — Operator can inspect triage state without reading DB

### Spec

CLI command exposes triage counts and rejection memory.

### Evidence

`python3 src/main.py insight-triage-stats` prints:
- counts by recommendation category (do_now / backlog / reject_or_defer)
- last 10 triage records with week_label, recommendation, title, reason
- last 5 rejection memory entries with date and reason

Handler: `src/main.py:handle_insight_triage_stats()`. ✅

### Findings

None.

### Verdict: **Met**

---

## Regression Check

| Area | Status | Notes |
|------|--------|-------|
| Existing recommendations delivery | ✅ No regression | `delivery_text` replaces `insights_text` in all send paths |
| Telegraph publish path | ✅ No regression | `html_path` written from `delivery_text` before publish |
| `_render_insights_fragment` | ✅ No regression | Not called in triage path; existing test still passes |
| `_store_recommendations` | ✅ No regression | Now stores `delivery_text` instead of raw LLM output |
| All prior tests | ✅ 111 → 136 passing | 25 new tests added, 0 regressions |

---

## Summary Table

| VC | Criterion | Verdict | Findings |
|----|-----------|---------|----------|
| VC-1 | Three-category classification | Met | None |
| VC-2 | Speculative ideas separated | Met | F1 (LOW) |
| VC-3 | Rejection memory suppression | Met | F2 (LOW), F3 (LOW) |
| VC-4 | Reason annotation in output | Met | F4 (LOW) |
| VC-5 | Operator CLI visibility | Met | None |

**All validation criteria met. No P0/P1 findings. 4 low-severity findings deferred.**

---

## Phase 6v3 Close Decision

Phase 6v3 is **CLOSED**.

Human phase gate approved: 2026-04-06.

Deferred findings (not blocking):
- F1: speculative keyword list not exhaustive — extend as needed
- F2: fingerprint does not catch synonym variation — acceptable for v1
- F3: `suppressed_until` column reserved but unused — future override mechanism
- F4: `<i>` triage note cosmetic rendering on Telegraph — low visual impact
