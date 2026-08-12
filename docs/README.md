# Documentation Index

Status: active
Last updated: 2026-08-12

## Current Product Direction

- docs/PROJECT_BRIEF.md
- docs/ARCHITECTURE.md
- docs/IMPLEMENTATION_CONTRACT.md
- docs/adr/ADR-001-product-pivot-to-personal-research-memory.md
- docs/personal_research_memory_product_contract.md
- docs/professional_personalization_contract.md
- docs/prm_operator_experience_audit.md
- docs/prm_operator_experience_roadmap.md
- docs/prm19_dogfood_plan.md
- docs/operator_quickstart.md
- docs/personal_research_memory_architecture.md
- docs/personal_research_memory_roadmap.md
- docs/PRODUCT_OPERATING_MODEL.md
- docs/final_acceptance_plan.md

## Playbook Governance

- docs/playbook_retrofit_audit.md
- docs/tasks.md
- docs/CODEX_PROMPT.md
- docs/DECISION_LOG.md
- docs/IMPLEMENTATION_JOURNAL.md
- docs/EVIDENCE_INDEX.md
- docs/REVIEW_POLICY.md
- .playbook/project_verification.json
- .playbook/delivery_execution_model.json

## RAG, Assistant, Cost, Privacy, Operations

- docs/RAG_DATA_READINESS.md
- docs/retrieval_eval.md
- docs/generation_eval.md
- docs/tool_eval.md
- docs/agent_eval.md
- docs/AGENT_HARNESS_DESIGN.md
- docs/COST_BUDGET.md
- docs/ai_cost_architecture.md
- docs/AUTONOMOUS_WORKFLOW_CONTRACT.md
- docs/PRIVACY_THREAT_MODEL.md
- docs/ROLLBACK_AND_REINDEX_PLAN.md
- docs/repo_hygiene_and_archive_plan.md

## Current Runtime Boundary

- docs/PRODUCT_OPERATING_MODEL.md
- docs/audit/PRM_RUNTIME_FREEZE_2026-07-29.md
- docs/audit/PRM_MANUAL_TELEGRAM_ASSISTANT_ACTIVATION_2026-08-11.md
- docs/audit/PRM_MANUAL_ARCHIVE_REFRESH_2026-08-12.md
- docs/audit/PRM_WEEKLY_ARCHIVE_REFRESH_TIMER_2026-08-12.md

The safe `prm-assistant` runtime is active for manual testing only. The live
legacy Telegram bot and old weekly Report V2 timer are stopped and disabled.
The dedicated archive-refresh timer is active for bounded weekly archive
freshness. PRM-19 dogfood has not started.

## Legacy And Compatibility Context

These documents describe prior weekly-report, IRX, Radar, Atlas, or curated-only
assistant work. They are preserved as history or compatibility context and are
not the active product authority:

- docs/architecture.md
- docs/curated_semantic_retrieval.md
- docs/hermes_pi_assistant_roadmap.md
- docs/intelligence_report_v2_roadmap.md
- docs/intelligence_report_v2_contract.md
- docs/intelligence_report_v2_audit.md
- docs/reaction_personalization_contract.md
- docs/weekly_run_manifest.md
- docs/archive/

## Evidence Rule

Candidate docs and tasks may define target behavior. They must not claim that
full-archive RAG, assistant archive search, dogfood success, vector retrieval,
or external skill approval exists until implementation and verification evidence
is recorded.
