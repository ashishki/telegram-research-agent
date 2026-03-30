---
# REVIEW_REPORT — Cycle 2
_Date: 2026-03-30 · Scope: T22–T27 (Phase 19 — Signal Intelligence Redesign)_

---

## Executive Summary

- **Stop-Ship: Yes** — CODE-1 (P1) blocks phase close: zero test coverage for the scoring engine and digest rewire; T24 AC requires at least one unit test and none exist.
- Phase 19 (T22–T27) was implemented inline in a single Orchestrator session without Light Review gates between tasks (documented workflow violation). All tasks are marked `[~]` and must be treated as unreviewed code.
- Architecture verdict: scoring pipeline, schema migration, prompt redesign, NO_OVERLAP_NOTE elimination, and all config files PASS structural review.
- Two architectural drift findings (ARCH-1/ARCH-2) confirm that `run_digest()` has become a covert orchestrator and `handle_run_digest` in the bot layer redundantly triggers recommendations delivery — creating a duplicate-delivery defect (CODE-6, P2).
- `quality_metrics` table was migrated correctly but is never populated after digest runs (CODE-8, P2) — observability gap.
- Baseline: 12 passing tests. Phase 19 adds no new tests; baseline must not regress.
- Four carry-forward findings from Cycle 1 (CODE-2, CODE-3, CODE-4, CODE-5) remain OPEN — partially mitigated by Phase 18/19 work but not closed (no code fix verified).
- Documentation is stale: `docs/architecture.md` and `docs/spec.md` do not reflect scoring layer, new DB columns, or T27 prompt variables (ARCH-3/ARCH-5, both P3).

---

## P0 Issues

_None identified this cycle._

---

## P1 Issues

### P1-1 (CODE-1) — Zero test coverage for scoring engine and digest rewire

**Symptom:** `tests/` directory contains no test file covering `src/processing/score_posts.py` or the rewired `src/output/generate_digest.py`. T24 acceptance criterion explicitly requires "at least 1 unit test covering bucket assignment logic" — this criterion is unmet.

**Evidence:** `tests/` (missing `test_score_posts.py` and `test_generate_digest.py`); T24 AC line 518 in `docs/tasks.md`.

**Root Cause:** T22–T27 were implemented inline in a single Orchestrator session. The test-writing step was either skipped or deferred without a gate. The scoring engine is the most complex new component (multi-dimensional weighted score, bucket thresholds, cultural override, personal interest boost/downrank) and has no automated safety net.

**Impact:** Any regression in bucket boundary logic (e.g., a weight config change that shifts the 0.75 strong threshold, or a profile keyword change that affects cultural override) will go undetected. The word-count gate warning path and `NO_OVERLAP_NOTE` guard in the digest generator are also untested. This is a phase-blocking finding per the Cycle 2 protocol: P1 finding in new Phase 19 code → phase treated as BLOCKED.

**Fix:**
1. Create `tests/test_score_posts.py`:
   - Bucket boundary values: post with signal_score 0.74 → `watch`; 0.75 → `strong`; 0.44 → `noise`.
   - Cultural keyword override: post with signal_score below watch threshold but cultural keyword in content → `cultural`.
   - `_score_personal_interest`: boost topic → score > neutral; downrank topic → score < neutral; neutral topic → baseline.
2. Create `tests/test_generate_digest.py`:
   - Word-count gate: mock LLM response with > 600 words → WARNING logged.
   - `NO_OVERLAP_NOTE` guard: repo with `matched_topics == ["NO_OVERLAP_NOTE"]` → skipped in `_append_github_section`.

**Verify:** `pytest tests/test_score_posts.py tests/test_generate_digest.py` — all green, no regressions to existing 12-test baseline.

---

## P2 Issues

| ID | Description | Files | Status |
|----|-------------|-------|--------|
| CODE-2 | `send_text()` hardcodes `parse_mode="HTML"` — non-digest callers cannot override | `src/bot/telegram_delivery.py:73` | OPEN (carry-forward Cycle 1) |
| CODE-3 | `handle_digest` sends `content_md` via `send_text(HTML)` — historical Markdown rows may garble on delivery | `src/bot/handlers.py:164` | OPEN (carry-forward Cycle 1) |
| CODE-4 | Bare `except Exception as e` in insights block logs WARNING but swallows full traceback — root cause invisible in logs | `src/output/generate_digest.py:461-462` | OPEN (carry-forward Cycle 1) |
| CODE-6 | `handle_run_digest` calls `generate_recommendations()` after `run_digest()` already called `run_recommendations()` internally — duplicate recommendations delivery | `src/bot/handlers.py:428-429` | NEW |
| CODE-8 | `quality_metrics` table created by migration and never populated — digest runs produce no observability row | `src/db/migrate.py:127-143`, `src/output/generate_digest.py` | NEW |

---

## P3 Issues

| ID | Description | Files | Status |
|----|-------------|-------|--------|
| CODE-5 | No delay between digest send and insights send — Telegram rate limit may silently drop second message | `src/output/generate_digest.py:447-462` | OPEN (carry-forward Cycle 1) |
| CODE-7 | `scoring.yaml cluster_coherence` documented as an active weight but permanently stubbed at 0.5 — misleads future operators | `src/config/scoring.yaml:31`, `src/processing/score_posts.py:215-216` | NEW |
| ARCH-3 | `docs/architecture.md` has no mention of scoring engine, new DB columns, or `quality_metrics` table | `docs/architecture.md` | NEW |
| ARCH-4 | `scoring.yaml cluster_coherence` references non-existent per-post silhouette data | `src/config/scoring.yaml:31`, `src/processing/score_posts.py:215-216` | NEW (same root as CODE-7) |
| ARCH-5 | `docs/spec.md` section 11 prompt contract not updated for T27 variable rename | `docs/spec.md:419` | NEW |

---

## Carry-Forward Status

| ID | Sev | Description | Status | Change |
|----|-----|-------------|--------|--------|
| CODE-2 | P2 | `send_text()` hardcodes `parse_mode="HTML"` globally | OPEN | No change — risk partially mitigated (digest is now HTML per T19/T27), but non-digest paths still unguarded |
| CODE-3 | P2 | `handle_digest` sends `content_md` via HTML parse_mode | OPEN | No change — new digests are HTML, historical Markdown rows still at risk |
| CODE-4 | P2 | `except Exception` in insights block swallows traceback | OPEN | No change — `exc_info=True` not added |
| CODE-5 | P3 | No delay between digest and insights send | OPEN | No change — `time.sleep()` not added |

---

## Stop-Ship Decision

**Yes.**

CODE-1 (P1) is a phase-blocking finding per Cycle 2 protocol: a P1 finding in unreviewed Phase 19 code forces phase BLOCKED status. T24 acceptance criterion ("at least 1 unit test covering bucket assignment logic") is unmet. Phase 19 cannot be marked `[x]` and Cycle 2 cannot be closed until `tests/test_score_posts.py` and `tests/test_generate_digest.py` exist and pass.

No P0 findings exist. All other findings are P2/P3 and do not independently block the phase, but CODE-6 (P2, duplicate delivery) and CODE-8 (P2, quality_metrics never populated) should be fixed in the same batch as CODE-1 to avoid a third review cycle for trivial issues.

---
