# Current Backlog

**Status:** Active lightweight backlog
**Last updated:** 2026-05-31

The historical memory-unification roadmap is complete and archived at
`docs/archive/roadmaps/tasks-v5-memory-unification.md`.

Detailed next-roadmap context lives in
`docs/next_development_roadmap.md`.

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
- Core-compatible Research Brief receipt adapter, weekly audit-note hash wiring,
  and `memory inspect-core-receipt` for delivered briefs

## Active Maintenance Queue

| ID | Priority | Task | Notes |
|---|---:|---|---|
| ENT-CORE-1 | P0 | Add Core evidence lookup checks for delivered Research Brief receipts | Verify `signal_evidence_item:<id>` refs resolve locally and Telegram source links have valid post URL shape; no Core runtime dependency |
| ENT-CORE-2 | P0 | Add Core receipt schema compatibility checks | Pin required Core-compatible fields/types and deterministic hash behavior before future receipt-field changes |
| ENT-CORE-3 | P0 | Preserve product-local receipt boundaries | Keep usefulness, delivery, Telegram source parsing, operator review, and digest generation local; Core remains derived proof vocabulary |
| TRUST-1 | P1 | Surface source down-rank explanations | Show observed reasons for noisy/down-ranked sources from local reactions, scores, source links, claim outcomes, and project relevance |
| RPT-1 | P1 | Add monthly operator report | Summarize reactions, inline decisions, usefulness, costs, empty/low-signal receipts, and fallback delivery |
| OPS-1 | P1 | Validate reaction sync against live Telegram channels | Confirm current user reactions are visible through Telethon in production |
| OPS-2 | P1 | Validate inline button callbacks in deployed bot polling | Requires bot process to run with callback updates enabled |
| FBK-1 | P2 | Add artifact-level feedback | Let operator mark specific sections/items/artifacts beyond weekly usefulness logs |
| PROD-1 | P2 | Define product split decision gate | Decide whether Telegram Channel Intelligence deserves a separate product workspace only after repeated operator value |

## Parking Lot

- Public/product UI after `PROD-1` passes.
- Referee pass for high-impact claims after source-trust explanations are
  inspectable.
- Productized Telegram Channel Intelligence repo or workspace after repeated
  operator value is demonstrated.
