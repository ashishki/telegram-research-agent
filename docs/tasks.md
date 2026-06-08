# Current Backlog

**Status:** Active lightweight backlog
**Last updated:** 2026-06-08

The historical memory-unification roadmap is complete and archived at
`docs/archive/roadmaps/tasks-v5-memory-unification.md`.

Detailed next-roadmap context lives in
`docs/next_development_roadmap.md`.

Reader-facing report quality and Demand-to-MVP Radar handoff details live in
`docs/report_quality_roadmap.md`.

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
  `memory inspect-core-receipt` for delivered briefs, and deterministic Core
  evidence lookup checks via `--verify-evidence`
- Core receipt schema compatibility tests and product-local boundary guards
- artifact-level operator feedback via `log-artifact-feedback` and
  `memory inspect-artifact-feedback`
- monthly operator report via `operator-report`
- source down-rank explanations via `memory explain-source-downrank`
- product split gate via `product-split-gate`
- production validation surfaces for reaction sync and inline callbacks via
  `ops-validate`
- deterministic report-quality gates for weekly artifacts via
  `output.report_quality`, digest delivery warnings, Study Plan/Project
  Insights logging, and `operator-report`
- reader-facing Research Brief Decision Brief and Actions header, with early
  What Changed summary and compact Telegram notification funnel/action count

## Active Maintenance Queue

The previous receipt/source-trust/operator-reporting backlog is implemented.
The active queue is now reader-facing report quality and Radar handoff.

| ID | Priority | Task | Notes |
|---|---:|---|---|
| RQ-3 | P0 | Add artifact feedback buttons | Add Research Brief / Implementation Ideas / MVP feedback buttons that write to `artifact_feedback_logs` |
| RQ-4 | P0 | Add reader-facing evidence/source-mix summary | Translate receipt/evidence lookup status into concise operator-facing confidence text |
| RADAR-2 | P0 | Fix Radar final gate contradictions | In `/srv/openclaw-you/workspace/Demand-to-MVP-Radar`, deterministic gates must override LLM text and Markdown/JSON must agree |
| RADAR-1 | P0 | Change Radar output to Candidate Dossier | Radar should render `build/focused_experiment/investigate/reject` status, missing evidence, next experiment, and kill criteria |
| RADAR-3 | P1 | Add Radar source-mix truth surface | Show selected-candidate source mix, missing credentials, and whether Reddit/GitHub evidence is actually primary |
| RADAR-4 | P1 | Add Radar report-quality tests | Lock candidate dossier, source mix, missing evidence, kill criteria, and no-contradiction contract |
| COST-1 | P1 | Dogfood internal LLM cost guardrail sentinel | Budget/spike warnings from existing `llm_usage`, surfaced in `cost-stats` and monthly operator report |
| RQ-5 | P1 | Add weekly artifact consistency contract | Ensure Research Brief, Implementation Ideas, Study Plan, Project Insights, and MVP status agree for the same week |
| MEM-1 | P2 | Add weekly editorial memory | Persist useful/confusing report notes from feedback and quality findings for future report generation |

Implementation details, acceptance criteria, touched-file guidance, and Radar
paths are in `docs/report_quality_roadmap.md`.

Production validation remains inspectable with `ops-validate`. If no live
Telegram reaction or callback event has occurred in the selected window, the
command reports `needs_live_event` rather than storing unverified success.

## Parking Lot

- Public/product UI after `PROD-1` passes.
- Referee pass for high-impact claims after source-trust explanations are
  inspectable.
- Productized Telegram Channel Intelligence repo or workspace after repeated
  operator value is demonstrated.
