# CODEX_PROMPT — Session Handoff
_v3.3 · 2026-05-01 · telegram-research-agent_

---

## Current State

- Memory unification and Roadmap v3 are complete.
- Recent shipped changes:
  - Telegram reaction sync imports source-post reactions as tags/feedback.
  - Implementation Ideas now send inline feedback cards and record decisions in `decision_journal`.
  - Bot polling callback dispatch has an integration-style unit test around `bot.run_bot`.
  - Implementation Ideas require concrete Telegram source-post links or render an insufficient-evidence note.
  - Weekly Research Brief usefulness can be recorded through `log-usefulness` into `weekly_usefulness_logs`.
  - Empty/low-signal digest health alerts are included in delivery notifications and trended in `score-stats` from Research Brief receipts.
  - README and active docs are aligned with the current delivery/feedback behavior.
  - Telegram Channel Intelligence design, schema migrations, deterministic repeated-claim extraction, canonical source-observation refresh, active-project intelligence links, narrative candidate refresh, inspection CLI, and optional Markdown report surface are captured in `docs/telegram_channel_intelligence.md`.
  - Research Brief receipt schema, storage helpers, generation-time receipt creation, delivery ref updates, deterministic verification checks, CLI inspection, operator review, and optional operator-only audit notes are implemented via `research_brief_receipts`.
  - `src/config/projects.yaml` has current project context for active repos.
  - README/docs were cleaned; historical material moved under `docs/archive/`.
  - Core schema compatibility tests, product-local Core boundary guards,
    artifact-level feedback, monthly operator report, source down-rank
    explanations, OPS validation surfaces, and the product split gate are
    implemented.
- No local implementation tasks remain in `docs/tasks.md`; live Telegram
  validation state is inspectable with `ops-validate`.
- VPS cognition vault: `/srv/codex-entropy/repos/product-3/engineering-cognition-vault`; use it as a downstream navigation layer, not as the source of truth.
- In this environment, `pytest` may be unavailable; verified fallback is `PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest ...`.
- Orchestrator-to-Codex execution path: write prompt to file, then `codex exec -s workspace-write < /tmp/prompt.md`

---

## What Exists

- Telegram ingestion, normalization, scoring, and topic assignment
- project relevance, personalization, and weekly report generation
- explicit feedback and tagging
- operator-authored weekly usefulness logs
- derived `channel_memory` and `project_context_snapshots`
- `signal_evidence_items` and `decision_journal` tables (unified memory)
- implementation-idea triage and rejection memory
- implementation-idea evidence guard for missing/non-Telegram source-post URLs
- scope-first retrieval helpers
- autonomous signal discovery via preference judge (category + confidence gate)

---

## Known Open Issues

- Live validation still needed for Telegram reaction visibility through Telethon.
- Live validation still needed for inline callback handling in the deployed bot process.
- Low-signal weeks now produce alerts and `score-stats` reports recent empty/low-signal receipt trends.

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

No active phase. Use `docs/tasks.md` as the maintenance backlog and
`docs/next_development_roadmap.md` for detailed task scope, acceptance
criteria, and verification guidance.

Before implementation, define scope, touched files, acceptance criteria, and verification command.

Reference documents:

- `docs/tasks.md`
- `docs/next_development_roadmap.md`
- `docs/COGNITION_MANIFEST.md`
- `docs/VPS_COGNITION_VAULT.md`
- `docs/IMPLEMENTATION_CONTRACT.md`
- `docs/architecture.md`
