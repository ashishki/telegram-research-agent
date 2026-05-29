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
- weekly Research Brief, Implementation Ideas, and Study Plan
- README and active docs aligned with current delivery/feedback behavior
- evidence memory via `signal_evidence_items`
- Implementation Ideas evidence guard: parsed `[Implement]` / `[Build]` ideas without concrete source post URLs render an insufficient-evidence note instead of actionable recommendations
- decision continuity via `decision_journal`
- operator-authored weekly usefulness logs via `weekly_usefulness_logs`
- project context snapshots
- low-signal / empty digest health alerts
- memory inspection CLI
- Telegram Channel Intelligence design captured in `docs/telegram_channel_intelligence.md` (design only; no runtime behavior implemented)
- Research Brief receipt SQLite schema and storage helpers via `research_brief_receipts`; generation, delivery updates, verification, and CLI inspection remain planned

## Active Maintenance Queue

| ID | Priority | Task | Notes |
|---|---:|---|---|
| ENT-3 | P1 | Create Research Brief receipt after generation | Snapshot evidence window, source set, model/config fingerprints, digest ID, artifact paths, and initial health flags |
| ENT-4 | P1 | Update Research Brief receipt delivery refs | Record Telegraph URL, Telegram timestamp/message ID, fallback delivery, and missing artifact flags after delivery |
| ENT-5 | P1 | Add deterministic receipt verification checks | Validate source links, evidence IDs, artifact refs, config fingerprints, usage refs, low-signal flags, and broad fallback visibility |
| ENT-6 | P2 | Add Research Brief receipt inspection CLI | Inspect by week, receipt ID, digest ID, artifact path, or Telegraph URL; print source of truth, refresh rule, retrieval path, and debug surface details |
| ENT-7 | P2 | Add operator receipt review workflow | Allow verified, waived, needs_review, or failed status with verifier notes; no reader-facing report changes |
| ENT-8 | P3 | Add optional operator-only audit note for receipts | Depends on ENT-6/ENT-7; show concise receipt status/flags only where useful |
| OPS-1 | P1 | Validate reaction sync against live Telegram channels | Confirm current user reactions are visible through Telethon in production |
| OPS-2 | P1 | Validate inline button callbacks in deployed bot polling | Requires bot process to run with callback updates enabled |
| INTEL-2 | P1 | Add Channel Intelligence schema migrations | Design-reviewed tables only for narratives, repeated claims, source observations, entity/topic links, project relevance joins, and weekly rollups; no report behavior changes |
| INTEL-3 | P1 | Implement repeated-claim extraction over scoped evidence | Depends on INTEL-2 and `signal_evidence_items`; validate cross-channel, same-channel, and weak single-occurrence fixtures |
| INTEL-4 | P2 | Implement source observation refresh | Derive counters from canonical posts, evidence, feedback, decisions, and usefulness logs; no model-authored source trust labels |
| INTEL-5 | P2 | Implement entity/topic/project intelligence links | Keep links lightweight and active-project scoped; validate no cross-project leakage |
| INTEL-6 | P2 | Implement narrative candidate refresh and narrative-claim links | Require supporting evidence row IDs and over-aggregation failure fixtures |
| INTEL-7 | P2 | Add Channel Intelligence inspection CLI | Inspect claims, narratives, source observations, and project links with source-of-truth and refresh metadata |
| INTEL-8 | P3 | Add optional Channel Intelligence report surface | Depends on INTEL-7 quality gates; report citations, weak-evidence labels, and input row IDs |
| QUAL-1 | P2 | Add weekly quality trend from digest health alerts | Track empty/low-signal weeks over time |
| QUAL-2 | P2 | Review project config monthly | Keep `src/config/projects.yaml` current with active repo direction |
| UX-1 | P2 | Tune Implementation Ideas card text | Ensure cards are short enough to act on without opening Telegraph |
| TEST-1 | P2 | Add integration-style callback test around `bot.run_bot` update dispatch | Unit tests cover callback recording, not the long-poll loop end to end |

## Parking Lot

- More granular artifact-level feedback beyond the weekly usefulness log.
- Monthly operator report summarizing reactions, button decisions, cost, and low-signal alerts.
- Better surfaced reasons when a source is repeatedly down-ranked.
- Productized Telegram Channel Intelligence can split later if weekly operator use proves repeated value.
