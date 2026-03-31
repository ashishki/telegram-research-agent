# CODEX_PROMPT — Session Handoff
_v2.2 · 2026-03-31 · telegram-research-agent_

---

## Current State

- `Execution model`: Strategic Roadmap v2
- `Current phase`: Phase 4 — Signal-First Output
- `Phase status`: IN PROGRESS — T48–T51 defined, starting implementation
- `Baseline`: 60 passing tests (2026-03-31, after Phase 3 completion)
- `Ruff`: not enforced

## Completed Phases

- **Phase 1**: Baseline stabilization, CODE-12 fix (sleep between sends), conftest.py, CI switched to pytest — T29–T35 done
- **Phase 2**: Scoring Foundation — T36–T41 done (score_run_id, scored_at, score_breakdown, score-stats CLI, MID tier tests, dead import removed)
- **Phase 3**: Model Routing — T42–T47 done (None guard, routed_model in posts, llm_usage table, cost-stats CLI, complete_vision retry, generate_answer extracted)

## Next Tasks

Phase 4 — T48–T51 (see tasks.md Phase 4 task table). Start with T48 (signal_report.py) and work in order.

## Fix Queue

### P1 — Stop-ship (must resolve before next production run)

- FIX-1 [CODE-12] — `src/output/generate_digest.py:534–546`: add `time.sleep(1)` between `_send_digest_to_telegram_owner()` and the insights `send_text()` call. Add test asserting sleep is invoked between sends. Evidence: two back-to-back Telegram sends with no delay; 429 silently swallowed by `except Exception` at line 547.

### P2 — Resolve before Phase 3 router wiring

- FIX-2 [CODE-9] — `tests/test_router.py`: add `test_route_per_post_mid_signal_returns_mid_model` (score=0.6) and `test_route_per_post_watch_threshold_boundary` (score=0.45).
- FIX-3 [CODE-10] — `src/llm/router.py:20`: guard `signal_score=None` — emit `LOGGER.warning` or raise `ValueError` instead of silently coercing to 0.0.
- FIX-4 [CODE-11] — `src/bot/handlers.py:15`: remove dead import `generate_recommendations`. Update test mock accordingly.
- FIX-5 [ARCH-1] — `src/llm/vision.py:36`: add `complete_vision()` in `client.py` with retry wrapper; route `vision.py` through it.
- FIX-6 [ARCH-2] — `src/bot/handlers.py:287–330`: extract `handle_ask` business logic to `src/output/generate_answer.py`.
- FIX-7 [ARCH-NEW-1] — `src/llm/router.py`: add inline comment labeling module as Phase 3 pre-wiring scaffolding; ensure Phase 3 task entry exists for per-post wiring.

### P3 — Phase 1 documentation debt (required for Phase 1 exit)

- FIX-8 [ARCH-3] — `docs/architecture.md`: add Component Map entry for `router.py`; add Data Model subsection for `quality_metrics`, `llm_usage`, `cluster_runs`, `study_plans`; note `scoring.yaml`/`profile.yaml` as Scoring Layer config surface.
- FIX-9 [ARCH-5] — `docs/spec.md` section 19: update artifact structure to reflect actual source tree (add `router.py`, `vision.py`, `score_posts.py`, missing directories, systemd units).
- FIX-10 [ARCH-7] — `docs/spec.md:341`: update `quality_metrics` note — replace “population is a future step” with description of T33 `_store_quality_metrics()` implementation.
- FIX-11 [ARCH-4/CODE-7] — `src/config/scoring.yaml:31`: add comment stating `cluster_coherence` is stubbed at 0.5 and will not respond to config changes until Phase 2.
- FIX-12 [CODE-13] — `tests/test_generate_digest.py:59–67`: replace tautological word-count gate tests with test that calls `run_digest` with patched `complete()` returning 601-word output.
- FIX-13 [CODE-14] — `src/llm/router.py:28–30`: add `LOGGER.warning(“Unknown model=%s, using default rates”, model)` before `.get()` fallback.
- FIX-14 [CODE-15] — `tests/test_telegram_delivery.py`: add `test_send_text_default_html_parse_mode` and `test_send_text_none_parse_mode`.

## Open Findings

| ID | Sev | Description | Status |
|----|-----|-------------|--------|
| CODE-12 | P1 | No sleep between digest and insights Telegram sends; 429 silently dropped | OPEN — stop-ship |
| CODE-9 | P2 | `test_router.py` missing MID tier and WATCH_THRESHOLD boundary tests | OPEN |
| CODE-10 | P2 | `route()` silently coerces `signal_score=None` to 0.0 | OPEN |
| CODE-11 | P2 | Dead import `generate_recommendations` in `handlers.py:15` | OPEN |
| ARCH-1 | P2 | `vision.py` bypasses `complete()` retry wrapper | OPEN |
| ARCH-2 | P2 | `handle_ask` embeds business logic in bot handler | OPEN |
| ARCH-NEW-1 | P2 | Per-post routing unwired; needs Phase 3 pre-wiring label | OPEN |
| CODE-13 | P3 | Word-count gate tests are tautological | OPEN |
| CODE-14 | P3 | Unknown model falls back silently to haiku rates | OPEN |
| CODE-15 | P3 | `test_telegram_delivery.py` missing default HTML and None parse_mode tests | OPEN |
| ARCH-3 | P3 | `architecture.md` missing scoring engine, new tables, router | OPEN — Phase 1 exit blocker |
| ARCH-4/CODE-7 | P3 | `scoring.yaml cluster_coherence` stub undocumented | OPEN |
| ARCH-5 | P3 | `spec.md` section 19 artifact structure stale | OPEN — Phase 1 exit blocker |
| ARCH-7 | P3 | `spec.md:341` quality_metrics “future step” note stale after T33 | OPEN — Phase 1 exit blocker |
| ARCH-NEW-2 | P3 | LLM cost DEBUG-only; no queryable cost-per-run summary | OPEN — deferred to Phase 3 |

## Open Context

- Legacy phases and audit artifacts remain in the repo as historical context
- Any references to `Phase 19`, `Phase 20`, `T29-T34`, or similar should be treated as legacy history, not as the current execution queue
- Current orchestration must derive scope from `docs/tasks.md` Roadmap v2, not from legacy phase numbering
- Cycle 3 baseline: **44 passing tests** — this is the locked entry state

## Legacy History Note

Legacy delivery work completed before Roadmap v2 includes:
- ingestion and normalization pipeline
- topic detection and digest generation
- project insights and recommendations
- scoring and initial routing-related work
- reporting/rendering experiments including HTML/PDF

These are implementation history, not the current phase plan.

## Instructions for Codex / Orchestrator

- Read `docs/tasks.md` first
- Treat `Strategic Roadmap v2` as authoritative for new execution
- Use legacy artifacts only as implementation context
- Do not start Phase 2+ work until Phase 1 entry and exit conditions are satisfied
- Return bounded packets and explicit stop conditions rather than broad “continue implementation” guidance
