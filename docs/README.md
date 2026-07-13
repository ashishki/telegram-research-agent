# Documentation Map

Version: 2.2
Last updated: 2026-07-13
State: documentation index

This directory keeps current operator and implementation guidance at the top
level. Historical reports, old roadmap snapshots, portfolio writeups, and
baseline examples live under `docs/archive/`.

## Canonical Docs

| File | Role |
|---|---|
| `intelligence_report_v2_audit.md` | W29 reader-value, period, reaction, Radar, thread, visualization, and quality-gate audit |
| `intelligence_report_v2_roadmap.md` | Active IRX-0..IRX-14 Report V2 product-correction queue |
| `intelligence_report_v2_contract.md` | Reader-facing Brief V2, Atlas V2, and Knowledge Audit Explorer product contract |
| `weekly_run_manifest.md` | Completed-period and same-run artifact identity/state contract |
| `reaction_personalization_contract.md` | Weak reaction personalization, mapping, receipt, and approval rules |
| `static_visualization_system.md` | Deterministic offline visual component contracts for Brief and Atlas |
| `portfolio_grade_intelligence_roadmap.md` | Broader product, architecture, evaluation, and portfolio-readiness roadmap; IRX supersedes its immediate dogfood order |
| `tasks.md` | Compact active IRX backlog plus historical PGI records |
| `intelligence_evaluation_framework.md` | Evaluation layers, annotation protocol, and weekly scorecard |
| `portfolio_evidence_plan.md` | Portfolio readiness gate and evidence artifacts |
| `mvp_radar_integration_contract.md` | Cross-repo contract with Demand-to-MVP Radar |
| `operator_ai_systems_learning_roadmap.md` | 4-6 month AI Systems learning roadmap tied to PGI implementation tasks |

## Supporting Architecture And Operations

| File | Role |
|---|---|
| `architecture.md` | Current system architecture and memory surfaces |
| `spec.md` | Implementation-facing system specification and maintenance lanes |
| `operator_workflow.md` | Weekly operator workflow for Brief, Atlas, Hermes, feedback, and Radar |
| `mvp_weekly_radar.md` | Existing Radar bridge, market/business context sidecar, KIR/RVE gates, and credentials |
| `mvp_skill_research_sources.md` | Locally installed Codex/Claude research skills for auxiliary MVP source discovery and gate-safe usage |
| `dogfood_4_week_plan.md` | Supporting dogfood protocol, blocked until the IRX-14 start gate |
| `report_format.md` | Legacy weekly artifact contracts and source-link requirements |
| `curated_semantic_retrieval.md` | HPI-9-lite retrieval decision: curated deterministic+SQLite FTS; raw/vector RAG deferred |
| `research_brief_receipt.md` | Research Brief receipt audit contract |
| `telegram_channel_intelligence.md` | Channel Intelligence design and implemented local inspection/report surfaces |
| `memory_architecture.md` | Memory model |
| `memory_inspection.md` | Memory/debug inspection CLI |
| `ops-security.md` | VPS, Telegram credential, and service security guidance |
| `dev-cycle.md` | AI-assisted development workflow |
| `IMPLEMENTATION_CONTRACT.md` | Engineering rules for future changes |
| `COGNITION_MANIFEST.md` | Repo-local cognition map and source-of-truth rules |
| `VPS_COGNITION_VAULT.md` | Shared VPS vault location and sync policy |
| `CODEX_PROMPT.md` | Current compact session handoff |
| `artifacts/README.md` | Versioned generated artifacts selected for review |

## Historical Or Superseded Roadmaps

| File | Current role |
|---|---|
| `next_development_roadmap.md` | Superseded implementation record for receipt/source-trust/report-quality/Radar/cost work |
| `report_quality_roadmap.md` | Historical implementation record for report-quality and Radar handoff tasks |
| `ai_knowledge_intelligence_roadmap.md` | Component roadmap and historical KIR quality record |
| `ai_intelligence_workbook_roadmap.md` | Superseded workbook roadmap and KIR-Q0..KIR-Q13 record |
| `hermes_pi_assistant_roadmap.md` | Hermes/PI component roadmap and implementation record |
| `PROJECT_PLAN.md` | Historical strategy snapshot; canonical strategy moved to portfolio roadmap |
| `pathway_live_source_intelligence.md` | Historical/supporting Pathway live-source context plan |

## Prompt Docs

`docs/prompts/` contains active LLM prompts used by the runtime pipeline and the
development workflow. These are not archive material.

## Audit Docs

`docs/audit/AUDIT_INDEX.md` is the active audit index. Historical audits are
under `docs/archive/legacy_audit/` and `docs/archive/reviews/`.

## Archive

See `docs/archive/README.md` for archived material:

- old baseline snapshots;
- old roadmaps;
- case study and demo walkthrough;
- session reports;
- legacy audit material.
