# CODEX_PROMPT — Session Handoff
_v3.3 · 2026-05-01 · telegram-research-agent_

---

## Current State

- Memory unification and Roadmap v3 are complete.
- Recent shipped changes:
  - Telegram reaction sync imports source-post reactions as tags/feedback.
  - Implementation Ideas now send inline feedback cards and record decisions in `decision_journal`.
  - Empty/low-signal digest health alerts are included in delivery notifications.
  - `src/config/projects.yaml` has current project context for active repos.
  - README/docs were cleaned; historical material moved under `docs/archive/`.
- Active work is maintenance/backlog driven from `docs/tasks.md`.
- In this environment, `pytest` may be unavailable; verified fallback is `PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest ...`.
- Orchestrator-to-Codex execution path: write prompt to file, then `codex exec -s workspace-write < /tmp/prompt.md`

---

## What Exists

- Telegram ingestion, normalization, scoring, and topic assignment
- project relevance, personalization, and weekly report generation
- explicit feedback and tagging
- derived `channel_memory` and `project_context_snapshots`
- `signal_evidence_items` and `decision_journal` tables (unified memory)
- implementation-idea triage and rejection memory
- scope-first retrieval helpers
- autonomous signal discovery via preference judge (category + confidence gate)

---

## Known Open Issues

- Live validation still needed for Telegram reaction visibility through Telethon.
- Live validation still needed for inline callback handling in the deployed bot process.
- Low-signal weeks now produce alerts, but long-term quality trend reporting is still backlog work.

---

## Active Architecture State

The weekly pipeline now has:
- project context snapshots (GitHub-derived)
- channel memory
- decision journal
- evidence items
- preference judge with generous inclusion policy

---

## Exact Next Execution Step

No active phase. Use `docs/tasks.md` as the maintenance backlog.

Before implementation, define scope, touched files, acceptance criteria, and verification command.

Reference documents:

- `docs/tasks.md`
- `docs/IMPLEMENTATION_CONTRACT.md`
- `docs/architecture.md`
