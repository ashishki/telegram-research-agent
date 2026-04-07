---
# REVIEW_REPORT — Cycle 3
_Date: 2026-03-30 · Scope: T29–T34_

---

## Executive Summary

Cycle 3 targeted T29–T34: the close-out of all Cycle 2 stop-ship P1/P2 findings, plus early Phase 3 scaffolding (T34 router). All six Cycle 2 P1/P2 findings (CODE-1 through CODE-8 excluding CODE-5/7) are confirmed closed. The router and digest delivery pipeline are functional. One new P1 finding (CODE-12) escalates the longstanding CODE-5 rate-limit gap to stop-ship severity. Six additional findings (CODE-9 through CODE-15 minus CODE-12, plus ARCH carry-forwards) were identified across router correctness, dead code, and test coverage gaps.

Phase 1 documentation debt (ARCH-3, ARCH-5, ARCH-7) and the cluster_coherence stub (CODE-7/ARCH-4) remain open but are non-blocking for code correctness. Per-post routing (ARCH-NEW-1) is acknowledged as Phase 3 pre-wiring and requires an explicit label.

**Stop-ship: Yes** — CODE-12 (P1) must be resolved before the next production digest run.

---

## P0 Issues

None this cycle.

---

## P1 Issues

### CODE-12 [P1] — No sleep between digest and insights Telegram sends (escalated from CODE-5)

**Evidence:** `src/output/generate_digest.py:533–548` — `_send_digest_to_telegram_owner()` called at line 534; `send_text()` for insights called at line 546 with no intervening delay. Two back-to-back Telegram Bot API calls to the same `chat_id` with no sleep, no retry, and no backoff. Telegram enforces a 1-message/second per-chat rate limit; consecutive sends without delay will trigger HTTP 429 on the second call. The `except Exception` block at line 547 silently swallows the 429 and drops the insights message.

**Fix required:**
1. Add `time.sleep(1)` between the digest send (line 534) and the insights send block (line 539).
2. For production hardening: wrap both sends with exponential backoff on 429.
3. Add a test asserting `time.sleep` is called between the two sends.

**Status: OPEN — blocking production.**

---

## P2 Issues

| ID | Location | Description | Fix |
|----|----------|-------------|-----|
| CODE-9 | `tests/test_router.py:8–13` | No test for MID tier path; `WATCH_THRESHOLD` (0.45) boundary untested. Neither of the two existing tests uses `signal_score` in 0.45–0.74 range. | Add `test_route_per_post_mid_signal_returns_mid_model` (score=0.6) and `test_route_per_post_watch_threshold_boundary` (score=0.45). |
| CODE-10 | `src/llm/router.py:20` | `route()` silently coerces `signal_score=None` to 0.0 via `float(signal_score or 0.0)`. No log or guard. Callers passing `None` get CHEAP routing silently. | Add guard: raise `ValueError` or emit `LOGGER.warning` before coercion. |
| CODE-11 | `src/bot/handlers.py:15` | Dead import `generate_recommendations` — imported but never called. Introduced by T32 cleanup. Recreates the cognitive precondition for CODE-6. | Remove line 15. Update test mock accordingly. |
| ARCH-1 | `src/llm/vision.py:36` | `vision.py` calls `client.messages.create()` directly via `_get_client()`, bypassing `complete()` retry wrapper. Transient API errors during photo analysis will not be retried. | Add `complete_vision()` in `client.py`; move vision message construction there. |
| ARCH-2 | `src/bot/handlers.py:287–330` | `handle_ask` embeds FTS5 query construction, context assembly, and direct `LLMClient.complete()` call inside a bot handler, violating the "bot handlers deliver only" contract. | Extract to `src/output/generate_answer.py`; handler calls function and sends result. |
| ARCH-NEW-1 | `src/llm/router.py:15–25`, `src/output/generate_digest.py:480` | Per-post routing fully implemented but zero wired call sites. Only `route("synthesis")` called in production. Score-based dispatch path has no integration test coverage. | Label `router.py` as Phase 3 pre-wiring via inline comment. Create Phase 3 task to wire per-post `route(signal_score=score)` calls. |

---

## P3 Issues

| ID | Location | Description | Fix |
|----|----------|-------------|-----|
| CODE-13 | `tests/test_generate_digest.py:59–67` | Word-count gate tests are tautological — tests call `gd.LOGGER.warning()` directly rather than exercising production code. | Replace with test calling `run_digest` with patched `complete()` returning 601-word output; assert `LOGGER.warning` fires from production code. |
| CODE-14 | `src/llm/router.py:28–30` | Unknown model falls back silently to haiku rates via `.get(model, DEFAULT_MODEL_RATES)` with no warning emitted. | Add `LOGGER.warning("Unknown model=%s, using default rates", model)` before `.get()` call. |
| CODE-15 | `tests/test_telegram_delivery.py` | Only one test case. Missing tests for default `parse_mode="HTML"` and `parse_mode=None`. | Add `test_send_text_default_html_parse_mode` and `test_send_text_none_parse_mode`. |
| ARCH-3 | `docs/architecture.md` | No mention of `score_posts.py`, `scoring.yaml`, `quality_metrics`, `llm_usage`, `cluster_runs`, `study_plans`, or `src/llm/router.py`. Phase 1 exit criterion "aligned docs" not met. | Add Component Map entry for `router.py`; add Data Model subsection for new tables and columns; note `scoring.yaml`/`profile.yaml` as Scoring Layer config surface. |
| ARCH-4/CODE-7 | `src/config/scoring.yaml:31`, `src/processing/score_posts.py:215–216` | `cluster_coherence: 0.15` documented as active weight; permanently stubbed at 0.5 in code. Misleads operators tuning the config. | Add explicit comment to `scoring.yaml` stating sub-dimension is stubbed at 0.5 and will not respond to config changes until Phase 2. |
| ARCH-5 | `docs/spec.md` section 19 | `src/llm/` lists only `client.py`; actual tree has `router.py` and `vision.py`. `src/processing/` missing `score_posts.py`. Multiple directories and systemd units absent. Phase 1 exit criterion "aligned docs" not met. | Update section 19 to reflect actual source tree. |
| ARCH-7 | `docs/spec.md:341` | "population is a future step" is stale — T33 implemented `_store_quality_metrics()` called in both exit paths. | Update `spec.md` section 7 `quality_metrics` note to reflect T33 implementation. |
| ARCH-NEW-2 | `src/llm/client.py:133–145`, `src/db/migrate.py:129–143` | LLM cost logging is DEBUG-only; no `total_cost_usd` in `quality_metrics`; cost-per-run not directly queryable. Deferred to Phase 3. | Phase 3: add `week_label TEXT` to `llm_usage` or `total_cost_usd REAL` to `quality_metrics`; wire digest run context to sum costs. |

---

## Carry-Forward Status

| ID | Original Sev | Description | This Cycle | Current Status |
|----|-------------|-------------|------------|----------------|
| CODE-5 | P3 | No delay between digest and insights Telegram sends | Escalated to CODE-12 P1 | OPEN — escalated to P1 |
| CODE-7 | P3 | `cluster_coherence` stub permanently at 0.5, undocumented | No fix in T29–T34 | OPEN — rolled into ARCH-4, P3 |
| ARCH-4 | P3 | `scoring.yaml cluster_coherence` references non-existent per-post silhouette data | No fix observed | OPEN — P3 |
| ARCH-NEW-1 | P2 | Per-post routing unwired; Phase 3 pre-wiring in Phase 1 | No comment/label added | OPEN — P2 |
| ARCH-NEW-2 | P3 | Cost logging DEBUG-only, no queryable cost-per-run | Acknowledged; deferred to Phase 3 | OPEN — P3, deferred |
| ARCH-6 | P3 (original) | Dead import `generate_recommendations` in `handlers.py:15` | Escalated to CODE-11 P2 | OPEN — escalated to P2 |

---

## Stop-Ship Decision

**Stop-ship: Yes.**

CODE-12 is a confirmed production defect: two sequential Telegram sends with no sleep or backoff guarantee the second message (insights) is silently dropped on any production digest run. The 429 error is swallowed by the `except Exception` block at line 547 — failure is invisible to operators. The fix is a one-liner (`time.sleep(1)`) but must be verified with a test before the next scheduled digest run.

No other finding this cycle independently constitutes a stop-ship condition.

**Baseline: 44 passing tests. Locked Cycle 3 baseline.**

---

_End of REVIEW_REPORT — Cycle 3_
