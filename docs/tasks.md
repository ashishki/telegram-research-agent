# Current Backlog

**Status:** Active lightweight backlog
**Last updated:** 2026-05-01

The historical memory-unification roadmap is complete and archived at
`docs/archive/roadmaps/tasks-v5-memory-unification.md`.

## Current State

Implemented:

- Telegram ingestion and normalized post storage
- deterministic scoring and project relevance
- reaction-based feedback sync for original Telegram posts
- inline Telegram feedback cards for implementation ideas
- weekly Research Brief, Implementation Ideas, and Study Plan
- evidence memory via `signal_evidence_items`
- decision continuity via `decision_journal`
- project context snapshots
- low-signal / empty digest health alerts
- memory inspection CLI

## Active Maintenance Queue

| ID | Priority | Task | Notes |
|---|---:|---|---|
| DOC-1 | P1 | Keep README and docs map aligned with runtime behavior | Update after delivery/feedback changes |
| OPS-1 | P1 | Validate reaction sync against live Telegram channels | Confirm current user reactions are visible through Telethon in production |
| OPS-2 | P1 | Validate inline button callbacks in deployed bot polling | Requires bot process to run with callback updates enabled |
| QUAL-1 | P2 | Add weekly quality trend from digest health alerts | Track empty/low-signal weeks over time |
| QUAL-2 | P2 | Review project config monthly | Keep `src/config/projects.yaml` current with active repo direction |
| UX-1 | P2 | Tune Implementation Ideas card text | Ensure cards are short enough to act on without opening Telegraph |
| TEST-1 | P2 | Add integration-style callback test around `bot.run_bot` update dispatch | Unit tests cover callback recording, not the long-poll loop end to end |

## Parking Lot

- More granular artifact-level feedback for the Research Brief itself.
- Monthly operator report summarizing reactions, button decisions, cost, and low-signal alerts.
- Better surfaced reasons when a source is repeatedly down-ranked.
