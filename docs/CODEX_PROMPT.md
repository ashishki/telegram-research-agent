# CODEX_PROMPT — Session Handoff
_v1.0 · 2026-03-21 · telegram-research-agent_

---

## Current State

- Phase: 18 (active — Focused Intel Redesign)
- Baseline: 12 passing tests
- Ruff: not enforced (pre-playbook project)
- Last CI: green (added 2026-03-21)

## Next Task

T18 — Curated projects config

## Fix Queue

empty

## Open Findings

- CODE-2 (P2): src/bot/telegram_delivery.py:73 — parse_mode="HTML" global; LLM may return Markdown, render may mangle
- CODE-3 (P2): src/bot/handlers.py:164 — handle_digest sends Markdown content via HTML parse_mode
- CODE-4 (P2): src/output/generate_digest.py:411 — bare except Exception swallows DB errors in insights block

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
