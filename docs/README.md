# Documentation Map

This directory keeps active operator and implementation guidance at the top level. Historical reports, old roadmap snapshots, portfolio writeups, and baseline examples live under `docs/archive/`.

## Active Docs

| File | Role |
|---|---|
| `architecture.md` | Current system architecture and memory surfaces |
| `spec.md` | Implementation-facing system specification and maintenance lanes |
| `operator_workflow.md` | Weekly workflow, operator feedback, `log-usefulness`, tuning, and troubleshooting |
| `report_format.md` | Weekly artifact contracts, boundaries, and Telegram source-link requirements |
| `mvp_weekly_radar.md` | Demand-to-MVP Radar bridge, source-mix contract, and live-source credentials |
| `research_brief_receipt.md` | Research Brief receipt audit contract with implemented SQLite schema/storage helpers for evidence window, source set, model/config, artifacts, delivery, and verification status; generation, delivery updates, verification, and CLI inspection remain planned |
| `telegram_channel_intelligence.md` | Planned Channel Intelligence design for narratives, repeated claims, source trust signals, entity/topic links, and project relevance |
| `memory_architecture.md` | Implemented four-tier memory design |
| `memory_inspection.md` | Memory/debug inspection CLI for evidence, decisions, snapshots, suppression, and project signals |
| `ops-security.md` | VPS, Telegram credential, and service security guidance |
| `dev-cycle.md` | AI-assisted development workflow for this repo |
| `tasks.md` | Current backlog and implemented-state checklist |
| `IMPLEMENTATION_CONTRACT.md` | Engineering rules for future changes |
| `COGNITION_MANIFEST.md` | Repo-local cognition map and source-of-truth rules |
| `VPS_COGNITION_VAULT.md` | Shared VPS vault location and sync policy |
| `CODEX_PROMPT.md` | Current session handoff and active repo state summary |

## Prompt Docs

`docs/prompts/` contains active LLM prompts used by the runtime pipeline and the development workflow. These are not archive material.

## Audit Docs

`docs/audit/AUDIT_INDEX.md` is the active audit index. Historical audits are under `docs/archive/legacy_audit/` and `docs/archive/reviews/`.

## Archive

See `docs/archive/README.md` for archived material:

- old baseline snapshots
- old roadmaps
- case study and demo walkthrough
- session reports
- legacy audit material
