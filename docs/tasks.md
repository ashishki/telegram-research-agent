# Current Backlog

**Status:** Active lightweight backlog
**Last updated:** 2026-05-29

The historical memory-unification roadmap is complete and archived at
`docs/archive/roadmaps/tasks-v5-memory-unification.md`.

## Current State

Implemented:

- Telegram ingestion and normalized post storage
- deterministic scoring and project relevance
- reaction-based feedback sync for original Telegram posts
- inline Telegram feedback cards for implementation ideas
- compact Implementation Ideas feedback cards capped for Telegram scanning
- integration-style bot polling callback dispatch test around `bot.run_bot`
- weekly Research Brief, Implementation Ideas, and Study Plan
- README and active docs aligned with current delivery/feedback behavior
- evidence memory via `signal_evidence_items`
- Implementation Ideas evidence guard: parsed `[Implement]` / `[Build]` ideas without concrete source post URLs render an insufficient-evidence note instead of actionable recommendations
- decision continuity via `decision_journal`
- operator-authored weekly usefulness logs via `weekly_usefulness_logs`
- project context snapshots
- low-signal / empty digest health alerts
- weekly quality trend from Research Brief receipt health alerts in `score-stats`
- monthly `projects.yaml` review guardrail in `health-check`
- memory inspection CLI
- Telegram Channel Intelligence design, schema migrations, deterministic repeated-claim extraction, canonical source-observation refresh, active-project intelligence links, narrative candidate refresh, inspection CLI, and optional Markdown report surface captured in `docs/telegram_channel_intelligence.md`
- Research Brief receipt SQLite schema, storage helpers, generation-time creation, delivery ref updates, deterministic verification checks, CLI inspection, operator review, and optional operator-only audit notes via `research_brief_receipts`

## Active Maintenance Queue

| ID | Priority | Task | Notes |
|---|---:|---|---|
| OPS-1 | P1 | Validate reaction sync against live Telegram channels | Confirm current user reactions are visible through Telethon in production |
| OPS-2 | P1 | Validate inline button callbacks in deployed bot polling | Requires bot process to run with callback updates enabled |

## Parking Lot

- More granular artifact-level feedback beyond the weekly usefulness log.
- Monthly operator report summarizing reactions, button decisions, cost, and low-signal alerts.
- Better surfaced reasons when a source is repeatedly down-ranked.
- Productized Telegram Channel Intelligence can split later if weekly operator use proves repeated value.
