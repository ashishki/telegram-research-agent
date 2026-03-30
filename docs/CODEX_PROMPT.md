# CODEX_PROMPT — Session Handoff
_v1.2 · 2026-03-30 · telegram-research-agent_

---

## Current State

- Phase: 19 (active — P2 batch fixes in progress)
- Baseline: 37 passing tests (updated 2026-03-30 after T28)
- Ruff: not enforced (pre-playbook project)
- Last CI: green (2026-03-30, 37 pass)
- Note: T22–T28 complete. CODE-1 (P1 stop-ship) resolved. P2 batch registered as T29–T33. T34 (LLM_ROUTER, Phase 20) queued after P2 complete.

## Next Task

T29 — Fix CODE-2: `send_text()` parse_mode override (`src/bot/telegram_delivery.py:73`).
Then T30, T31, T32, T33 in order.
After all P2 fixed and light-reviewed: Cycle 3 Deep Review → Phase 19 close → Phase 20 (T34 LLM_ROUTER).

## Fix Queue

empty (FIX-1 resolved by T28)

## Open Findings

| ID | Sev | Description | Files | Status |
|----|-----|-------------|-------|--------|
| CODE-1 | P1 | Zero test coverage for scoring engine and digest rewire — T24 AC unmet, phase BLOCKED | tests/ (missing) | ✅ RESOLVED — T28 (37 tests, 2026-03-30) |
| CODE-2 | P2 | `send_text()` hardcodes `parse_mode="HTML"` — non-digest callers cannot override | src/bot/telegram_delivery.py:73 | OPEN (Cycle 1 carry-forward) |
| CODE-3 | P2 | `handle_digest` sends `content_md` via HTML parse_mode — historical Markdown rows may garble | src/bot/handlers.py:164 | OPEN (Cycle 1 carry-forward) |
| CODE-4 | P2 | `except Exception` in insights block swallows full traceback — `exc_info=True` missing | src/output/generate_digest.py:461-462 | OPEN (Cycle 1 carry-forward) |
| CODE-5 | P3 | No delay between digest send and insights send — Telegram rate limit risk | src/output/generate_digest.py:447-462 | OPEN (Cycle 1 carry-forward) |
| CODE-6 | P2 | `handle_run_digest` calls `generate_recommendations()` after `run_digest()` already sent insights — duplicate delivery | src/bot/handlers.py:428-429 | OPEN (Cycle 2 new) |
| CODE-7 | P3 | `scoring.yaml cluster_coherence` documented as active weight but permanently stubbed at 0.5 — misleading config | src/config/scoring.yaml:31, src/processing/score_posts.py:215-216 | OPEN (Cycle 2 new) |
| CODE-8 | P2 | `quality_metrics` table created by migration but never populated after digest runs | src/db/migrate.py:127-143, src/output/generate_digest.py | OPEN (Cycle 2 new) |

## Completed Phases

- P0: Architecture docs
- P1: DB schema + ingestion bootstrap
- P2: Incremental ingestion
- P3: Normalization
- P4: Clustering (TF-IDF + KMeans)
- P5: Topic detection (LLM labeling via Claude Haiku)
- P6: Digest generation (JSON + Markdown)
- P7: Recommendations
- P8: Study plan
- P9: Project insights
- P10: Telegram bot (long-polling, owner-only)
- P11: Systemd timers
- P12: GitHub integration (sync + crossref)
- P13: Cost tracking
- P14: Quick wins (week bounds, keyword parsing, validation)
- P15: Code consolidation (telegram_delivery.py, report_utils.py, message_url)
- P16: Report schema + multilingual support + cluster diagnostics
- P17: HTML/PDF rendering (Jinja2 + WeasyPrint)

## Instructions for Codex

Read docs/IMPLEMENTATION_CONTRACT.md before starting any task.
Update this file at every phase boundary.
Return: IMPLEMENTATION_RESULT: DONE | BLOCKED
