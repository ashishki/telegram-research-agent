# Active Task Graph

Status: proposed
Last updated: 2026-08-13
Playbook baseline SHA: 965612aa463fca1a35a55104633d0e09da33d615
Historical Playbook pin retained in prior PRM evidence: 5583eca96c4d2d480b5574ed78bea63e0b07ebf0 (stale)
Target repo inspected for PRM-MAT planning: c282056210c09781cbe45fe00ac2b0008bc35043

## Operating Rules

- Product work now flows through PBR and PRM only.
- Historical IRX work remains preserved in prior roadmaps and git history.
- Do not add new product tasks to IRX.
- New operator-experience work flows through PRM-UX, not IRX and not a second
  autonomous trial task.
- Do not run live Telegram ingestion, reaction sync, Frontier, Radar, report
  generation, full archive LLM backfill, external embeddings, hosted vector
  services, or external web research jobs from backlog grooming. PRM-27 local
  vector sidecar indexing is authorized only inside ADR-004.
- Do not modify production database contents.
- Candidate retrieval queries are not gold evidence until the human operator
  approves expected evidence and citations.
- Human approval is required before accepting the product pivot ADR, changing
  a live runtime boundary, expanding vector work beyond ADR-004 local sidecar, approving
  external skills, or deleting compatibility files.
- Deep review is batched by milestone block. A task-level Critic-Required value
  means the task must be covered by the next block review, not that a separate
  deep-review agent must be run after every task.
- Immediate deep review still blocks continuation for privacy egress, unsafe
  writes, production data migration, vector backend adoption, external skill
  approval, release claims, or deletion/archive of compatibility
  files.

## Current Baseline

| Area | Status |
| --- | --- |
| Repository | Existing product, not greenfield; pre-retrofit commit ad8689fa25b89f77122c4cec7c7a6b9da3f500cf |
| Playbook | Retrofit baseline pin is 5583eca96c4d2d480b5574ed78bea63e0b07ebf0; current Playbook checkout inspected for PRM-UX is 965612aa463fca1a35a55104633d0e09da33d615 |
| Product center | Personal Telegram Research Memory + Grounded Assistant; PRM-UX narrows the next phase to daily operator usefulness, not a new infrastructure wave |
| Full archive search | Bounded SQLite FTS archive search plus PRM-27 local vector sidecar are implemented as local assistant retrieval slices; product RAG gates remain required before live operator validation |
| Current SQLite FTS | Hardened as the persistent baseline for bounded archive search; PRM-27 adds an optional local vector sidecar without replacing FTS |
| PI assistant retrieval | Uses bounded curated and SQLite FTS archive tools; hybrid local vector retrieval is available behind explicit local flags; broad raw corpus provider egress remains forbidden |
| Knowledge Library | Deterministic PRM-13 topic-page DTO and static HTML renderer implemented for bounded supplied topic evidence; not released |
| Project context support | Deterministic PRM-14 assistant tool combines active project descriptors, bounded archive retrieval, and curated knowledge into direct_implication, weak_watch, learning_relevance, or no_match labels without build/code/project mutation approval |
| Local operator UX | `memory ask` gives a local-only evidence brief over bounded archive/curated/project context with no LLM calls, external search, startup migrations, service starts, or writes |
| LLM chat UX | PRM-18A contract, PRM-18B CLI harness, and PRM-18C Telegram UX/runbook implemented; Telegram provider-egress/router flags are enabled for manual testing |
| Research session assistant | Polished project-aware archive-plus-linked-source assistant target is documented by PRM-21; PRM-22 fixture-first linked-source resolver/cache, PRM-23 bounded `memory research` planner, and PRM-27 optional local hybrid retrieval are implemented |
| Learning state | PRM-15 fixture-only migration/projection maps legacy source presence to indexed/surfaced only and requires explicit receipts for opened/read/understood/explained/tried/applied/measured |
| Weekly Brief V3 | PRM-16 deterministic secondary projection and static HTML renderer implemented for bounded supplied context; V1 Brief and Atlas are demoted to compatibility/internal surfaces |
| Runtime workflows | PRM-17 deterministic workflow registry and privacy-safe aggregate telemetry receipt implemented; scheduled runtime activation is not approved |
| Release gate | PRM-18 historical deterministic release receipt remains recorded; current UX work uses explicit operator-test approvals rather than a dogfood gate |
| Runtime deployment | Legacy `telegram-bot.service` and `telegram-ai-split-report.timer` stopped and disabled on 2026-07-29; safe `telegram-prm-assistant.service` is installed/enabled/running for manual operator testing as of 2026-08-11 18:27 CEST; startup migrations remain skipped |
| PRM-13..17 review gate | Batched deep review recorded; one telemetry budget-validation finding fixed before PRM-18 |
| PRM-18A..18C review gate | Batched deep review recorded on 2026-08-03; no unresolved stop-ship finding in this block, residual provider/runtime risks remain gated before PRM-19 |
| W29 reports | V1 Brief and Atlas rendered despite V2 preview code existing elsewhere |
| W29 reactions | Seven personal reactions resolved to posts, zero atoms, zero themes, zero ranking effects |
| Radar | Historical W29 Radar stage failed; PRM-16 V3 fixtures localize Radar failure to the Radar card |
| Operator production tests | Human-run production testing is optional evidence collection and does not block PRM-UX implementation |

## Dependency Graph

```text
PBR-0 -> PBR-1 -> PBR-2 -> PBR-3 -> PBR-4 -> PBR-5
PBR-3/PBR-5 -> PBR-6
PBR-0/PBR-3 -> PBR-7
PBR-2/PBR-3/PBR-4/PBR-5/PBR-6/PBR-7 -> PBR-8

PBR-8 -> PRM-0 -> PRM-1 -> PRM-2 -> PRM-3 -> PRM-4
PRM-3 -> PRM-5 -> PRM-6
PRM-3/PRM-4/PRM-1 -> PRM-7 -> PRM-8 conditional
PRM-4/PRM-5/PRM-7 -> PRM-9 -> PRM-10 -> PRM-11
PRM-10 -> PRM-12 -> PRM-13 -> PRM-14
PRM-5/PRM-12 -> PRM-15 -> PRM-16
PRM-3/PRM-5/PRM-6/PRM-16 -> PRM-17
PRM-10/PRM-11/PRM-12/PRM-16/PRM-17 -> PRM-18
PRM-18 -> PRM-18A -> PRM-18B -> PRM-18C
PRM-18C -> PRM-21 -> PRM-22 -> PRM-23
PRM-23 -> PRM-24 -> PRM-25 -> PRM-26 -> PRM-28 no-vector path
PRM-26 -> ADR-004 -> PRM-27 local vector sidecar
PRM-28 -> PRM-UX-0 -> PRM-UX-1 -> PRM-UX-2 -> PRM-UX-3 -> PRM-UX-4
PRM-UX-4 -> PRM-UX-5 -> PRM-UX-6 -> PRM-UX-7 -> PRM-UX-10
PRM-UX-0 -> PRM-UX-11
PRM-UX-3/PRM-UX-4/PRM-UX-2 -> PRM-UX-8A/8B/8C/8D/8E
PRM-UX-2 -> PRM-UX-9
PRM-UX-10 -> PRM-UX-12 -> PRM-UX-13 -> PRM-20
PRM-19 is optional operator production-test evidence and may inform PRM-20
PRM-24..PRM-28 formalize the required full product RAG path. PRM-26 refines
the older PRM-8 hybrid/vector backend gate. PRM-27 is allowed only inside the
ADR-004 local-sidecar scope: no external embeddings, no hosted vector service,
no canonical DB mutation, and no live web research.
PRM-UX formalizes the required operator-experience and professional
personalization path before operator production tests; it must not restart legacy
bot/report timers or claim user value before real operator labels exist.
```

## PBR Queue - Playbook Retrofit

### PBR-0: Current Playbook Differential Audit

Owner: codex
Phase: PBR
Type: project:governance
Status: implemented
Depends-On: none
Risk-Level: medium
Public-Tests-Required: not_required
Critic-Required: conditional
Holdout-Required: not_required
Mutation-Required: not_required
Property-Required: not_required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Pin the exact target repository and Playbook state, compare copied Playbook surfaces against the current checkout, and classify missing, stale, duplicate, contradictory, or obsolete governance artifacts without changing product code.
Acceptance-Criteria:
  - id: AC-1; description: target and Playbook commit SHAs, branch names, git status, recent logs, diff stats, and tracked file inventory are recorded; verify: docs/playbook_retrofit_audit.md contains the exact pre-edit evidence summary.
  - id: AC-2; description: each required Playbook artifact is classified as present, missing, stale, or conflicting; verify: docs/playbook_retrofit_audit.md includes the artifact matrix.
  - id: AC-3; description: duplicate authority conflicts are named instead of silently resolved; verify: docs/playbook_retrofit_audit.md lists architecture, contract, assistant retrieval, and report-centered conflicts.
Verification:
  - python3 tools/playbook_validate.py --root . --check references
Files:
  - docs/playbook_retrofit_audit.md
  - docs/EVIDENCE_INDEX.md
Context-Refs:
  - docs/product_pivot_current_state_audit.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: any external model or subagent review is requested
Notes: |
  This task is documentation-only and must not run product pipelines.

### PBR-1: Project Brief And Evidence Plan

Owner: codex
Phase: PBR
Type: project:governance
Status: implemented
Depends-On: PBR-0
Risk-Level: high
Public-Tests-Required: not_required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: not_required
Property-Required: not_required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Complete the project brief from the actual operator failure, define adoption failure, first proof metric, evaluation dataset source, human review budget, cost and latency boundaries, and forbidden claims.
Acceptance-Criteria:
  - id: AC-1; description: Project Brief states the operator problem, current workaround, first proof metric, and adoption failure condition; verify: docs/PROJECT_BRIEF.md contains those sections.
  - id: AC-2; description: human review budget and gold-query approval path are explicit; verify: docs/PROJECT_BRIEF.md and docs/RAG_DATA_READINESS.md both state that agent-generated queries are candidates only.
  - id: AC-3; description: unsupported product claims are listed; verify: README.md and docs/CODEX_PROMPT.md do not claim full-archive RAG or dogfood success.
Verification:
  - python3 tools/playbook_validate.py --root . --check placeholders --check references
Files:
  - docs/PROJECT_BRIEF.md
  - README.md
  - docs/CODEX_PROMPT.md
Context-Refs:
  - docs/product_pivot_current_state_audit.md
  - docs/final_acceptance_plan.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: any external model or subagent review is requested
Notes: |
  Human brief approval is required before product implementation starts.

### PBR-2: Safe Standard Retrofit

Owner: codex
Phase: PBR
Type: playbook:retrofit
Status: implemented
Depends-On: PBR-0, PBR-1
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: not_required
Mutation-Required: not_required
Property-Required: conditional
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Reconcile current Playbook validators, schemas, templates, verification contracts, and delivery execution model into the existing repository without force initialization, duplicated authority, or generated private artifacts.
Acceptance-Criteria:
  - id: AC-1; description: initializer help and dry-run behavior are recorded before any retrofit action; verify: docs/playbook_retrofit_audit.md records supported flags and duplicate-risk result.
  - id: AC-2; description: current Playbook validators and schemas exist in the target repository; verify: test -f tools/playbook_validate.py && test -f schemas/task.schema.json.
  - id: AC-3; description: project verification and delivery execution contracts validate against their schemas; test: python3 tools/playbook_validate.py --root . --check readiness --check delivery.
Verification:
  - python3 tools/playbook_validate.py --root . --check readiness --check delivery
Files:
  - tools/playbook_validate.py
  - tools/verify_project.py
  - tools/receipt_run.py
  - schemas/task.schema.json
  - templates/tasks_schema.md
  - .playbook/project_verification.json
  - .playbook/delivery_execution_model.json
Context-Refs:
  - docs/playbook_retrofit_audit.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: initializer would overwrite existing authoritative docs
Notes: |
  No initializer --force, no Claude hooks, and no external skill activation.

### PBR-3: Product Pivot ADR And Implementation Contract

Owner: codex
Phase: PBR
Type: project:governance
Status: implemented
Depends-On: PBR-1, PBR-2
Risk-Level: high
Public-Tests-Required: not_required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: not_required
Property-Required: not_required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Supersede the report-centered contract through a proposed ADR and updated implementation contract that define archive memory, selective enrichment, assistant primacy, privacy boundaries, and human approval requirements.
Acceptance-Criteria:
  - id: AC-1; description: ADR records the old decision, new decision, W29 evidence, privacy implications, migration path, rollback path, and out-of-scope boundaries; verify: docs/adr/ADR-001-product-pivot-to-personal-research-memory.md contains Status proposed.
  - id: AC-2; description: implementation contract no longer states that broad archive memory is rejected; verify: docs/IMPLEMENTATION_CONTRACT.md states full archive search is planned primary memory.
  - id: AC-3; description: product RAG is distinguished from Playbook engineering continuity; verify: docs/IMPLEMENTATION_CONTRACT.md and docs/ARCHITECTURE.md define separate boundaries.
Verification:
  - python3 tools/playbook_validate.py --root . --check references --check placeholders
Files:
  - docs/adr/ADR-001-product-pivot-to-personal-research-memory.md
  - docs/IMPLEMENTATION_CONTRACT.md
  - docs/personal_research_memory_product_contract.md
Context-Refs:
  - docs/product_pivot_current_state_audit.md
  - docs/PROJECT_BRIEF.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: human is asked to accept the ADR
Notes: |
  Do not mark the ADR accepted automatically.

### PBR-4: Architecture, Capability Profiles, Harness, And Runtime Tier

Owner: codex
Phase: PBR
Type: rag:data-readiness tool:schema agent:harness cost:architecture
Status: implemented
Depends-On: PBR-3
Risk-Level: high
Public-Tests-Required: conditional
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: not_required
Property-Required: conditional
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Declare active capability profiles, minimum runtime tier, deterministic versus LLM-owned boundaries, assistant harness shape, and Hermes reuse decision for the pivot product.
Acceptance-Criteria:
  - id: AC-1; description: RAG, Tool-Use, Agentic, Planning, Compliance, Autonomous Workflow, and Cost profiles are explicitly declared with rationale; verify: docs/ARCHITECTURE.md contains the capability profile table.
  - id: AC-2; description: runtime tier is T1 with bounded read-only assistant loop and no T3 dependency; verify: docs/ARCHITECTURE.md and docs/AGENT_HARNESS_DESIGN.md state the tier.
  - id: AC-3; description: Hermes naming boundary classifies official Hermes Agent as pattern_only; verify: docs/ARCHITECTURE.md records the reuse decision.
Verification:
  - python3 tools/playbook_validate.py --root . --check references
Files:
  - docs/ARCHITECTURE.md
  - docs/personal_research_memory_architecture.md
  - docs/AGENT_HARNESS_DESIGN.md
  - docs/agent_eval.md
Context-Refs:
  - docs/IMPLEMENTATION_CONTRACT.md
  - docs/adr/ADR-001-product-pivot-to-personal-research-memory.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: any runtime dependency is proposed
Notes: |
  Agentic is ON only for bounded multi-tool assistant behavior; it is not approval for hidden mutation.

### PBR-5: Delivery Execution Model And Review Policy

Owner: codex
Phase: PBR
Type: project:governance
Status: implemented
Depends-On: PBR-4
Risk-Level: medium
Public-Tests-Required: conditional
Critic-Required: required
Holdout-Required: not_required
Mutation-Required: not_required
Property-Required: not_required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Define Codex Direct bootstrap, split_orchestrated ongoing delivery, optional read-only review loops, Test Critic and privacy review triggers, human completion authority, and task evidence destinations.
Acceptance-Criteria:
  - id: AC-1; description: delivery execution JSON identifies Codex Direct bootstrap and split_orchestrated ongoing delivery; test: python3 tools/playbook_validate.py --root . --check delivery.
  - id: AC-2; description: review policy blocks child agent commits, pushes, self-review, and completion authority; verify: docs/REVIEW_POLICY.md contains those prohibitions.
  - id: AC-3; description: task evidence destinations are listed; verify: docs/REVIEW_POLICY.md and docs/EVIDENCE_INDEX.md name required evidence records.
Verification:
  - python3 tools/playbook_validate.py --root . --check delivery --check references
Files:
  - .playbook/delivery_execution_model.json
  - docs/REVIEW_POLICY.md
  - docs/EVIDENCE_INDEX.md
  - AGENTS.md
Context-Refs:
  - docs/ARCHITECTURE.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: any child agent is granted write capability
Notes: |
  Human remains final completion authority.

### PBR-6: Evaluation, Cost, Privacy, And Skill Governance

Owner: codex
Phase: PBR
Type: rag:data-readiness rag:query rag:generation tool:schema agent:harness eval:gate cost:architecture skill:security
Status: implemented
Depends-On: PBR-3, PBR-5
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Create evaluation, cost, privacy, and external-skill governance contracts that prevent unsupported release claims and block untrusted data egress.
Acceptance-Criteria:
  - id: AC-1; description: retrieval, generation, tool, agent, cost, and privacy contracts exist and identify target metrics as proposed; verify: test -f docs/retrieval_eval.md && test -f docs/generation_eval.md && test -f docs/tool_eval.md && test -f docs/agent_eval.md.
  - id: AC-2; description: candidate query set contains 50 unapproved cases and no gold label claim; verify: python3 -m json.tool is not required; use python to count evals/retrieval/query_set_candidate.jsonl rows and human_approved=false values.
  - id: AC-3; description: external skills are inventoried as disabled, deferred, or rejected until trust records exist; verify: docs/playbook_retrofit_audit.md includes the external skill table.
Verification:
  - python3 tools/playbook_validate.py --root . --check references --check placeholders
Files:
  - docs/RAG_DATA_READINESS.md
  - docs/retrieval_eval.md
  - docs/generation_eval.md
  - docs/tool_eval.md
  - docs/agent_eval.md
  - docs/COST_BUDGET.md
  - docs/ai_cost_architecture.md
  - docs/PRIVACY_THREAT_MODEL.md
  - evals/retrieval/query_set_candidate.jsonl
  - evals/retrieval/README.md
Context-Refs:
  - docs/final_acceptance_plan.md
  - docs/playbook_retrofit_audit.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: any external skill, LLM judge, or embedding provider is proposed
Notes: |
  Candidate queries are not gold evidence.

### PBR-7: Repo Hygiene And Archive Plan

Owner: codex
Phase: PBR
Type: repo:hygiene
Status: implemented
Depends-On: PBR-0, PBR-3
Risk-Level: medium
Public-Tests-Required: conditional
Critic-Required: conditional
Holdout-Required: not_required
Mutation-Required: not_required
Property-Required: not_required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Classify active, compatibility, legacy, generated, private, fixture, historical, oversized, duplicate, stale, and cleanup-candidate files without deleting or moving application files.
Acceptance-Criteria:
  - id: AC-1; description: hygiene plan includes active runtime, assistant/RAG, V1 compatibility, generated private artifacts, fixtures, duplicate docs, stale commands, systemd units, and CI/test baseline categories; verify: docs/repo_hygiene_and_archive_plan.md contains the inventory table.
  - id: AC-2; description: every cleanup candidate lists path, callers, obsolescence reason, evidence needed, earliest milestone, and verification command; verify: docs/repo_hygiene_and_archive_plan.md contains the cleanup candidate table.
  - id: AC-3; description: broad refactor is prohibited before PRM-4 and initial retrieval evaluation; verify: docs/repo_hygiene_and_archive_plan.md states the rule.
Verification:
  - python3 tools/playbook_validate.py --root . --check references
Files:
  - docs/repo_hygiene_and_archive_plan.md
Context-Refs:
  - docs/playbook_retrofit_audit.md
  - docs/ARCHITECTURE.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: deletion, archive, or move is proposed
Notes: |
  Cleanup is planned only; broad refactor waits until PRM search value is proven.

### PBR-8: Playbook Validation And Baseline

Owner: codex
Phase: PBR
Type: eval:gate
Status: implemented
Depends-On: PBR-2, PBR-3, PBR-4, PBR-5, PBR-6, PBR-7
Risk-Level: medium
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: not_required
Property-Required: conditional
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Run the Playbook validators, project verifier, diff checks, and repository baseline commands, then record exact warnings and failures without relabeling them as passes.
Acceptance-Criteria:
  - id: AC-1; description: Playbook validator command is run with tasks, placeholders, readiness, delivery, and references checks; verify: docs/EVIDENCE_INDEX.md records exact result after execution.
  - id: AC-2; description: project verifier command is run or a precise environment blocker is recorded; verify: docs/EVIDENCE_INDEX.md records exact result after execution.
  - id: AC-3; description: git diff check and diff stat are recorded; verify: final handoff includes exact command outcomes.
Verification:
  - python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
  - python3 tools/verify_project.py --root .
  - git diff --check
  - git diff --stat
Files:
  - docs/EVIDENCE_INDEX.md
  - docs/CODEX_PROMPT.md
Context-Refs:
  - docs/REVIEW_POLICY.md
  - docs/PROJECT_BRIEF.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: verifier would run live product pipelines
Notes: |
  This task produces an implementation-ready handoff only if validators do not report unresolved blockers.

## PRM Queue - Personal Research Memory

### PRM-0: Final Product And Acceptance Contract

Owner: codex
Phase: PRM
Type: project:governance
Status: implemented
Depends-On: PBR-8
Risk-Level: high
Public-Tests-Required: conditional
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: not_required
Property-Required: not_required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Freeze the Personal Research Memory v1 user experience, primary workflows, non-goals, final acceptance, and dogfood entry criteria before implementation starts.
Acceptance-Criteria:
  - id: AC-1; description: product contract lists exact, concept, case, comparison, project, timeline, reaction, life, no-answer, and external verification workflows; verify: docs/personal_research_memory_product_contract.md contains all ten workflows.
  - id: AC-2; description: acceptance plan separates data readiness, retrieval, generation, end-to-end, and dogfood levels; verify: docs/final_acceptance_plan.md contains those sections.
  - id: AC-3; description: non-goals prohibit vector-first, public SaaS, full archive LLM backfill, and automatic memory mutation; verify: docs/spec.md contains those non-goals.
Verification:
  - python3 tools/playbook_validate.py --root . --check references --check placeholders
Files:
  - docs/personal_research_memory_product_contract.md
  - docs/final_acceptance_plan.md
  - docs/spec.md
Context-Refs:
  - docs/PROJECT_BRIEF.md
  - docs/IMPLEMENTATION_CONTRACT.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: acceptance thresholds are changed
Notes: |
  Human approval required before PRM-1 moves from planning to implementation.

### PRM-1: Corpus Inventory, Data Readiness, And Gold Query Process

Owner: codex
Phase: PRM
Type: rag:data-readiness
Status: implemented
Depends-On: PRM-0
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: not_required
Property-Required: conditional
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Inventory configured channels and canonical storage sources, measure text and metadata readiness, duplicate and language cases, privacy retention boundaries, and establish the human-approved gold query process without mutating production data.
Acceptance-Criteria:
  - id: AC-1; description: read-only inventory reports counts for retained posts, indexable text, required metadata, empty or malformed rows, duplicates, repost candidates, date coverage, language coverage, and URL coverage; verify: generated PRM-1 evidence report contains all fields.
  - id: AC-2; description: candidate query set remains unapproved and a separate human label workflow is documented; verify: evals/retrieval/query_set_candidate.jsonl rows have human_approved=false and docs/RAG_DATA_READINESS.md states the rule.
  - id: AC-3; description: privacy review confirms no raw Telegram text was written into public fixtures or ordinary logs; verify: grep review over new eval fixtures plus privacy checklist entry.
Verification:
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - read-only SQLite inspection script or command documented in task evidence
Files:
  - docs/RAG_DATA_READINESS.md
  - docs/retrieval_eval.md
  - evals/retrieval/query_set_candidate.jsonl
  - evals/retrieval/README.md
Context-Refs:
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/final_acceptance_plan.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: any sampled post text would leave the local machine
Notes: |
  This is the first implementation task. It is read-only and must not run ingestion, backfill, or indexing.

### PRM-2: Archive Document Identity, Chunking, And Dedupe Contract

Owner: codex
Phase: PRM
Type: rag:ingestion
Status: implemented
Depends-On: PRM-1
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Map existing raw_posts and posts rows into stable searchable document identities, define chunking only for long posts, preserve citations, define content hashes and repost clusters, and specify incremental update and rollback behavior.
Acceptance-Criteria:
  - id: AC-1; description: document identity contract names canonical body source, stable document ID fields, source URL, channel, message ID, date, language, content hash, and duplicate cluster fields; verify: architecture or RAG readiness doc contains the contract.
  - id: AC-2; description: normal Telegram posts remain coherent and long-post chunking preserves exact post-level source links; verify: property tests or design examples cover normal and long post cases.
  - id: AC-3; description: rollback procedure restores prior index state without deleting canonical archive rows; verify: docs/ROLLBACK_AND_REINDEX_PLAN.md is updated with archive document rollback.
Verification:
  - python3 -m pytest tests/ -q
  - python3 tools/playbook_validate.py --root . --check references
Files:
  - src/
  - tests/
  - docs/RAG_DATA_READINESS.md
  - docs/ROLLBACK_AND_REINDEX_PLAN.md
Context-Refs:
  - docs/personal_research_memory_architecture.md
  - docs/PRIVACY_THREAT_MODEL.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: schema migration would touch production database contents
Notes: |
  Do not duplicate full post text into a second store unless measured constraints require an ADR.

### PRM-3: Persistent Full-Archive FTS Search

Owner: codex
Phase: PRM
Type: rag:query
Status: implemented
Depends-On: PRM-2
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Expose every indexable retained post through a persistent SQLite FTS baseline with query, date, channel, language, reaction, and project filters, returning source URL, date, channel, snippet, and stable document identity without Knowledge Atom requirements.
Acceptance-Criteria:
  - id: AC-1; description: search returns retained posts that have no Knowledge Atom when their text matches the query; test: archive search regression test covers an atomless post.
  - id: AC-2; description: result rows include source URL, date, channel, snippet, stable document identity, and optional reaction metadata; test: archive search result schema test checks required fields.
  - id: AC-3; description: p95 local retrieval latency is measured on the approved baseline query subset; verify: retrieval eval report records latency and sample size.
Verification:
  - python3 -m pytest tests/ -q
  - python3 tools/playbook_validate.py --root . --check tasks
Files:
  - src/
  - tests/
  - docs/retrieval_eval.md
Context-Refs:
  - docs/RAG_DATA_READINESS.md
  - docs/retrieval_eval.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: non-FTS backend is proposed
Notes: |
  This is the first user-value implementation milestone.

### PRM-4: Assistant Archive Search Vertical Slice

Owner: codex
Phase: PRM
Type: rag:query tool:schema tool:call
Status: implemented
Depends-On: PRM-3
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add a read-only search_telegram_archive tool to the existing assistant path so exact and concept-like archive queries return grounded Telegram results and insufficient_evidence when the corpus support is weak.
Acceptance-Criteria:
  - id: AC-1; description: assistant tool catalog exposes search_telegram_archive with read-only schema and no mutation fields; test: assistant tool schema test checks allowlist.
  - id: AC-2; description: exact search workflow returns a Telegram source link for a matching retained post; test: vertical slice integration test uses a sanitized fixture.
  - id: AC-3; description: no-answer fixture returns insufficient_evidence and no fabricated citation; test: assistant answer contract test covers no-answer.
Verification:
  - python3 -m pytest tests/ -q
  - python3 tools/playbook_validate.py --root . --check tasks
Files:
  - src/assistant/
  - tests/
  - docs/tool_eval.md
  - docs/generation_eval.md
Context-Refs:
  - docs/AGENT_HARNESS_DESIGN.md
  - docs/personal_research_memory_product_contract.md
Cost-Budget: |
  scope: task
  max_cost_usd: 1.00
  max_model_calls: 10
  max_tool_calls: 40
  max_retries: 1
  approval_required_when: model calls require private raw post text outside bounded retrieval context
Notes: |
  Produce a directly testable user interaction without broad router redesign.

### PRM-5: Reaction Fast Lane

Owner: codex
Phase: PRM
Type: rag:ingestion rag:query workflow:autonomous
Status: implemented
Depends-On: PRM-3
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Ensure every detected personal reaction confirms archive source existence, makes the post searchable immediately, queues enrichment independently, attempts topic linkage, exposes search availability, and records a receipt for each stage.
Acceptance-Criteria:
  - id: AC-1; description: reacted posts remain searchable even when atom extraction fails; test: reaction fast-lane fixture has seven reactions, zero atoms, and seven searchable archive documents.
  - id: AC-2; description: receipt records detected reactions, unique posts, indexed documents, enrichment attempts, successes, failures, topic links, ranking effects, and incomplete-stage reasons; test: receipt schema test checks required fields.
  - id: AC-3; description: no reaction is interpreted as negative and emoji type remains audit metadata only; test: reaction semantics unit test covers absent and multiple emoji cases.
Verification:
  - python3 -m pytest tests/ -q
  - python3 tools/playbook_validate.py --root . --check tasks
Files:
  - src/
  - tests/
  - docs/reaction_personalization_contract.md
  - docs/RAG_DATA_READINESS.md
Context-Refs:
  - docs/product_pivot_current_state_audit.md
  - docs/personal_research_memory_product_contract.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0.50
  max_model_calls: 5
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: reaction data would mutate permanent profile or preferences
Notes: |
  Do not accept seven reactions to zero searchable knowledge items as a completed state.

### PRM-6: Selective Enrichment Pipeline V2

Owner: codex
Phase: PRM
Type: rag:ingestion rag:generation
Status: implemented
Depends-On: PRM-5
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Enrich priority posts with claims, cases, tools, practices, warnings, entities, and topic candidates while preserving source references, separating extraction failure from search availability, and enforcing cheap bounded batches without full archive backfill.
Acceptance-Criteria:
  - id: AC-1; description: enrichment queue priority order covers reactions, repeated search returns, cited answers, watch topics, active projects, repeated signals, and manual saves; test: priority ordering test covers all sources.
  - id: AC-2; description: extraction failure leaves archive search result available and records failure reason; test: enrichment failure fixture remains searchable.
  - id: AC-3; description: cost and retry caps stop a batch before exceeding approved task budget; test: cost cap test simulates retry exhaustion.
Verification:
  - python3 -m pytest tests/ -q
Files:
  - src/
  - tests/
  - docs/COST_BUDGET.md
  - docs/ai_cost_architecture.md
Context-Refs:
  - docs/personal_research_memory_architecture.md
  - docs/COST_BUDGET.md
Cost-Budget: |
  scope: task
  max_cost_usd: 5.00
  max_model_calls: 200
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: full archive backfill or higher-cost model is requested
Notes: |
  No full archive LLM backfill.

### PRM-7: Retrieval Baseline Evaluation And Hybrid ADR

Owner: codex
Phase: PRM
Type: rag:query eval:gate
Status: implemented
Depends-On: PRM-1, PRM-3, PRM-4
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: not_required
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Run the human-approved gold query set against the FTS baseline, classify retrieval failures, decide whether embeddings or hybrid retrieval are justified, compare vector backend candidates, and record a human-approved ADR before vector implementation.
Acceptance-Criteria:
  - id: AC-1; description: evaluation uses only human-approved gold labels and reports which candidate queries remain unapproved; verify: retrieval eval output separates gold and candidate rows.
  - id: AC-2; description: metrics include hit@10, MRR, citation precision, stale rejection, no-answer accuracy, duplicate top-10 rate, latency, and reacted-post searchability; verify: docs/retrieval_eval.md contains the metric table and result path.
  - id: AC-3; description: vector backend ADR compares recall, latency, update complexity, privacy, backup, overhead, cost, and repository fit; verify: ADR exists only after evaluation evidence is attached.
Verification:
  - python3 -m pytest tests/ -q
  - retrieval eval command documented in evidence report
Files:
  - evals/retrieval/
  - docs/retrieval_eval.md
  - docs/adr/
Context-Refs:
  - docs/retrieval_eval.md
  - docs/RAG_DATA_READINESS.md
  - docs/PRIVACY_THREAT_MODEL.md
Cost-Budget: |
  scope: task
  max_cost_usd: 2.00
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: embeddings or external provider calls are proposed
Notes: |
  No vector backend implementation before this task demonstrates need.

### PRM-8: Hybrid Retrieval And Reranking

Owner: codex
Phase: PRM
Type: rag:query
Status: implemented
Depends-On: PRM-7
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Implement hybrid retrieval only when PRM-7 approves it, combining metadata filters, FTS, vector candidates, dedupe, freshness, diversity, reaction and project boosts, bounded reranking, index versioning, and rollback.
Acceptance-Criteria:
  - id: AC-1; description: task does not start unless the hybrid ADR is human-approved; verify: implementation evidence references accepted ADR status.
  - id: AC-2; description: hybrid retrieval improves approved metrics against FTS baseline without reducing citation precision below target; test: retrieval eval comparison command reports both baseline and hybrid metrics.
  - id: AC-3; description: corpus/index version, reindex command, rollback command, and backup path are recorded; verify: docs/ROLLBACK_AND_REINDEX_PLAN.md contains hybrid sections.
Verification:
  - python3 -m pytest tests/ -q
  - retrieval eval comparison command documented in evidence report
Files:
  - src/
  - tests/
  - evals/retrieval/
  - docs/ROLLBACK_AND_REINDEX_PLAN.md
Context-Refs:
  - docs/retrieval_eval.md
  - docs/PRIVACY_THREAT_MODEL.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 until human-approved hybrid budget is recorded
  max_model_calls: 0 until human-approved hybrid budget is recorded
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: embeddings provider, vector backend, or reranker changes
Notes: |
  SQLite archive remains canonical.

### PRM-9: Assistant Intent Router And Bounded Tool Catalog

Owner: codex
Phase: PRM
Type: tool:schema tool:call agent:harness agent:termination
Status: implemented
Depends-On: PRM-4, PRM-5, PRM-7
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Route exact search, concept search, cases, comparison, news, project application, reaction recall, no-answer, and external verification through one conversational entrypoint with bounded read-only tools, trace records, and termination.
Acceptance-Criteria:
  - id: AC-1; description: tool catalog includes all minimum read-only tools and confirmation-gated proposal tools, with no automatic mutation tools; test: tool catalog allowlist test.
  - id: AC-2; description: deterministic routing covers exact search, reaction recall, and no-answer when sufficient; test: router fixture tests for required intents.
  - id: AC-3; description: tool traces record selected tool, arguments, result count, termination reason, and privacy boundary; test: assistant trace schema test.
Verification:
  - python3 -m pytest tests/ -q
Files:
  - src/assistant/
  - tests/
  - docs/AGENT_HARNESS_DESIGN.md
  - docs/tool_eval.md
Context-Refs:
  - docs/AGENT_HARNESS_DESIGN.md
  - docs/tool_eval.md
Cost-Budget: |
  scope: task
  max_cost_usd: 2.00
  max_model_calls: 20
  max_tool_calls: 120
  max_retries: 1
  approval_required_when: router adds hidden mutation or unbounded loop
Notes: |
  The user must not choose between Hermes, PI, Atlas, Radar, or separate search systems.

### PRM-10: Grounded Answer Generation

Owner: codex
Phase: PRM
Type: rag:generation
Status: implemented
Depends-On: PRM-9, PRM-7
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Synthesize answers from retrieved evidence with exact Telegram citations, archive-versus-model distinction, freshness, contradictions, insufficient_evidence behavior, and separate retrieval and generation latency and cost telemetry.
Acceptance-Criteria:
  - id: AC-1; description: answers contain direct answer, archive support, source links, uncertainty, date boundary, model background, external verification needs, and optional next action; test: answer contract fixture test.
  - id: AC-2; description: unsupported archive claims are rejected or labeled as model background; test: generation eval fixture with missing source support.
  - id: AC-3; description: retrieval latency, generation latency, model calls, and cost are recorded separately without raw post text in logs; test: telemetry privacy test.
Verification:
  - python3 -m pytest tests/ -q
Files:
  - src/assistant/
  - tests/
  - docs/generation_eval.md
  - docs/COST_BUDGET.md
Context-Refs:
  - docs/generation_eval.md
  - docs/PRIVACY_THREAT_MODEL.md
Cost-Budget: |
  scope: task
  max_cost_usd: 3.00
  max_model_calls: 30
  max_tool_calls: 100
  max_retries: 1
  approval_required_when: prompt requires broad raw corpus context
Notes: |
  LLM judge output is advisory until calibrated against human labels.

### PRM-11: On-Demand External Verification

Owner: codex
Phase: PRM
Type: tool:schema tool:call
Status: implemented
Depends-On: PRM-9, PRM-10
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add explicit external verification flow for unstable or high-stakes claims, label Telegram evidence separately from external evidence, avoid automatic browsing for every internal query, and store only approved research notes.
Acceptance-Criteria:
  - id: AC-1; description: high-stakes categories trigger a request_external_verification path or a clear requirement label; test: routing fixture for pricing, legal, medical, financial, career-market, and visa questions.
  - id: AC-2; description: answer sections separate archive evidence, external verification, and unknowns; test: external verification answer fixture.
  - id: AC-3; description: external skill use is blocked unless an approved trust record exists; test: tool allowlist test rejects unapproved skill.
Verification:
  - python3 -m pytest tests/ -q
Files:
  - src/assistant/
  - tests/
  - docs/tool_eval.md
  - docs/PRIVACY_THREAT_MODEL.md
Context-Refs:
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/playbook_retrofit_audit.md
Cost-Budget: |
  scope: task
  max_cost_usd: 2.00
  max_model_calls: 20
  max_tool_calls: 80
  max_retries: 1
  approval_required_when: external skill or broad web crawl is requested
Notes: |
  Telegram remains discovery context for unstable facts, not final truth.

### PRM-12: Confirmation-Gated Save And Watch Flow

Owner: codex
Phase: PRM
Type: tool:schema tool:call tool:unsafe
Status: implemented
Depends-On: PRM-10
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: required
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Propose and confirm Knowledge Notes, Watch Topics, project links, decisions, actions, experiments, and feedback with append-only history, no automatic chat transcript memory, and clear edit, delete, and rollback semantics.
Acceptance-Criteria:
  - id: AC-1; description: proposal tools do not write until confirmation token or explicit approval is supplied; test: unsafe tool confirmation test.
  - id: AC-2; description: session chat is not durable memory unless user approves a save proposal; test: transcript persistence test.
  - id: AC-3; description: decision and experiment records are append-only and rollback leaves an audit trail; test: saved memory history test.
Verification:
  - python3 -m pytest tests/ -q
Files:
  - src/assistant/
  - src/
  - tests/
  - docs/tool_eval.md
Context-Refs:
  - docs/personal_research_memory_product_contract.md
  - docs/PRIVACY_THREAT_MODEL.md
Cost-Budget: |
  scope: task
  max_cost_usd: 2.00
  max_model_calls: 20
  max_tool_calls: 100
  max_retries: 1
  approval_required_when: write scope expands beyond confirmed proposal objects
Notes: |
  No profile edits or permanent preference changes from implicit reactions.

### PRM-13: Query-Driven Knowledge Library And Topic Pages

Owner: codex
Phase: PRM
Type: rag:generation
Status: implemented
Depends-On: PRM-10, PRM-12
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Build the Knowledge Library around query-driven or watched Topics, Research Notes, Cases, Tools, Practices, Projects, Decisions, and Experiments while keeping the old global Atlas as an internal Knowledge Audit Explorer.
Acceptance-Criteria:
  - id: AC-1; description: topic pages show current understanding, 30 and 90 day changes, claims, cases, tools, contradictions, project links, saved notes, open questions, and original sources; test: topic page fixture test.
  - id: AC-2; description: global Atlas is labeled as internal audit/debug surface, not primary user product; verify: README and product docs use Knowledge Audit Explorer naming.
  - id: AC-3; description: visual checks confirm no overlapping text on supported desktop and mobile fixtures; verify: Playwright or screenshot evidence attached when UI is changed.
Verification:
  - python3 -m pytest tests/ -q
  - visual verification command documented when UI files change
Files:
  - src/
  - tests/
  - docs/personal_research_memory_product_contract.md
Context-Refs:
  - docs/personal_research_memory_architecture.md
  - docs/final_acceptance_plan.md
Cost-Budget: |
  scope: task
  max_cost_usd: 3.00
  max_model_calls: 30
  max_tool_calls: 80
  max_retries: 1
  approval_required_when: full graph or large frontend application is proposed
Notes: |
  A graph is secondary and only for saved canonical topics.

### PRM-14: Project Context And Decision Support

Owner: codex
Phase: PRM
Type: rag:query rag:generation
Status: implemented
Depends-On: PRM-10, PRM-13
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Combine project descriptors with archive retrieval and curated knowledge to provide concrete evidence-backed project suggestions, distinguishing direct implication, weak watch, learning relevance, and no match.
Acceptance-Criteria:
  - id: AC-1; description: project application answer cites archive evidence and names the project descriptor fields used; test: project context fixture for Eval-Ground-Truth-Lab.
  - id: AC-2; description: weak keyword-only matches are labeled weak_watch or no_match instead of action recommendations; test: project relevance classifier fixture.
  - id: AC-3; description: no automatic MVP build approval or code mutation is exposed; test: tool allowlist rejects project mutation commands.
Verification:
  - python3 -m pytest tests/ -q
Files:
  - src/assistant/
  - tests/
  - docs/tool_eval.md
Context-Refs:
  - docs/personal_research_memory_product_contract.md
  - docs/generation_eval.md
Cost-Budget: |
  scope: task
  max_cost_usd: 2.00
  max_model_calls: 20
  max_tool_calls: 80
  max_retries: 1
  approval_required_when: project context writes are requested
Notes: |
  Demand-to-MVP-Radar remains a related project input, not source of truth for the memory product.

### PRM-15: Learning-State Correction And Migration

Owner: codex
Phase: PRM
Type: data:migration
Status: implemented
Depends-On: PRM-5, PRM-12
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Replace false read inference with indexed, surfaced, opened, read, understood, explained, tried, applied, measured, rejected, and stale states while preserving legacy records and avoiding fabricated historical user actions.
Acceptance-Criteria:
  - id: AC-1; description: migration preserves existing records and maps old source URL or atom presence to indexed or surfaced only; test: migration fixture covers legacy records.
  - id: AC-2; description: opened, read, understood, tried, applied, and measured require explicit evidence receipts; test: learning state transition test rejects inferred upgrades.
  - id: AC-3; description: assistant and reports label no feedback as unknown; test: learning display fixture covers unknown state.
Verification:
  - python3 -m pytest tests/ -q
Files:
  - src/
  - tests/
  - docs/ROLLBACK_AND_REINDEX_PLAN.md
Context-Refs:
  - docs/product_pivot_current_state_audit.md
  - docs/personal_research_memory_product_contract.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0.50
  max_model_calls: 5
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: migration touches production database contents
Notes: |
  Do not fabricate historical read, understood, applied, or measured states.

### PRM-16: Weekly Brief V3 And Legacy Surface Demotion

Owner: codex
Phase: PRM
Type: rag:generation
Status: implemented
Depends-On: PRM-13, PRM-15
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Derive Weekly Brief V3 from Watch Topics, reacted posts, questions, saved notes, active projects, repeated signals, experiments, and feedback while localizing Radar failure and demoting V1 Brief and Atlas surfaces.
Acceptance-Criteria:
  - id: AC-1; description: Brief contains one main change, one ACT item, one STUDY item, one WATCH or IGNORE item, reaction summary, concrete project connection or honest zero, optional Radar card, and feedback request; test: Brief V3 fixture test.
  - id: AC-2; description: generic fallback action phrasing is absent from generated Brief fixtures; test: text regression test rejects generic fallback actions.
  - id: AC-3; description: Radar failure changes only Radar card state and does not invalidate archive search, assistant answers, Knowledge Library, or non-Radar Brief sections; test: Radar failure fixture.
Verification:
  - python3 -m pytest tests/ -q
  - visual verification command documented when renderer files change
Files:
  - src/output/
  - tests/
  - docs/report_format.md
Context-Refs:
  - docs/personal_research_memory_product_contract.md
  - docs/final_acceptance_plan.md
Cost-Budget: |
  scope: task
  max_cost_usd: 3.00
  max_model_calls: 40
  max_tool_calls: 80
  max_retries: 1
  approval_required_when: report generation would process broad archive text through LLM
Notes: |
  Weekly Brief is secondary projection, not knowledge source.

### PRM-17: Runtime, Autonomous Workflows, Observability, Cost, And Rollback

Owner: codex
Phase: PRM
Type: workflow:autonomous cost:telemetry
Status: implemented
Depends-On: PRM-3, PRM-5, PRM-6, PRM-16
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Define scheduled ingestion, indexing, enrichment, and brief routines as idempotent workflows with freshness, queue, retrieval, generation, tool-call, cost, no-answer, backup, reindex, and rollback telemetry that excludes private raw text from logs.
Acceptance-Criteria:
  - id: AC-1; description: workflow contract lists trigger, inputs, outputs, idempotency key, retry policy, fallback, receipt, and rollback for each scheduled routine; verify: docs/AUTONOMOUS_WORKFLOW_CONTRACT.md updated.
  - id: AC-2; description: telemetry records index freshness, queue age, retrieval latency, generation latency, model cost, no-answer rate, and error class without raw post text; test: telemetry privacy fixture.
  - id: AC-3; description: rollback and reindex commands are documented with dry-run or fixture validation; verify: docs/ROLLBACK_AND_REINDEX_PLAN.md updated.
Verification:
  - python3 -m pytest tests/ -q
Files:
  - src/
  - tests/
  - docs/AUTONOMOUS_WORKFLOW_CONTRACT.md
  - docs/COST_BUDGET.md
  - docs/ROLLBACK_AND_REINDEX_PLAN.md
Context-Refs:
  - docs/AUTONOMOUS_WORKFLOW_CONTRACT.md
  - docs/COST_BUDGET.md
  - docs/PRIVACY_THREAT_MODEL.md
Cost-Budget: |
  scope: workflow
  max_cost_usd: 10.00 per week until dogfood budget is approved
  max_model_calls: 500 per week
  max_tool_calls: n/a
  max_retries: 1 per job
  approval_required_when: weekly cost exceeds budget or queue fan-out expands
Notes: |
  Scheduled jobs must be idempotent and recoverable.

### PRM-18: End-To-End Evaluation And Security Review

Owner: codex
Phase: PRM
Type: eval:gate
Status: implemented
Depends-On: PRM-10, PRM-11, PRM-12, PRM-16, PRM-17
Risk-Level: critical
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Run data, retrieval, generation, tool, agent, privacy, cost, UI, and end-to-end evaluations, produce a release receipt, and block dogfood while stop-ship criteria remain.
Acceptance-Criteria:
  - id: AC-1; description: all eleven end-to-end acceptance scenarios have pass, fail, or blocked status with evidence links; verify: final acceptance receipt contains scenario table.
  - id: AC-2; description: Test Critic and privacy review findings are resolved or explicitly accepted by the human; verify: review receipt references approvals.
  - id: AC-3; description: dogfood gate blocks on private-data leakage, unsupported claims, retrieval metric failure, unsafe writes, or cost budget breach; verify: gate output shows blocking reasons.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_prm_release_gate.py -q
  - python3 tools/test_tiers.py focused-prm
  - python3 tools/test_tiers.py fast-contract
  - python3 tools/verify_project.py --root .
  - evaluation and security review commands documented in release receipt
Files:
  - evals/prm_release_gate.py
  - evals/prm18_release_gate_receipt_2026-07-29.json
  - evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json
  - tests/test_prm_release_gate.py
  - tools/test_tiers.py
  - docs/final_acceptance_plan.md
  - docs/PRIVACY_THREAT_MODEL.md
Context-Refs:
  - docs/final_acceptance_plan.md
  - docs/REVIEW_POLICY.md
Cost-Budget: |
  scope: phase
  max_cost_usd: 20.00
  max_model_calls: 300
  max_tool_calls: 500
  max_retries: 1
  approval_required_when: LLM judge, browser verification, or external model fan-out expands
Notes: |
  Implemented as deterministic release-gate aggregation and validation. The
  historical 2026-07-29 PRM-18 receipt blocked dogfood on stop-ship criteria,
  missing final acceptance evidence, and missing human dogfood-start approval.
  The current 2026-08-11 post-PRM28 receipt records deterministic local
  no-vector RAG readiness and clears current stop-ship blockers, but still
  blocks dogfood on missing explicit PRM-19 dogfood-start approval. It does not
  run dogfood or claim release readiness.

### PRM-18A: Operator LLM Chat UX Contract

Owner: codex
Phase: PRM
Type: product:ux
Status: implemented
Depends-On: PRM-18
Risk-Level: high
Public-Tests-Required: required
Critic-Required: conditional
Holdout-Required: not_required
Mutation-Required: not_required
Property-Required: conditional
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Define the operator-facing ChatGPT-like PRM chat workflow over the existing
  PI chat/RAG harness, including explicit provider-egress approval, citation
  display, answer-contract display, privacy flags, local-only fallback, and no
  hidden durable writes.
Acceptance-Criteria:
  - id: AC-1; description: docs define the exact one-shot and interactive commands, default local-only behavior, explicit LLM/provider-egress switch, and user-visible privacy line; verify: docs/operator_workflow.md and README.md contain the command examples.
  - id: AC-2; description: privacy docs distinguish local `memory ask` from LLM-backed chat where bounded Telegram snippets may be sent to the provider; verify: docs/PRIVACY_THREAT_MODEL.md and docs/COST_BUDGET.md contain the distinction.
  - id: AC-3; description: dogfood remains blocked and runtime/service start is not implied by the chat UX contract; verify: docs/PRODUCT_OPERATING_MODEL.md states PRM-19 remains blocked.
Verification:
  - python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
  - git diff --check
Files:
  - README.md
  - docs/operator_workflow.md
  - docs/PRODUCT_OPERATING_MODEL.md
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/COST_BUDGET.md
  - docs/tasks.md
Context-Refs:
  - docs/operator_workflow.md
  - docs/PRODUCT_OPERATING_MODEL.md
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/COST_BUDGET.md
  - src/assistant/pi_chat.py
  - src/assistant/local_memory_ask.py
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: any real provider call, raw/bounded Telegram snippet provider egress, or external skill is requested
Notes: |
  Implemented as a contract/docs task. It did not call providers, run external
  search, start Telegram services, run migrations, or write production DB state.
  The implementation command names are `memory chat` and
  `memory ask --llm-approved`, with an explicit `--allow-provider-egress` style
  switch before private archive snippets can be sent to an LLM.

  Contracted answer display requires answer, sources, archive-support status,
  unknowns or external-verification needs, write status, and the privacy/cost
  line:

  `Privacy: mode=<local-only|llm-approved>; model_calls=<n>; estimated_cost_usd=<usd>; bounded_telegram_snippet_provider_egress=<true|false>; raw_telegram_corpus_egress=false; durable_writes=false`

  PRM-18A is part of the PRM-18A..PRM-18C batched deep review boundary,
  recorded at `docs/audit/PRM_DEEP_REVIEW_PRM18A_18C_2026-08-03.md`.

### PRM-18B: LLM-Backed Memory Chat CLI

Owner: codex
Phase: PRM
Type: product:implementation
Status: implemented
Depends-On: PRM-18A
Risk-Level: high
Public-Tests-Required: required
Critic-Required: conditional
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Implement a user-facing CLI chat harness that feels like a compact ChatGPT
  over personal Telegram memory while reusing the existing `answer_pi_chat`
  tool loop, grounded answer contract, archive search, curated retrieval,
  project context, external-verification requirement, and confirmation-gated
  proposal flow.
Acceptance-Criteria:
  - id: AC-1; description: one-shot LLM mode requires an explicit provider-egress approval switch and otherwise exits or falls back to local `memory ask` with clear copy; test: CLI tests cover both approved and unapproved paths with fake LLM clients.
  - id: AC-2; description: interactive mode supports repeated questions, prints answer, source links, archive-support status, unknowns, privacy flags, and cost/model-call estimate without logging raw Telegram text; test: harness tests assert answer contract and privacy fields.
  - id: AC-3; description: no direct writes occur from chat except existing confirmation-gated `confirm_save_proposal`, and proposal confirmations require exact proposal/token; test: PI chat/tool tests cover write gating and local chat tests assert write_performed=false by default.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_local_memory_ask.py tests/test_pi_chat.py tests/test_cli.py -q
  - python3 tools/test_tiers.py focused-prm
  - python3 tools/test_tiers.py fast-contract
  - python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
  - git diff --check
Files:
  - src/main.py
  - src/assistant/pi_chat.py
  - src/assistant/local_memory_ask.py
  - src/assistant/pi_tools.py
  - tests/test_cli.py
  - tests/test_pi_chat.py
  - tests/test_local_memory_ask.py
  - docs/operator_workflow.md
  - docs/EVIDENCE_INDEX.md
Context-Refs:
  - src/assistant/pi_chat.py
  - src/assistant/pi_tools.py
  - src/assistant/local_memory_ask.py
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/COST_BUDGET.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for implementation and tests
  max_model_calls: 0 for implementation and tests
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: running the new chat against real private archive snippets with a real provider, increasing tool-call fan-out, or adding external-skill calls
Notes: |
  Implemented on 2026-08-03 as a gated CLI wrapper over the existing PI chat
  path. `memory ask --llm-approved` refuses before PI chat execution with exit
  code 2 unless `--allow-provider-egress` is present;
  `memory chat --allow-provider-egress` runs repeated stdin/stdout turns until
  exit/quit commands, `:q`, or EOF.

  CLI answers render a privacy-safe `prm_chat_display.v1` receipt with answer,
  sources, archive-support status, external-verification status, unknowns,
  write status, model calls, estimated cost, bounded-snippet egress, raw corpus
  egress, and durable-write flags. Local-only `memory ask` now prints the same
  privacy/cost line with `mode=local-only`.

  Implementation and tests used fake LLM clients and fixture databases. No live
  provider calls, external search, Telegram services, migrations, or production
  database writes were run.

### PRM-18C: Telegram PRM Assistant UX Parity And Start Runbook

Owner: codex
Phase: PRM
Type: product:runtime
Status: implemented
Depends-On: PRM-18B
Risk-Level: high
Public-Tests-Required: required
Critic-Required: conditional
Holdout-Required: not_required
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Align the safe Telegram `prm-assistant` experience with the CLI chat contract
  so the operator sees the same citations, unknowns, privacy boundary, and
  confirmation-gated save behavior, while keeping any runtime activation
  separate from PRM-19 dogfood-start approval.
Acceptance-Criteria:
  - id: AC-1; description: Telegram start/help commands explain local-only mode, explicit LLM/provider-egress mode, safe commands, blocked legacy commands, and dogfood-not-started status; test: bot handler tests assert the help copy hides legacy generators and states the boundary.
  - id: AC-2; description: Telegram chat command output includes answer, sources, archive-support/unknowns, and privacy line without exposing raw tool payloads; test: handler tests use fake PI chat response and assert formatted output.
  - id: AC-3; description: runtime runbook explains install/start/stop/status commands, rollback to disabled state, and approval prerequisites without treating service activation as dogfood; verify: docs/operator_workflow.md and docs/PRODUCT_OPERATING_MODEL.md updated.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_handlers.py tests/test_callbacks.py tests/test_cli.py -q
  - systemd-analyze verify systemd/telegram-prm-assistant.service
  - python3 tools/test_tiers.py fast-contract
  - python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
  - git diff --check
Files:
  - src/bot/handlers.py
  - src/bot/bot.py
  - src/main.py
  - systemd/telegram-prm-assistant.service
  - tests/test_handlers.py
  - tests/test_callbacks.py
  - tests/test_cli.py
  - docs/operator_workflow.md
  - docs/PRODUCT_OPERATING_MODEL.md
  - docs/EVIDENCE_INDEX.md
Context-Refs:
  - docs/PRODUCT_OPERATING_MODEL.md
  - docs/AUTONOMOUS_WORKFLOW_CONTRACT.md
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/audit/PRM_SAFE_ASSISTANT_RUNTIME_2026-07-29.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for implementation and tests
  max_model_calls: 0 for implementation and tests
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: starting/enabling systemd runtime, running real provider calls with private snippets, or recording dogfood evidence
Notes: |
  Implemented on 2026-08-03. Telegram safe-mode start and help now state
  local-only CLI mode, approved LLM/provider-egress mode, safe read-only
  commands, blocked legacy generation/write commands, and dogfood-not-started
  status. Telegram chat, Hermes, and ask aliases use the same privacy-safe PRM
  chat renderer as the CLI only when separately approved for provider egress
  and started with `PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1`.
  Post-PRM28 local UX routing now sends ordinary text and voice transcripts in
  `prm-assistant` mode through the Telegram auto command, which chooses local-only compact
  research or local-only source-backed editor brief by default. Explicit
  `/research <question>` and `/brief <question>` remain manual fallbacks. The
  runtime keeps volatile in-process follow-up context and previous mode per
  chat, and improves deterministic AI-transformation archive query hints. LLM
  auto-routing and auto chat require both `PRM_TELEGRAM_AUTO_LLM_ROUTER=1` and
  `PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1`. Open browsing, writes, external
  vector/backend work, production migrations, and dogfood remain gated.
  A later 2026-08-11 operator instruction enabled the local vector/RAG/LLM/
  Telegram stack for manual testing only.
  A same-day repair prevents archive/source questions from falling through to
  generic chat and adds Telegram-only bounded LLM synthesis after local hybrid
  RAG when `PRM_TELEGRAM_RAG_LLM_SYNTHESIS=1` is set. This sends only selected
  bounded snippets/context to the provider, suppresses usage DB recording, and
  leaves PRM-19 dogfood unstarted. A follow-up presentation repair makes
  Telegram research/brief render packaged topic reports and strips visible
  technical metrics/cost/tool-call/debug footers from the user message.

  The operator runbook documents preflight inspection, install/start/status,
  stop/disable, and rollback-to-disabled commands while preserving the hard
  gate: a running manual-test service is not dogfood. PRM-19 remains blocked
  until explicit human dogfood-start approval.

### PRM-19: Operator Production-Test Evidence

Owner: human
Phase: PRM
Type: eval:gate
Status: proposed
Depends-On: PRM-18C, PRM-28, PRM-UX-10, PRM-UX-11
Risk-Level: high
Public-Tests-Required: not_required
Critic-Required: conditional
Holdout-Required: required
Mutation-Required: conditional
Property-Required: not_required
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Record human-run production-test questions, useful answers, corrections, saved notes, watch topics, decisions, recovered reactions, time to useful answer, cost, value score, friction score, and continuation decision.
Acceptance-Criteria:
  - id: AC-1; description: real operator questions are recorded with privacy-safe metadata and usefulness labels; verify: production-test receipt count and label coverage.
  - id: AC-2; description: saved notes, watch topics, project or life decisions, rejected answers, and corrections are counted separately; verify: dogfood summary table.
  - id: AC-3; description: continuation decision is based on value, friction, latency, cost, and user desire to keep using it; verify: human production-test decision record.
Verification:
  - production-test receipt review by human operator
Files:
  - docs/prm19_dogfood_plan.md
  - docs/dogfood_4_week_plan.md
  - docs/EVIDENCE_INDEX.md
Context-Refs:
  - docs/final_acceptance_plan.md
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/prm_operator_experience_roadmap.md
  - docs/prm19_dogfood_plan.md
Cost-Budget: |
  scope: phase
  max_cost_usd: 0 until human-approved production-test budget is recorded
  max_model_calls: 0 until human-approved production-test budget is recorded
  max_tool_calls: n/a
  max_retries: 1 per failed workflow
  approval_required_when: weekly budget or provider egress changes
Notes: |
  This is an optional human-run evidence stream, not a prerequisite for UX
  implementation. It does not start automatically, and its operator controls
  remain subject to the existing privacy, provider, and write boundaries.

### PRM-20: Post-Production-Test Simplification, Cleanup, And Archive

Owner: codex
Phase: PRM
Type: repo:hygiene
Status: blocked
Depends-On: PRM-UX-13
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Use real operator production-test evidence to remove unused reports, commands, modules, docs, and abstractions, split oversized modules only where maintenance evidence justifies it, archive historical IRX surfaces safely, and make one primary product path visible.
Acceptance-Criteria:
  - id: AC-1; description: each delete, archive, or move candidate cites current callers, production-test evidence, migration risk, and verification command; verify: cleanup plan rows are updated before edits.
  - id: AC-2; description: final README has one primary operator workflow, one architecture link, one task handoff, and clear legacy labels; verify: README review.
  - id: AC-3; description: generated private outputs remain ignored and no private report artifacts are added; verify: git status and ignore review.
Verification:
  - python3 -m pytest tests/ -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - README.md
  - docs/repo_hygiene_and_archive_plan.md
  - docs/archive/
Context-Refs:
  - docs/repo_hygiene_and_archive_plan.md
  - docs/final_acceptance_plan.md
  - docs/prm_operator_experience_roadmap.md
Cost-Budget: |
  scope: task
  max_cost_usd: 1.00
  max_model_calls: 10
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: deletion or archive affects compatibility surface
Notes: |
  Cleanup follows usage evidence; it is not a precondition for PRM-UX work.
  PRM-20 is currently blocked by missing PRM-19 production-test evidence, the
  PRM-UX-13 simplification handoff, and explicit human approval before
  compatibility files are archived, deleted, or moved.

### PRM-21: Project-Aware Research Session Contract

Owner: codex
Phase: PRM
Type: product:contract
Status: implemented
Depends-On: PRM-18C
Risk-Level: high
Public-Tests-Required: not_required
Critic-Required: conditional
Holdout-Required: required
Mutation-Required: not_required
Property-Required: not_required
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Define the polished assistant product bar for research sessions where the
  operator asks a natural-language question, the system searches the Telegram
  archive, reads approved linked sources, compares approaches, infers project
  context, and returns a clear grounded explanation with deeper-reading links.
Acceptance-Criteria:
  - id: AC-1; description: contract states that RAG is necessary but not sufficient, and separates archive retrieval, linked-source research, project routing, bounded planning, synthesis, confirmation-gated memory, and evals; verify: docs/personal_research_memory_product_contract.md has the capability stack.
  - id: AC-2; description: evidence classes separate Telegram archive, curated memory, linked external evidence, model background, and unknowns; verify: docs/personal_research_memory_product_contract.md contains an evidence class table.
  - id: AC-3; description: task graph records PRM-22..PRM-23 as capability implementation work, not current dogfood evidence or vector/backend approval; verify: docs/tasks.md and docs/ARCHITECTURE.md state the boundary.
Verification:
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - docs/tasks.md
  - docs/personal_research_memory_product_contract.md
  - docs/ARCHITECTURE.md
  - docs/operator_workflow.md
  - docs/EVIDENCE_INDEX.md
  - README.md
Context-Refs:
  - docs/final_acceptance_plan.md
  - docs/retrieval_eval.md
  - docs/generation_eval.md
  - docs/PRIVACY_THREAT_MODEL.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: any live provider call, external web research, service start, or vector/backend adoption is proposed
Notes: |
  Implemented on 2026-08-03 as documentation/backlog grooming. It records the
  polished assistant product bar and PRM-22..PRM-23 implementation tasks. It
  does not implement PRM-23 planner behavior by itself, run web research, start
  dogfood, approve provider egress, or unblock PRM-8 vector/hybrid retrieval.

### PRM-22: Linked Source Research Layer

Owner: codex
Phase: PRM
Type: tool:research
Status: implemented
Depends-On: PRM-21
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Implement a fixture-first linked-source resolver that extracts URLs from
  selected Telegram evidence, classifies source types, stores privacy-safe
  cached text/metadata, and emits receipts without running live external web
  research by default.
Acceptance-Criteria:
  - id: AC-1; description: URL extraction and source classification handle article, docs, GitHub, paper, video, product, and unknown sources from fixture posts; test: focused linked-source resolver tests pass.
  - id: AC-2; description: linked-source cache stores fetched-at time, source URL, normalized title, content hash, extraction status, and redacted failure reason without raw provider payload logs; test: receipt/cache tests inspect sanitized fields.
  - id: AC-3; description: live HTTP fetch, external skills, and provider summarization refuse unless explicit approval/budget switches are present; test: refusal-path tests pass.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_linked_sources.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/assistant/linked_sources.py
  - tests/test_linked_sources.py
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/COST_BUDGET.md
Context-Refs:
  - docs/personal_research_memory_product_contract.md
  - docs/IMPLEMENTATION_CONTRACT.md
  - docs/PRIVACY_THREAT_MODEL.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 until human-approved external research budget is recorded
  max_model_calls: 0 until human-approved provider budget is recorded
  max_tool_calls: n/a
  max_retries: 1 per approved fetch workflow
  approval_required_when: live HTTP fetch, external skill use, provider call, or durable cache write over private production inputs is proposed
Notes: |
  Implemented on 2026-08-03 as a fixture-first resolver/cache layer. It
  extracts and classifies linked source URLs, uses injected fake fetchers in
  tests, emits sanitized cache/receipt records, and refuses live HTTP fetch,
  external skills, or provider summarization unless explicit approval and
  budget switches are present. It does not run live web research, start
  dogfood, approve provider egress, or adopt a vector/backend.

### PRM-23: Bounded Memory Research Planner

Owner: codex
Phase: PRM
Type: assistant:workflow
Status: implemented
Depends-On: PRM-21, PRM-22
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: required
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add a bounded `memory research` assistant path that combines archive search,
  approved linked-source evidence, project-context routing, comparison, and
  LLM synthesis into a polished answer while preserving privacy, citation, cost,
  and confirmation-gated write boundaries.
Acceptance-Criteria:
  - id: AC-1; description: `memory research` produces direct answer, archive evidence, linked-source evidence, approach comparison, project fit, deeper-reading path, unknowns, and privacy/cost receipt from fixture inputs; test: CLI/render tests pass.
  - id: AC-2; description: planner has deterministic limits for tool calls, source count, retries, prompt size, timeout, and cost, and refuses open-ended browsing; test: budget/refusal tests pass.
  - id: AC-3; description: project routing reports direct_implication, weak_watch, learning_relevance, no_match, or ambiguous_project without mutating project descriptors; test: project-routing tests pass.
  - id: AC-4; description: all save/watch/project/action proposals remain drafts until explicit confirmation token; test: confirmation-gate regression tests pass.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_memory_research.py -q
  - PYTHONPATH=src python3 -m pytest tests/test_cli.py -q
  - python3 tools/test_tiers.py focused-prm
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/assistant/memory_research.py
  - src/main.py
  - tests/test_memory_research.py
  - tests/test_cli.py
  - docs/operator_workflow.md
  - docs/EVIDENCE_INDEX.md
Context-Refs:
  - docs/personal_research_memory_product_contract.md
  - docs/generation_eval.md
  - docs/tool_eval.md
  - docs/agent_eval.md
  - docs/COST_BUDGET.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for implementation/tests using fake clients and fixtures
  max_model_calls: 0 for implementation/tests using fake clients and fixtures
  max_tool_calls: n/a
  max_retries: 1 per approved runtime workflow
  approval_required_when: real provider egress, live linked-source fetch, service start, dogfood start, or vector/backend adoption is proposed
Notes: |
  Implemented on 2026-08-03 as a fixture-first local research planner and
  `memory research` CLI. It uses bounded archive/curated/project context,
  deterministic SQLite FTS query decomposition with local acceptance filtering,
  PRM-22 linked-source cache/fake fetcher paths, deterministic synthesis,
  privacy/cost receipts, and confirmation-gated draft proposals. `--project`
  is a project-context hint, not a hard archive FTS filter. It still does not
  approve production dogfood, Telegram service start, live external research,
  provider egress, durable production writes/cache, vector/backend adoption, or
  release claims by itself.

### PRM-24: Product RAG Gold Eval Set

Owner: human+codex
Phase: PRM
Type: eval:dataset eval:gate rag:query
Status: implemented
Depends-On: PRM-23
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: not_required
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Convert the operator's real product questions into a human-approved RAG gold
  eval set that covers archive recall, semantic phrasing, project fit,
  linked-source needs, freshness needs, and no-answer behavior before any
  vector/backend adoption.
Acceptance-Criteria:
  - id: AC-1; description: at least 50 privacy-safe eval rows are recorded across archive recall, project-aware research, linked-source/freshness, no-answer, and decision-support cases; verify: eval set summary reports category coverage.
  - id: AC-2; description: every gold row has human-approved expected source IDs or an explicit no-answer expectation; test: eval schema validation rejects unlabeled or self-invented gold rows.
  - id: AC-3; description: baseline SQLite FTS/query-planner metrics are reported separately from candidate-only diagnostics; test: retrieval eval command separates gold, holdout, and candidate rows.
  - id: AC-4; description: acceptance thresholds are recorded for recall@5, recall@10, citation precision, no-answer accuracy, stale rejection, duplicate rejection, and latency; verify: docs/retrieval_eval.md has the threshold table.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_product_rag_eval.py tests/test_archive_retrieval_eval.py tests/test_memory_research.py -q
  - PYTHONPATH=src python3 tools/product_rag_seed_gold_labels.py --root . --db data/agent.db --jsonl evals/retrieval/product_rag_gold_labels.jsonl
  - PYTHONPATH=src python3 tools/product_rag_gold_cases.py --root . --jsonl evals/retrieval/product_rag_gold_cases.jsonl
  - PYTHONPATH=src python3 tools/product_rag_eval_manifest.py --root . --json evals/retrieval/product_rag_eval_manifest.json
  - PYTHONPATH=src python3 tools/archive_retrieval_eval.py --root . --db data/agent.db --cases evals/retrieval/product_rag_gold_cases.jsonl --limit 10 --json evals/retrieval/product_rag_fts_baseline_report.json
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - evals/retrieval/
  - src/db/product_rag_eval.py
  - tools/product_rag_eval_manifest.py
  - tools/product_rag_gold_cases.py
  - tools/product_rag_seed_gold_labels.py
  - tools/archive_retrieval_eval.py
  - tests/test_product_rag_eval.py
  - tests/test_archive_retrieval_eval.py
  - docs/retrieval_eval.md
  - docs/RAG_DATA_READINESS.md
  - docs/EVIDENCE_INDEX.md
Context-Refs:
  - docs/retrieval_eval.md
  - docs/RAG_DATA_READINESS.md
  - docs/personal_research_memory_product_contract.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for dataset/schema work
  max_model_calls: 0 for dataset/schema work
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: private raw Telegram text would be copied into eval rows or an LLM judge is proposed
Notes: |
  Started on 2026-08-08 as a safe scaffold. Product RAG candidate rows,
  proposed thresholds, a privacy-safe manifest tool, and focused validation
  tests exist. On 2026-08-11 the human operator instructed Codex to create all
  50 generated seed gold labels under
  `operator-approval-2026-08-11-all-50-generated-gold`; the committed labels
  contain stable local archive document/post IDs or explicit no-answer
  expectations, not raw Telegram text or source URLs. Baseline SQLite
  FTS/query-planner evidence is recorded in
  `evals/retrieval/product_rag_fts_baseline_report.json`: hit@10=1.0,
  citation_precision=1.0, p95 latency=46.912 ms, no_answer_accuracy=0.0, and
  stale_rejection=null on this generated seed set. This completes PRM-24
  coverage/eval scaffolding but does not approve embeddings, vector backend
  adoption, provider calls, live web research, migrations, production writes,
  service start, PRM-27, PRM-28, or dogfood.

### PRM-25: Citation-Safe RAG Context Pack

Owner: codex
Phase: PRM
Type: rag:context assistant:contract tool:call
Status: implemented
Depends-On: PRM-24
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: required
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Build a deterministic context-pack layer that merges archive, curated memory,
  linked-source cache, project descriptors, freshness requirements, and
  unknowns into a bounded citation-safe payload for local and LLM-backed RAG
  answers.
Acceptance-Criteria:
  - id: AC-1; description: context packs contain source refs, source class, snippet/excerpt budget, retrieval query variant, freshness status, project label, and no-answer threshold fields; test: schema fixture tests pass.
  - id: AC-2; description: context assembly refuses to include uncited claims or raw corpus dumps and records every excluded candidate reason; test: privacy and no-answer regression tests pass.
  - id: AC-3; description: local `memory research` can render the context pack without LLM/provider calls; test: CLI/render tests pass with fake clients.
  - id: AC-4; description: the context pack supports later hybrid/vector candidates without changing answer-rendering contracts; test: fixture with synthetic semantic candidate preserves citations and dedupe.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_memory_research.py tests/test_cli.py -q
  - python3 tools/test_tiers.py focused-prm
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/assistant/
  - tests/
  - docs/personal_research_memory_product_contract.md
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/EVIDENCE_INDEX.md
Context-Refs:
  - docs/personal_research_memory_product_contract.md
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/generation_eval.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for implementation/tests with fake clients
  max_model_calls: 0 for implementation/tests with fake clients
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: provider synthesis, live linked-source fetch, or raw corpus egress is proposed
Notes: |
  This is the safe pre-vector RAG substrate. It may use SQLite FTS and fixtures,
  but it must not adopt embeddings or a vector backend.
  Implemented on 2026-08-08 as a fixture-only context-pack substrate. It
  excludes uncited/raw candidates, records exclusion reasons, keeps excerpts
  bounded, and is rendered by local `memory research`. PRM-24 now has 50
  operator-approved generated seed gold labels; PRM-26 accepted the no-vector
  path for now; PRM-28 implements the no-vector answer gate.

### PRM-26: Hybrid Retrieval ADR And Privacy Budget

Owner: human+codex
Phase: PRM
Type: rag:architecture eval:gate privacy:approval
Status: implemented
Depends-On: PRM-24, PRM-25
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: not_required
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Decide, from gold eval evidence, whether full product RAG requires a hybrid
  retrieval backend, which embedding model/backend is acceptable, what privacy
  and cost budget applies, and how rollback/reindexing will work.
Acceptance-Criteria:
  - id: AC-1; description: ADR compares SQLite FTS planner, local embeddings, external embeddings, sqlite-vss/Chroma/Postgres pgvector, and no-vector alternatives against recall, precision, latency, update complexity, privacy, cost, backup, and rollback; verify: ADR decision matrix exists.
  - id: AC-2; description: measured FTS failures from PRM-24 are mapped to retrieval mechanisms that could plausibly fix them; verify: failure-to-mechanism table exists.
  - id: AC-3; description: explicit human approval is recorded before any embedding provider, vector database, production index, or migration work can start; verify: ADR status is accepted and cites approval.
  - id: AC-4; description: cost/privacy budget names provider, model, max rows, max tokens/chars, persistence boundary, and redaction/logging rules; verify: docs/COST_BUDGET.md and docs/PRIVACY_THREAT_MODEL.md are updated.
Verification:
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - docs/adr/
  - docs/retrieval_eval.md
  - docs/COST_BUDGET.md
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/ROLLBACK_AND_REINDEX_PLAN.md
  - docs/EVIDENCE_INDEX.md
Context-Refs:
  - docs/retrieval_eval.md
  - docs/RAG_DATA_READINESS.md
  - docs/ROLLBACK_AND_REINDEX_PLAN.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 until approval is recorded
  max_model_calls: 0 until approval is recorded
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: any embedding run, vector backend adoption, production migration, or provider egress is proposed
Notes: |
  This task refines the older PRM-8 blocked gate for the product RAG path. It
  is documentation/eval/approval work only unless the human operator explicitly
  approves a backend.
  Safe PRM-26 ADR/privacy/cost/rollback evidence was accepted on 2026-08-11 in
  `docs/adr/ADR-003-prm26-hybrid-retrieval-privacy-budget.md`. The draft
  accepts no vector/backend adoption for now from current generated seed
  evidence: source-label hit/citation metrics are recovered by SQLite FTS/query
  planner, while the measured gaps are no-answer/refusal behavior and missing
  stale labels. Approval ref:
  `operator-approval-2026-08-11-no-vector-prm28-path`. ADR-004 later accepts a
  local vector sidecar for PRM-27 under
  `operator-approval-2026-08-11-full-stack-local-vector-telegram-llm` without
  approving external embeddings, migrations, provider egress, service start, or
  dogfood.

### PRM-27: Hybrid Retrieval Implementation

Owner: codex
Phase: PRM
Type: rag:query rag:index eval:comparison
Status: implemented
Depends-On: PRM-26
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Implement the approved hybrid retrieval backend and index workflow, compare
  it against the SQLite FTS baseline on the gold eval set, and expose it through
  the existing citation-safe context pack with rollback and privacy receipts.
Acceptance-Criteria:
  - id: AC-1; description: task does not start until PRM-26 has an accepted ADR, human approval, and budget receipt; verify: implementation evidence cites ADR-004 and approval ref.
  - id: AC-2; description: indexing is incremental, versioned, rollback-aware, and never mutates canonical raw_posts/posts rows; test: index/rollback tests pass against fixtures.
  - id: AC-3; description: hybrid retrieval preserves approved recall/citation metrics without reducing no-answer boundary below threshold and records aggregate comparison evidence; test: eval comparison report passes.
  - id: AC-4; description: assistant context pack shows whether each source came from FTS, semantic/vector, linked-source cache, curated memory, or reranking; test: context provenance tests pass.
Verification:
  - python3 -m py_compile src/db/archive_vector.py src/db/archive_search.py src/db/archive_retrieval_eval.py src/assistant/pi_facade.py src/assistant/memory_research.py src/assistant/rag_context_pack.py src/bot/handlers.py src/main.py tools/archive_retrieval_eval.py
  - PYTHONPATH=src python3 -m pytest tests/test_archive_vector.py tests/test_archive_search.py tests/test_archive_retrieval_eval.py tests/test_rag_context_pack.py tests/test_memory_research.py tests/test_pi_facade_archive_vector.py tests/test_cli.py tests/test_handlers.py -q
  - retrieval eval comparison command documented in docs/EVIDENCE_INDEX.md
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/
  - tests/
  - evals/retrieval/
  - docs/adr/ADR-004-prm27-local-vector-sidecar.md
  - docs/retrieval_eval.md
  - docs/ROLLBACK_AND_REINDEX_PLAN.md
  - docs/EVIDENCE_INDEX.md
Context-Refs:
  - docs/adr/
  - docs/retrieval_eval.md
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/ROLLBACK_AND_REINDEX_PLAN.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for local vector indexing/search
  max_model_calls: 0 for local vector indexing/search
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: backend choice, embedding model, index persistence, provider budget, canonical DB write, migration, or service-start scope changes
Notes: |
  Implemented on 2026-08-11 under
  `operator-approval-2026-08-11-full-stack-local-vector-telegram-llm` and
  `docs/adr/ADR-004-prm27-local-vector-sidecar.md`. The implementation adds
  `src/db/archive_vector.py`, `memory vector-index`, `memory vector-search`,
  `memory research --hybrid`, PI facade hybrid search, Telegram research and
  brief hybrid env flags, context-pack retrieval provenance, and
  hybrid eval mode. The default hybrid policy is FTS-first with local vector
  fallback on FTS miss; the actual aggregate report is
  `evals/retrieval/product_rag_hybrid_local_vector_report.json` with hit@10=1.0,
  MRR=1.0, citation_precision=1.0, and latency_ms_p95=59.077 on the 50 generated
  seed gold cases. It uses a gitignored SQLite sidecar and deterministic local
  hashing only. It does not approve external embeddings, live web research,
  production migrations, canonical DB writes, PRM-19 dogfood, or compatibility
  cleanup.

### PRM-28: Product RAG Chat And Acceptance Gate

Owner: codex
Phase: PRM
Type: assistant:workflow eval:gate product:ux
Status: implemented
Depends-On: PRM-25, PRM-26
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: required
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Wire the accepted no-vector RAG context pack into the local product answer
  path, pass the product RAG answer gate, and make the operator-facing answer
  path fast, cited, no-answer aware, freshness-aware, project-aware, and
  confirmation gated before dogfood starts.
Acceptance-Criteria:
  - id: AC-1; description: `memory research` emits the same retrieval/context-pack provenance, answer gate, and privacy/cost receipt without provider egress; test: memory research regression tests pass.
  - id: AC-2; description: answer synthesis is a thin deterministic layer over cited context and cannot invent uncited claims, durable writes, or project actions; test: no-answer/current-fact regression tests block drafts.
  - id: AC-3; description: no-vector product path does not require PRM-27, embeddings, vector backend, provider egress, service start, or production writes; verify: PRM-28 answer-gate report and ADR cite false vector/egress flags.
  - id: AC-4; description: product eval passes recall, citation precision, answer-level no-answer accuracy, freshness boundary, latency, and operator-readability thresholds on the PRM-24 seed gold set; verify: final eval reports are recorded.
  - id: AC-5; description: PRM-19 dogfood remains blocked unless this task passes or the human operator explicitly waives the RAG gate; verify: dogfood gate receipt includes PRM-28 status.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_rag_context_pack.py tests/test_memory_research.py tests/test_product_rag_eval.py tests/test_archive_retrieval_eval.py -q
  - PYTHONPATH=src python3 tools/product_rag_answer_gate_eval.py --root . --cases evals/retrieval/product_rag_gold_cases.jsonl --json evals/retrieval/product_rag_answer_gate_report.json
  - retrieval/generation eval commands documented in docs/EVIDENCE_INDEX.md
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/assistant/
  - src/main.py
  - src/db/product_rag_answer_gate_eval.py
  - tools/product_rag_answer_gate_eval.py
  - tests/
  - evals/retrieval/product_rag_answer_gate_report.json
  - docs/operator_workflow.md
  - docs/final_acceptance_plan.md
  - docs/EVIDENCE_INDEX.md
Context-Refs:
  - docs/generation_eval.md
  - docs/tool_eval.md
  - docs/agent_eval.md
  - docs/final_acceptance_plan.md
  - docs/PRIVACY_THREAT_MODEL.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for fake-client implementation/tests
  max_model_calls: 0 for fake-client implementation/tests
  max_tool_calls: bounded by assistant tool catalog
  max_retries: 1
  approval_required_when: real provider egress, service start, dogfood start, live linked-source fetch, or production write is proposed
Notes: |
  This is the full product RAG readiness gate before PRM-19. It does not start
  Telegram runtime dogfood by itself and does not approve provider egress beyond
  explicit command-line/runtime switches.
  Implemented on 2026-08-11 as the accepted no-vector PRM-28 path. The
  `rag_answer_gate.v1` layer blocks impossible/current project-state claims and
  current-price/current-fact questions even when FTS returns related posts. It
  records answer-gate status in `memory research` and the context pack, blocks
  draft proposals when evidence is insufficient, and keeps provider egress,
  embeddings, vector backend, service start, migrations, production writes, and
  dogfood false. `evals/retrieval/product_rag_answer_gate_report.json` reports
  no_answer_accuracy=1.0, external_verification_boundary_accuracy=1.0,
  answerable_source_label_accuracy=1.0, vector_backend_required_rate=0.0, and
  embeddings_run_rate=0.0 on the 50-row generated seed gold set. This satisfies
  the no-vector RAG acceptance gate but does not start PRM-19 dogfood.

## PRM-UX Queue - Operator Experience And Professional Personalization

### PRM-UX-0: Current Operator Experience And Documentation Audit

Owner: codex
Phase: PRM-UX
Type: project:governance eval:gate
Status: implemented
Depends-On: PRM-28
Risk-Level: medium
Public-Tests-Required: not_required
Critic-Required: conditional
Holdout-Required: not_required
Mutation-Required: not_required
Property-Required: not_required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Produce a grounded operator-experience audit that classifies current PRM runtime/product claims by code, tests, receipts, docs, stale state, contradictions, or unverifiable gaps, and converts the findings into a bounded PRM-UX roadmap.
Acceptance-Criteria:
  - id: AC-1; description: audit records target SHA, Playbook SHA, stale Playbook pin status, local-only UX probe metrics, claim classification table, and no private post bodies; verify: docs/prm_operator_experience_audit.md contains those sections.
  - id: AC-2; description: roadmap records PRM-UX phases, dependency graph, minimum dogfood-start slice, anti-complexity rules, and evaluation updates; verify: docs/prm_operator_experience_roadmap.md contains those sections.
  - id: AC-3; description: task graph contains PRM-UX queue and updates PRM-19/PRM-20 dependencies without adding IRX tasks; verify: docs/tasks.md contains PRM-UX-0 through PRM-UX-13 and no new IRX task.
Verification:
  - python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
  - python3 tools/verify_project.py --root .
  - git diff --check
Files:
  - docs/prm_operator_experience_audit.md
  - docs/prm_operator_experience_roadmap.md
  - docs/professional_personalization_contract.md
  - docs/prm19_dogfood_plan.md
  - docs/operator_quickstart.md
  - docs/tasks.md
Context-Refs:
  - docs/PRODUCT_OPERATING_MODEL.md
  - docs/EVIDENCE_INDEX.md
  - docs/audit/PRM_LOCAL_UX_TRIAL_2026-08-11.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 0
  approval_required_when: task scope expands to runtime/code behavior or provider calls
Notes: |
  User problem: the product has strong technical receipts but unclear daily value.
  Boundary: documentation/task planning only; no code/runtime/data mutation.
  Likely paths inspected: src/bot/handlers.py, src/assistant/memory_research.py,
  src/assistant/local_memory_ask.py, src/db/archive_search.py, src/db/archive_vector.py.
  Dogfood effect: creates the evidence baseline for PRM-UX but does not start PRM-19.

### PRM-UX-1: Single Conversational Entrypoint And Intent Acknowledgement

Owner: codex
Phase: PRM-UX
Type: product:ux agent:harness
Status: implemented
Depends-On: PRM-UX-0
Risk-Level: medium
Public-Tests-Required: required
Critic-Required: conditional
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Make ordinary Telegram text and voice transcripts the single normal operator entrypoint by adding deterministic intent acknowledgement for research, brief, gated chat, feedback, and clarification paths while keeping manual commands as fallback overrides.
Acceptance-Criteria:
  - id: AC-1; description: PRM assistant start/help copy presents normal text or voice as the default workflow and demotes slash research, slash brief, and slash chat to fallback controls; test: tests/test_handlers.py::test_prm_start_copy_contract_after_prm_ux_1.
  - id: AC-2; description: auto-routed research and brief responses can include one compact Russian interpretation line when the route is non-obvious and omit it when it would repeat the question; test: tests/test_handlers.py::test_auto_route_intent_acknowledgement_copy.
  - id: AC-3; description: ambiguous intent asks at most one compact clarification with bounded choices and does not call a provider or write memory; test: tests/test_handlers.py::test_auto_route_ambiguous_intent_clarification_is_local.
  - id: AC-4; description: voice transcripts enter the same auto interpretation path as text and do not expose legacy slash voice feedback command copy in PRM safe mode; test: tests/test_callbacks.py::test_run_bot_prm_safe_dispatches_transcribed_voice_as_auto.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_handlers.py tests/test_callbacks.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/bot/handlers.py
  - tests/test_handlers.py
  - tests/test_callbacks.py
  - docs/operator_quickstart.md
  - docs/operator_workflow.md
Context-Refs:
  - docs/prm_operator_experience_audit.md
  - docs/prm_operator_experience_roadmap.md
  - docs/PRODUCT_OPERATING_MODEL.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for tests
  max_model_calls: 0 for tests
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: provider-backed route selection, service restart, or durable write is proposed
Notes: |
  User problem: the operator should not choose between subsystems.
  Product outcome: one Telegram conversation with compact interpretation.
  Boundary: no provider calls, env changes, service starts, or DB writes.
  Likely code paths: _route_auto_message, handle_auto, handle_research,
  handle_research_brief, voice callback dispatch.
  Interface changes: response copy only; no new durable schema.
  Failure behavior: ambiguous route asks one question or falls back to safe local research.
  Non-goal: answer contract rewrite belongs to PRM-UX-2.
  Dogfood effect: required part of minimum PRM-19 start slice.

### PRM-UX-2: Answer-First Telegram Response Contract

Owner: codex
Phase: PRM-UX
Type: rag:generation product:ux eval:gate
Status: implemented
Depends-On: PRM-UX-1
Risk-Level: medium
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Enforce a single answer-first Russian Telegram response contract with source, uncertainty, professional relevance, one-next-action, insufficient-evidence, and external-verification boundaries while hiding retrieval receipts from ordinary output.
Acceptance-Criteria:
  - id: AC-1; description: ordinary Telegram research answer includes `Короткий вывод`, `Что найдено`, `Почему это важно тебе`, `Что сделать`, weak-evidence wording, and `Источники`; test: tests/test_handlers.py::test_telegram_research_answer_first_contract.
  - id: AC-2; description: ordinary Telegram output excludes local paths, raw DB IDs, model/cost/token/tool/debug footers, and unexplained internal English labels; test: tests/test_handlers.py::test_telegram_research_hides_internal_receipts.
  - id: AC-3; description: current/high-stakes questions lead with external-verification status and do not present archive context as current truth; test: tests/test_handlers.py::test_telegram_current_fact_answer_first_boundary.
  - id: AC-4; description: generated response validators are documented for exact checks and human-review checks; verify: docs/generation_eval.md and docs/prm_operator_experience_roadmap.md list validator split.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_handlers.py tests/test_memory_research.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/bot/handlers.py
  - src/assistant/memory_research.py
  - tests/test_handlers.py
  - tests/test_memory_research.py
  - docs/generation_eval.md
  - docs/operator_quickstart.md
Context-Refs:
  - docs/prm_operator_experience_roadmap.md
  - docs/generation_eval.md
  - docs/PRIVACY_THREAT_MODEL.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for tests
  max_model_calls: 0 for tests with fake/local paths
  max_tool_calls: bounded by existing research path
  max_retries: 1
  approval_required_when: real provider synthesis prompt changes are tested against live private snippets
Notes: |
  User problem: a source-backed report can still fail as an answer.
  Likely code paths: _synthesize_telegram_rag_answer, _telegram_report_without_technical_metrics,
  render_memory_research_answer, render_memory_research_brief.
  Data source: bounded context pack and answer gate.
  Privacy: no raw corpus, local paths, provider payloads, or debug receipts in ordinary Telegram output.
  Failure behavior: answer gate refusal or insufficient-evidence response.
  Non-goal: new retrieval backend or external verification execution.
  Dogfood effect: required part of minimum PRM-19 start slice.

### PRM-UX-3: Professional Lens Profile V2

Owner: human+codex
Phase: PRM-UX
Type: project:governance rag:query
Status: implemented
Depends-On: PRM-UX-2
Risk-Level: medium
Public-Tests-Required: required
Critic-Required: conditional
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add a versioned professional-lens contract that separates recall, rerank, framing, and action so personalization improves answer relevance without reducing broad archive retrieval recall.
Acceptance-Criteria:
  - id: AC-1; description: professional lens schema covers ai_systems_engineer, portfolio_builder, career, product_strategy, enterprise_ai_adoption, writer_editor, and learning with goals, evidence preferences, and output preferences; test: tests/test_professional_personalization.py::test_lens_schema_contract.
  - id: AC-2; description: retrieval recall path ignores lens as a hard filter while rerank/framing/action may use lens fields; test: tests/test_professional_personalization.py::test_lens_does_not_reduce_recall_candidates.
  - id: AC-3; description: permanent profile changes are represented only as proposals requiring human confirmation; test: tests/test_professional_personalization.py::test_lens_preference_change_requires_confirmation.
  - id: AC-4; description: operator approval checklist exists before profile configuration mutation; verify: docs/professional_personalization_contract.md lists approval rules and migration from current profile.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_professional_personalization.py tests/test_memory_research.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/assistant/professional_personalization.py
  - tests/test_professional_personalization.py
  - docs/professional_personalization_contract.md
  - src/config/profile.yaml
Context-Refs:
  - docs/professional_personalization_contract.md
  - docs/prm_operator_experience_audit.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: writing profile.yaml, changing default lens, or using provider inference
Notes: |
  User problem: current profile is topic/source based rather than goal/output based.
  Boundary: implement schema/loader/rerank hooks only; do not modify profile.yaml without approval.
  Likely files: new assistant helper, memory research route/render tests.
  Source of truth: professional_personalization.v2 plus current profile as legacy input.
  Failure behavior: unknown lens falls back to neutral framing and broad recall.
  Non-goal: automatic permanent preference learning.
  Dogfood effect: required part of minimum PRM-19 start slice after human schema approval.

### PRM-UX-4: Active Project Portfolio Context V2

Owner: human+codex
Phase: PRM-UX
Type: project:governance rag:query
Status: implemented
Depends-On: PRM-UX-3
Risk-Level: medium
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add a versioned project portfolio context model with status, priority, current goal, blocker, next proof, signal preferences, and owner-confirmation status so assistant project actions target only approved active/priority work.
Acceptance-Criteria:
  - id: AC-1; description: project context schema validates required fields and accepted status values active, priority, watch, reference, paused, archived; test: tests/test_project_portfolio_context.py::test_project_context_v2_schema.
  - id: AC-2; description: default routing uses only approved active/priority projects unless the operator names another project; test: tests/test_project_portfolio_context.py::test_default_project_set_excludes_watch_reference.
  - id: AC-3; description: broad keyword overlap alone yields no action recommendation; test: tests/test_project_portfolio_context.py::test_keyword_overlap_is_not_project_action.
  - id: AC-4; description: proposed classification table is documented and marked unapproved before projects.yaml mutation; verify: docs/professional_personalization_contract.md contains candidate project classification and approval boundary.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_project_portfolio_context.py tests/test_project_context.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/assistant/project_context.py
  - src/assistant/project_portfolio_context.py
  - tests/test_project_portfolio_context.py
  - tests/test_project_context.py
  - docs/professional_personalization_contract.md
  - src/config/projects.yaml
Context-Refs:
  - docs/professional_personalization_contract.md
  - src/config/projects.yaml
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: changing project active status, priority, or default active set
Notes: |
  User problem: current project list is flat and contains report-era descriptors.
  Boundary: schema/loader/routing behavior only unless human approves config edits.
  Data source: projects.yaml plus explicit V2 overlay/proposal.
  Privacy: no external repo sync or provider calls.
  Failure behavior: unconfirmed project status routes as reference/watch, not action.
  Non-goal: broad portfolio cleanup or GitHub mutation.
  Dogfood effect: required part of minimum PRM-19 start slice after owner approval.

### PRM-UX-5: Incremental Archive Freshness And Operator Refresh Receipt

Owner: human+codex
Phase: PRM-UX
Type: rag:ingestion workflow:autonomous cost:telemetry
Status: implemented
Depends-On: PRM-UX-4
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: required
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Design and implement a bounded incremental archive freshness path and operator slash refresh receipt that can update Telegram archive/FTS within an approved staleness window without LLM calls, report generation, reaction sync coupling, or release/dogfood claims.
Acceptance-Criteria:
  - id: AC-1; description: refresh contract refuses routine schedule changes until operator timezone, source volume, rate limits, host availability, backup cost, vector cost, and acceptable staleness are recorded; verify: docs/PRODUCT_OPERATING_MODEL.md and docs/prm_operator_experience_roadmap.md list approval inputs.
  - id: AC-2; description: slash refresh or CLI receipt returns new posts, channels touched, latest post age, reaction summary placeholder, enrichment pending, and no report/provider flags without raw post text; test: tests/test_prm_refresh_receipt.py::test_operator_refresh_receipt_contract.
  - id: AC-3; description: archive refresh failure does not run reports, providers, migrations, reaction sync, or vector rebuild unless separately approved; test: tests/test_prm_refresh_receipt.py::test_refresh_failure_boundary.
  - id: AC-4; description: current weekly Europe/Berlin timer remains unchanged unless a human approval reference is recorded; verify: systemd template diff and docs approval checklist.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_prm_refresh_receipt.py tests/test_prm_archive_refresh_systemd.py tests/test_cli.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/main.py
  - src/bot/handlers.py
  - tests/test_prm_refresh_receipt.py
  - tests/test_prm_archive_refresh_systemd.py
  - docs/PRODUCT_OPERATING_MODEL.md
  - docs/operator_quickstart.md
Context-Refs:
  - docs/audit/PRM_MANUAL_ARCHIVE_REFRESH_2026-08-12.md
  - docs/audit/PRM_WEEKLY_ARCHIVE_REFRESH_TIMER_2026-08-12.md
  - docs/prm_operator_experience_roadmap.md
Cost-Budget: |
  scope: workflow
  max_cost_usd: 0 provider cost
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: routine schedule, timezone, canonical DB write scope, vector rebuild cadence, or Telegram rate-limit policy changes
Notes: |
  User problem: weekly archive freshness is weak for current questions.
  Boundary: production writes and schedule changes require explicit approval.
  Likely code paths: memory refresh-archive, Telegram handler surface, systemd templates.
  Data source: canonical local SQLite archive and FTS.
  Failure behavior: old archive remains usable with stale receipt.
  Non-goal: live web verification or report generation.
  Dogfood effect: required part of minimum PRM-19 start slice after schedule/staleness approval.

### PRM-UX-6: Reaction Sync And Searchable Fast Lane

Owner: human+codex
Phase: PRM-UX
Type: rag:ingestion workflow:autonomous cost:telemetry
Status: implemented
Depends-On: PRM-UX-5
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: required
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add a routine reaction fast-lane plan and receipt path where reaction sync can resolve personal reactions, confirm archive searchability, apply temporary interest boosts, queue enrichment, and fail independently from archive freshness.
Acceptance-Criteria:
  - id: AC-1; description: reaction receipt records detected reactions, resolved posts, already-searchable posts, newly indexed posts, queued/completed/failed enrichment, provisional topic/project links, ranking effects, and no-effect reasons without raw text or emoji semantics; test: tests/test_reaction_fast_lane.py::test_reaction_fast_lane_operator_receipt_fields.
  - id: AC-2; description: no reaction maps to unknown and never negative; test: tests/test_reaction_fast_lane.py::test_no_reaction_is_unknown_not_negative.
  - id: AC-3; description: reaction sync failure produces a receipt and does not block archive refresh success status; test: tests/test_reaction_sync.py::test_reaction_failure_isolated_from_archive_refresh.
  - id: AC-4; description: adding reaction sync to any routine service is blocked until credentials, Telethon visibility, rate-limit, and approval boundaries are documented; verify: docs/prm_operator_experience_roadmap.md and docs/PRODUCT_OPERATING_MODEL.md list the approval gate.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_reaction_fast_lane.py tests/test_reaction_sync.py tests/test_prm_refresh_receipt.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/db/reaction_fast_lane.py
  - src/ingestion/reaction_sync.py
  - src/bot/handlers.py
  - tests/test_reaction_fast_lane.py
  - tests/test_reaction_sync.py
  - docs/PRODUCT_OPERATING_MODEL.md
Context-Refs:
  - docs/RAG_DATA_READINESS.md
  - docs/prm_operator_experience_audit.md
  - docs/prm_operator_experience_roadmap.md
Cost-Budget: |
  scope: workflow
  max_cost_usd: 0 provider cost
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: reaction sync is added to a routine timer/service or credential scope changes
Notes: |
  User problem: reactions are high-signal but not part of daily PRM refresh.
  Boundary: no automatic routine reaction sync before approval.
  Likely code paths: reaction_sync, reaction_fast_lane, archive search filters.
  Source of truth: reaction_sync_state plus canonical archive rows.
  Privacy: raw post text, source URLs in receipts, and emoji sentiment are excluded.
  Non-goal: permanent preference learning.
  Dogfood effect: required part of minimum PRM-19 start slice as a failure-isolated path.

### PRM-UX-7: Post-Answer Save, Watch, Project, And Feedback Actions

Owner: codex
Phase: PRM-UX
Type: tool:schema tool:call tool:unsafe product:ux
Status: implemented
Depends-On: PRM-UX-6
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: required
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Convert existing confirmation-gated proposal concepts into a simple Telegram post-answer habit for Save Knowledge Note, Watch Topic, Link To Project, Create Action, Create Experiment, Mark Useful, Mark Wrong Priority, Mark Too Shallow, and Mark Applied.
Acceptance-Criteria:
  - id: AC-1; description: ordinary answer renderer exposes only safe inline actions relevant to the answer type and keeps callback payloads bounded; test: tests/test_prm_post_answer_actions.py::test_action_markup_relevant_and_bounded.
  - id: AC-2; description: selecting save/watch/project/action/experiment shows a compact proposal and performs no durable write before explicit confirmation; test: tests/test_prm_post_answer_actions.py::test_proposal_before_write.
  - id: AC-3; description: confirmation creates or reuses the expected durable event and displays how to retrieve it; test: tests/test_prm_post_answer_actions.py::test_confirmed_action_receipt.
  - id: AC-4; description: feedback actions record usefulness metadata without mutating profile.yaml, projects.yaml, provider config, or external systems; test: tests/test_prm_post_answer_actions.py::test_feedback_action_no_config_or_external_mutation.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_prm_post_answer_actions.py tests/test_pi_tools.py tests/test_callbacks.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/bot/handlers.py
  - src/bot/callbacks.py
  - src/assistant/pi_tools.py
  - src/assistant/pi_memory.py
  - tests/test_prm_post_answer_actions.py
  - docs/tool_eval.md
Context-Refs:
  - docs/personal_research_memory_product_contract.md
  - docs/tool_eval.md
  - docs/PRIVACY_THREAT_MODEL.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: bounded by existing proposal/write catalog
  max_retries: 1
  approval_required_when: new durable table, external action, reminder, profile/project mutation, or unconfirmed write is proposed
Notes: |
  User problem: save/watch concepts exist but are not a pleasant habit.
  Boundary: no write without explicit confirmation; no automatic reminders.
  Data source: personal_memory_events and existing proposal confirmation contracts.
  Failure behavior: expired/missing proposal asks for regeneration, not a guessed write.
  Non-goal: generic task manager or automatic follow-up system.
  Dogfood effect: required part of minimum PRM-19 start slice.

### PRM-UX-8A: AI Systems And Project Application Workflow

Owner: codex
Phase: PRM-UX
Type: rag:query rag:generation eval:gate
Status: implemented
Depends-On: PRM-UX-2, PRM-UX-3, PRM-UX-4
Risk-Level: medium
Public-Tests-Required: required
Critic-Required: conditional
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add a bounded AI systems workflow that turns archive evidence about agent runtime failure modes, evals, RAG, context engineering, or safety into a failure taxonomy, one active-project implication, one PR-sized action, and one eval case.
Acceptance-Criteria:
  - id: AC-1; description: fixture question about agent runtime failure modes returns taxonomy, cited cases, project implication, one project action, one eval case, and uncertainty; test: tests/test_prm_professional_workflows.py::test_ai_systems_project_application_workflow.
  - id: AC-2; description: project action is absent when evidence has only broad keyword overlap; test: tests/test_prm_professional_workflows.py::test_ai_systems_no_keyword_only_action.
  - id: AC-3; description: output follows answer-first Telegram contract and marks external verification needs for current claims; test: tests/test_prm_professional_workflows.py::test_ai_systems_freshness_boundary.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_prm_professional_workflows.py tests/test_handlers.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/assistant/memory_research.py
  - src/bot/handlers.py
  - tests/test_prm_professional_workflows.py
  - docs/generation_eval.md
Context-Refs:
  - docs/professional_personalization_contract.md
  - docs/prm_operator_experience_roadmap.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for tests
  max_model_calls: 0 for tests
  max_tool_calls: bounded by research path
  max_retries: 1
  approval_required_when: live provider synthesis or external verification is introduced
Notes: |
  User problem: systems research must become a project/eval move.
  Boundary: one workflow slice, no broad renderer rewrite.
  Dogfood effect: professional value slice; not required before first dogfood day.

### PRM-UX-8B: Career And Portfolio Gap Workflow

Owner: codex
Phase: PRM-UX
Type: rag:query rag:generation eval:gate
Status: implemented
Depends-On: PRM-UX-3, PRM-UX-4, PRM-UX-10
Risk-Level: medium
Public-Tests-Required: required
Critic-Required: conditional
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add a career and portfolio workflow that extracts recurring Agentic AI Engineer requirements from local evidence, compares them with approved portfolio project evidence, identifies missing proof, and proposes one next portfolio action.
Acceptance-Criteria:
  - id: AC-1; description: fixture career question returns recurring requirement, source evidence, current portfolio evidence, missing proof, next portfolio action, and unstable job-market verification warning; test: tests/test_prm_professional_workflows.py::test_career_portfolio_gap_workflow.
  - id: AC-2; description: absent local repo evidence is labelled unknown or reference-only instead of fabricated portfolio proof; test: tests/test_prm_professional_workflows.py::test_missing_portfolio_repo_not_fabricated.
  - id: AC-3; description: career-market current facts require primary-source verification before recommendation; test: tests/test_prm_professional_workflows.py::test_career_current_market_verification_boundary.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_prm_professional_workflows.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/assistant/memory_research.py
  - src/assistant/project_portfolio_context.py
  - tests/test_prm_professional_workflows.py
  - docs/generation_eval.md
Context-Refs:
  - docs/professional_personalization_contract.md
  - docs/prm19_dogfood_plan.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for tests
  max_model_calls: 0 for tests
  max_tool_calls: bounded by research path
  max_retries: 1
  approval_required_when: live job-market verification or provider synthesis is proposed
Notes: |
  User problem: career signals need mapping to portfolio proof.
  Boundary: no external job scraping and no portfolio repo mutation.
  Dogfood effect: professional value slice; labels feed PRM-19 usefulness evidence.

### PRM-UX-8C: Product And Enterprise AI Adoption Workflow

Owner: codex
Phase: PRM-UX
Type: rag:query rag:generation eval:gate
Status: implemented
Depends-On: PRM-UX-3, PRM-UX-4
Risk-Level: medium
Public-Tests-Required: required
Critic-Required: conditional
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add a product and enterprise AI adoption workflow that extracts pain patterns, buyer/owner signals, workarounds, evidence maturity, relevant project implications, validation steps, and do-not-build boundaries from local archive evidence.
Acceptance-Criteria:
  - id: AC-1; description: enterprise adoption fixture returns pain pattern, evidence maturity, buyer/owner signal, relevant project, validation step, and do-not-build boundary; test: tests/test_prm_professional_workflows.py::test_enterprise_ai_adoption_workflow.
  - id: AC-2; description: Telegram-only business claims are labelled discovery evidence and not build-ready validation; test: tests/test_prm_professional_workflows.py::test_telegram_only_product_claim_boundary.
  - id: AC-3; description: no relevant active project yields watch/reference guidance and no action recommendation; test: tests/test_prm_professional_workflows.py::test_enterprise_no_project_action_without_direct_evidence.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_prm_professional_workflows.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/assistant/memory_research.py
  - tests/test_prm_professional_workflows.py
  - docs/generation_eval.md
Context-Refs:
  - docs/professional_personalization_contract.md
  - docs/prm_operator_experience_roadmap.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for tests
  max_model_calls: 0 for tests
  max_tool_calls: bounded by research path
  max_retries: 1
  approval_required_when: external demand validation or live web research is proposed
Notes: |
  User problem: product hypotheses need evidence maturity and do-not-build boundaries.
  Boundary: no Demand-to-MVP live run and no external research.
  Dogfood effect: professional value slice after initial UX.

### PRM-UX-8D: Writer And Editor Brief Workflow

Owner: codex
Phase: PRM-UX
Type: rag:generation product:ux eval:gate
Status: implemented
Depends-On: PRM-UX-2, PRM-UX-3
Risk-Level: medium
Public-Tests-Required: required
Critic-Required: conditional
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add a writer/editor workflow that produces a source-backed Russian brief with thesis, two or three cases, counterargument, practical conclusion, source links, and claims requiring external verification.
Acceptance-Criteria:
  - id: AC-1; description: editor fixture about AI adoption workflow returns thesis, source-backed cases, counterargument, practical conclusion, sources, and verification-required claims; test: tests/test_prm_professional_workflows.py::test_writer_editor_brief_workflow.
  - id: AC-2; description: brief output avoids draft-final-post claims when current external facts are unverified; test: tests/test_prm_professional_workflows.py::test_editor_brief_marks_unverified_current_claims.
  - id: AC-3; description: source bullets support the thesis/cases without raw post bodies in committed fixtures; verify: test fixtures contain source refs only.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_prm_professional_workflows.py tests/test_handlers.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/assistant/memory_research.py
  - src/bot/handlers.py
  - tests/test_prm_professional_workflows.py
  - docs/generation_eval.md
Context-Refs:
  - docs/professional_personalization_contract.md
  - docs/prm_operator_experience_roadmap.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for tests
  max_model_calls: 0 for tests
  max_tool_calls: bounded by research path
  max_retries: 1
  approval_required_when: live linked-source fetch or provider final drafting is proposed
Notes: |
  User problem: writing needs a thesis, not a retrieval dump.
  Boundary: brief inputs only; no automatic publishing or final content claim.
  Dogfood effect: professional value slice after answer contract.

### PRM-UX-8E: Learning And Experiment Workflow

Owner: codex
Phase: PRM-UX
Type: rag:generation eval:gate
Status: implemented
Depends-On: PRM-UX-2, PRM-UX-3, PRM-UX-4
Risk-Level: medium
Public-Tests-Required: required
Critic-Required: conditional
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add a learning workflow that explains a complex AI engineering concept simply, cites local sources, connects it to existing knowledge/project context, and proposes one small experiment with success criterion and reflection question.
Acceptance-Criteria:
  - id: AC-1; description: context-engineering fixture returns plain explanation, analogy, source evidence, existing-knowledge relation, one experiment, success criterion, and reflection question; test: tests/test_prm_professional_workflows.py::test_learning_experiment_workflow.
  - id: AC-2; description: learning state remains explicit and does not infer read/applied/measured from source existence; test: tests/test_learning_layer.py::test_learning_state_does_not_infer_progress_from_sources.
  - id: AC-3; description: experiment action is a proposal and requires confirmation before durable write; test: tests/test_prm_professional_workflows.py::test_learning_experiment_confirmation_boundary.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_prm_professional_workflows.py tests/test_learning_layer.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/assistant/memory_research.py
  - tests/test_prm_professional_workflows.py
  - docs/generation_eval.md
Context-Refs:
  - docs/professional_personalization_contract.md
  - docs/personal_research_memory_product_contract.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for tests
  max_model_calls: 0 for tests
  max_tool_calls: bounded by research path
  max_retries: 1
  approval_required_when: provider tutoring mode or durable experiment write changes
Notes: |
  User problem: learning should become a small experiment, not passive reading.
  Boundary: no automatic learning-state promotion.
  Dogfood effect: professional value slice after initial UX.

### PRM-UX-9: Targeted Primary-Source Verification

Owner: human+codex
Phase: PRM-UX
Type: tool:schema tool:call skill:security rag:generation
Status: implemented
Depends-On: PRM-UX-2
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: required
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add a bounded primary-source verification workflow triggered by the operator that separates Telegram signal, official/GitHub/paper/independent evidence, what changed, unknowns, and revised recommendation without enabling broad autonomous web research.
Acceptance-Criteria:
  - id: AC-1; description: `Проверить первоисточники` creates a verification plan with evidence classes and refuses live fetch when approval/trust record is missing; test: tests/test_primary_source_verification.py::test_verification_requires_approval_before_live_fetch.
  - id: AC-2; description: official documentation and GitHub repository sources are preferred over broad external skill bundles when direct source URLs exist; test: tests/test_primary_source_verification.py::test_direct_primary_source_preference.
  - id: AC-3; description: answer format separates Telegram signal, primary source, independent confirmation, changed facts, unknowns, and revised recommendation; test: tests/test_primary_source_verification.py::test_verification_answer_contract.
  - id: AC-4; description: external skill enablement is blocked until trust record template is filled and approved; verify: templates/EXTERNAL_SKILL_TRUST_RECORD.md and docs/PRIVACY_THREAT_MODEL.md approval boundary.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_primary_source_verification.py tests/test_pi_tools.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/assistant/primary_source_verification.py
  - src/assistant/pi_tools.py
  - tests/test_primary_source_verification.py
  - docs/tool_eval.md
  - docs/PRIVACY_THREAT_MODEL.md
  - templates/EXTERNAL_SKILL_TRUST_RECORD.md
Context-Refs:
  - docs/prm_operator_experience_roadmap.md
  - docs/PRIVACY_THREAT_MODEL.md
  - templates/EXTERNAL_SKILL_TRUST_RECORD.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 until approval
  max_model_calls: 0 until approval
  max_tool_calls: 0 live external calls until approval
  max_retries: 0 until approval
  approval_required_when: live web/API call, external skill, provider summary, or durable cache write is proposed
Notes: |
  User problem: Telegram is discovery evidence and often needs primary-source verification.
  Boundary: no unrestricted web research and no skill install in this task.
  Failure behavior: returns verification_required_not_run with next approval step.
  Dogfood effect: not required for first dogfood day if verification-required claims are marked.

### PRM-UX-10: Real-Question Evaluation And PRM-19 Instrumentation

Owner: human+codex
Phase: PRM-UX
Type: eval:gate cost:telemetry
Status: implemented
Depends-On: PRM-UX-7
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Add privacy-safe real-question evaluation instrumentation for PRM-19 that records category, lens, project, intent, clarification, latency, source count, usefulness, trust, rephrase, evidence errors, saved actions, decision impact, time saved, corrections, and feedback notes.
Acceptance-Criteria:
  - id: AC-1; description: dogfood receipt schema validates the PRM-19 real-question fields and excludes raw post text, prompts, completions, and provider payloads; test: tests/test_prm19_dogfood_receipts.py::test_real_question_receipt_schema_privacy.
  - id: AC-2; description: 30-question category plan is documented with generated labels excluded from independent user evidence; verify: docs/prm19_dogfood_plan.md contains category plan and label boundary.
  - id: AC-3; description: 10-question smoke command can record metadata without starting PRM-19 or claiming success; test: tests/test_prm19_dogfood_receipts.py::test_smoke_receipt_not_dogfood_start.
  - id: AC-4; description: useful/partial/no and trust labels are operator-owned fields, not LLM judge authority; test: tests/test_prm19_dogfood_receipts.py::test_operator_labels_are_primary.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_prm19_dogfood_receipts.py tests/test_prm_release_gate.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/db/prm19_dogfood_receipts.py
  - schemas/prm19_dogfood_receipt.schema.json
  - tests/test_prm19_dogfood_receipts.py
  - docs/prm19_dogfood_plan.md
  - docs/final_acceptance_plan.md
Context-Refs:
  - docs/prm19_dogfood_plan.md
  - docs/final_acceptance_plan.md
  - evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json
Cost-Budget: |
  scope: phase
  max_cost_usd: 0 until human dogfood budget approval
  max_model_calls: 0 until human dogfood budget approval
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: dogfood start, provider budget, or durable production write scope changes
Notes: |
  User problem: existing evals measure mechanics more than usefulness.
  Boundary: instrumentation and smoke only; PRM-19 start remains human-gated.
  Data source: operator labels and privacy-safe metadata.
  Failure behavior: missing labels mean unknown, not pass.
  Dogfood effect: required part of minimum PRM-19 start slice.

### PRM-UX-11: Documentation And Runbook Consolidation

Owner: codex
Phase: PRM-UX
Type: project:governance
Status: implemented
Depends-On: PRM-UX-0
Risk-Level: medium
Public-Tests-Required: not_required
Critic-Required: conditional
Holdout-Required: not_required
Mutation-Required: not_required
Property-Required: not_required
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Consolidate operator-facing docs so root README stays product-first, operator quickstart explains daily use, runbooks hold operational detail, and legacy Report V2 / Atlas / Radar / old bot/timer material is clearly labelled compatibility history.
Acceptance-Criteria:
  - id: AC-1; description: docs/operator_quickstart.md answers bot input, expected answer, save, refresh, feedback, non-goals, and health questions; verify: docs/operator_quickstart.md contains all seven questions.
  - id: AC-2; description: root README points to the PRM-UX phase without adding more systemd manual detail; verify: README.md navigation section links PRM-UX docs and runbooks.
  - id: AC-3; description: operational detail is moved or linked to runbook docs and legacy surfaces are labelled compatibility-only; verify: docs/runbooks/assistant_runtime.md, docs/runbooks/archive_refresh.md, docs/runbooks/development.md, and docs/legacy_surfaces.md exist or task notes explain deferred creation.
  - id: AC-4; description: docs/README.md current date and runtime truth match Product Operating Model; verify: docs/README.md has Last updated 2026-08-12 and PRM-UX links.
Verification:
  - python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check references
  - git diff --check
Files:
  - README.md
  - docs/README.md
  - docs/operator_quickstart.md
  - docs/operator_workflow.md
  - docs/PRODUCT_OPERATING_MODEL.md
  - docs/legacy_surfaces.md
  - docs/runbooks/assistant_runtime.md
  - docs/runbooks/archive_refresh.md
  - docs/runbooks/development.md
Context-Refs:
  - docs/prm_operator_experience_audit.md
  - docs/prm_operator_experience_roadmap.md
  - docs/PRODUCT_OPERATING_MODEL.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: compatibility docs are moved, archived, deleted, or renamed
Notes: |
  User problem: competing product eras make daily use unclear.
  Boundary: docs only; do not delete compatibility docs in this task.
  Failure behavior: stale operational detail must be labelled, not removed.
  Dogfood effect: required part of minimum PRM-19 start slice.

### PRM-UX-12: Usage-Derived Weekly Recap

Owner: codex
Phase: PRM-UX
Type: rag:generation workflow:autonomous eval:gate
Status: implemented
Depends-On: PRM-UX-10
Risk-Level: medium
Public-Tests-Required: required
Critic-Required: conditional
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Create a secondary weekly recap derived from actual PRM usage questions, reactions, saved notes, watches, project links, actions, experiments, and feedback rather than legacy report pipelines.
Acceptance-Criteria:
  - id: AC-1; description: recap builder uses operator production-test/usage receipts and confirmed memory events, not legacy Report V2 gate outputs; test: tests/test_prm_usage_weekly_recap.py::test_recap_uses_usage_receipts_not_report_v2.
  - id: AC-2; description: recap shows one main change, one action/study/watch-or-ignore item, reaction processing summary, project connection or honest zero, and feedback request; test: tests/test_prm_usage_weekly_recap.py::test_recap_contract.
  - id: AC-3; description: recap generation requires real operator usage evidence or an explicit fixture-only preview approval; test: tests/test_prm_usage_weekly_recap.py::test_recap_requires_usage_evidence.
Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_prm_usage_weekly_recap.py tests/test_weekly_brief_v3.py -q
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
Files:
  - src/output/weekly_brief_v3.py
  - src/output/prm_usage_weekly_recap.py
  - tests/test_prm_usage_weekly_recap.py
  - docs/personal_research_memory_product_contract.md
Context-Refs:
  - docs/prm19_dogfood_plan.md
  - docs/personal_research_memory_product_contract.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0 for deterministic/fixture path
  max_model_calls: 0 for deterministic/fixture path
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: scheduled generation, provider synthesis, or delivery is proposed
Notes: |
  User problem: weekly projection should summarize actual use, not restart reports.
  Boundary: secondary surface; fixture preview remains non-persistent until real operator usage exists.

### PRM-UX-13: Post-Production-Test Simplification And PRM-20 Handoff

Owner: codex
Phase: PRM-UX
Type: repo:hygiene project:governance
Status: implemented
Depends-On: PRM-UX-12
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
Objective: |
  Convert real operator production-test usage evidence into a simplification handoff that identifies which commands, docs, report surfaces, compatibility modules, and abstractions to keep, demote, archive, or leave untouched before PRM-20 cleanup.
Acceptance-Criteria:
  - id: AC-1; description: simplification table cites real operator usage evidence, current callers, migration risk, and verification command for every candidate; verify: docs/repo_hygiene_and_archive_plan.md contains evidence-backed candidate rows.
  - id: AC-2; description: no delete, move, archive, or rename action is performed without explicit human compatibility approval; verify: git diff contains no compatibility path deletion/move and approval checklist is open.
  - id: AC-3; description: PRM-20 handoff depends on production-test evidence and this simplification table; verify: docs/tasks.md PRM-20 Depends-On includes PRM-UX-13.
Verification:
  - python3 tools/playbook_validate.py --root . --check tasks --check references
  - git diff --check
  - git status --short
Files:
  - docs/repo_hygiene_and_archive_plan.md
  - docs/legacy_surfaces.md
  - docs/tasks.md
  - docs/EVIDENCE_INDEX.md
Context-Refs:
  - docs/repo_hygiene_and_archive_plan.md
  - docs/prm19_dogfood_plan.md
  - docs/prm_operator_experience_roadmap.md
Cost-Budget: |
  scope: task
  max_cost_usd: 0
  max_model_calls: 0
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: any compatibility delete, move, archive, or rename is proposed
Notes: |
  User problem: cleanup must follow usage evidence, not aesthetic preference.
  Boundary: handoff/planning only until PRM-20 approval.
  This task is a bridge from production-test evidence to canonical PRM-20 cleanup.
## PRM-MAT Queue — Mature Integrated Operator Product

The historical PRM-UX records above remain foundation evidence. These proposed successor tasks reconcile their actual integration maturity; none authorizes runtime activation, config writes, live fetch, dogfood, release claim, or compatibility cleanup.

### PRM-MAT-0: Integrated Maturity Audit And Task Truth Reconciliation

Owner: codex
Phase: A
Type: project:governance
Status: proposed
Depends-On: none
Risk-Level: medium
Public-Tests-Required: not_required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: not_required
Property-Required: not_required
Visual-Contract: not_applicable
Runtime-Verification: required
Correction-Budget: 2
User-Problem: The operator cannot distinguish a fixture, local runtime receipt, integrated path, and validated value claim.
Objective: Reconcile component maturity, current task evidence, CI state, runtime claims and documentation truth without changing product behavior.
Implementation-Boundary: Documentation/evidence only; preserve historic records.
Source-of-Truth: docs/prm_mature_product_gap_audit.md and git/test/CI evidence.
Files:
  - docs/prm_mature_product_gap_audit.md
  - docs/tasks.md
Schema-Interface-Changes: none
Privacy-Boundary: No private corpus/question text in audit artifacts.
Failure-Behavior: Report unresolved evidence as unknown, never inferred.
Acceptance-Criteria:
  - id: AC-1; description: Maturity matrix names all PRM-UX foundations with evidence class and gap; verify: rg -n "Existing PRM-UX component" docs/prm_mature_product_gap_audit.md.
Executable-Tests:
  - python3 tools/playbook_validate.py --root . --check tasks --check references
Verification:
  - python3 tools/playbook_validate.py --root . --check tasks --check references
Integration-Checks: Compare current bot path with documented component claims.
Eval-Impact: Establishes baselines only.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: none
Human-Approvals: none
Non-Goals: no code, DB or service change
Operator-Validation-Impact: prevents false validation claims

### PRM-MAT-1: Canonical OperatorContext And Primary Workflow Selection

Owner: codex
Phase: A
Type: rag:query agent:harness
Status: proposed
Depends-On: PRM-MAT-0
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: One request can receive conflicting route, workflow, project and date decisions.
Objective: Create one validated context and select exactly one deterministic primary workflow before retrieval.
Implementation-Boundary: Route/context only; no config migration, provider call, durable receipt or answer redesign.
Source-of-Truth: docs/operator_context_contract.md and rag answer gate.
Files:
  - src/assistant/operator_context.py
  - src/bot/handlers.py
  - tests/test_operator_context.py
Schema-Interface-Changes: operator_context.v1 in-memory contract only.
Privacy-Boundary: Hash chat identity; raw query is ephemeral unless approved policy changes.
Failure-Behavior: Low confidence emits one Russian clarification; safety gate wins.
Acceptance-Criteria:
  - id: AC-1; description: Each fixture request has one interaction ID and one allowed workflow; test: tests/test_operator_context.py::test_selects_one_workflow.
  - id: AC-2; description: Current-fact fixture cannot route to unsafe chat; test: tests/test_operator_context.py::test_current_fact_gate_wins.
Executable-Tests:
  - python3 -m pytest tests/test_operator_context.py tests/test_handlers.py -q
Verification:
  - python3 -m pytest tests/test_operator_context.py tests/test_handlers.py -q
Integration-Checks: Trace normal auto-command text and voice fixture through context into retrieval inputs.
Eval-Impact: Adds 50-case routing holdout scaffold.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: Preserve slash-command overrides.
Human-Approvals: none
Non-Goals: no LLM routing, persistent session or project config write
Operator-Validation-Impact: prerequisite for interpretable receipt evidence

### PRM-MAT-2: Professional Lens Runtime Integration

Owner: codex
Phase: A
Type: rag:query eval:gate
Status: proposed
Depends-On: PRM-MAT-1
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Lens preferences are lexical internal data that do not reliably improve answers.
Objective: Apply a bilingual phrase-based soft lens rerank and pass the selected lens to answer framing.
Implementation-Boundary: No default profile write; no recall filtering.
Source-of-Truth: docs/prm_mature_product_contract.md.
Files:
  - src/assistant/professional_personalization.py
  - src/assistant/memory_research.py
  - tests/test_professional_personalization.py
Schema-Interface-Changes: lens evidence/preferences fields only.
Privacy-Boundary: Local candidate metadata only.
Failure-Behavior: Unknown lens becomes neutral without reducing recall.
Acceptance-Criteria:
  - id: AC-1; description: Neutral versus lens ranking preserves candidate membership; test: tests/test_professional_personalization.py::test_lens_never_filters_recall.
  - id: AC-2; description: Russian/English cross-language fixtures show measured soft-rank deltas; test: tests/test_professional_personalization.py::test_bilingual_lens_rerank.
Executable-Tests:
  - python3 -m pytest tests/test_professional_personalization.py tests/test_memory_research.py -q
Verification:
  - python3 -m pytest tests/test_professional_personalization.py tests/test_memory_research.py -q
Integration-Checks: Confirm selected lens appears in reader DTO, not debug-only JSON.
Eval-Impact: Adds required neutral/AI, portfolio/writer and source-quality exceptions.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: Existing explicit lens IDs remain accepted.
Human-Approvals: Default durable lenses before profile write.
Non-Goals: hard filters or permanent inference
Operator-Validation-Impact: makes personalization measurable

### PRM-MAT-3: Project Portfolio V2 Configuration Migration

Owner: codex
Phase: A
Type: compliance:control tool:schema
Status: proposed
Depends-On: PRM-MAT-2
Risk-Level: critical
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Runtime project selection uses stale report-era descriptors rather than approved active work.
Objective: Introduce reviewed Portfolio V2 loading with compatibility mapping and explicit approval-gated config write.
Implementation-Boundary: Plan/read-only validation first; config mutation only after exact approval.
Source-of-Truth: docs/prm_configuration_migration_plan.md.
Files:
  - src/config/projects.yaml
  - src/assistant/project_portfolio_context.py
  - tests/test_project_portfolio_context.py
Schema-Interface-Changes: Versioned project descriptor only if durable compatibility boundary is approved.
Privacy-Boundary: No repo/private content in public diffs.
Failure-Behavior: Invalid/unapproved V2 config falls back to existing explicit named-project behavior.
Acceptance-Criteria:
  - id: AC-1; description: Approved active/priority and explicitly named watch/reference fixtures resolve deterministically; test: tests/test_project_portfolio_context.py::test_selection_policy.
  - id: AC-2; description: Rollback fixture restores old descriptor resolution; test: tests/test_project_portfolio_context.py::test_legacy_mapping_rollback.
Executable-Tests:
  - python3 -m pytest tests/test_project_portfolio_context.py tests/test_project_context.py -q
Verification:
  - python3 -m pytest tests/test_project_portfolio_context.py tests/test_project_context.py -q
Integration-Checks: Produce redacted approval diff and read-only config validation artifact.
Eval-Impact: Adds project selection and false project-action cases.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: Preserve old keyword/named links with rollback.
Human-Approvals: Exact descriptor and active/priority approval required.
Non-Goals: inferring status from absent repositories
Operator-Validation-Impact: makes project actions auditable

### PRM-MAT-4: Grounded Professional Synthesis And Unified Answer DTO

Owner: codex
Phase: A
Type: rag:generation agent:harness cost:architecture
Status: proposed
Depends-On: PRM-MAT-3
Risk-Level: critical
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Answer rendering hides professional workflow output and has no unified grounded contract.
Objective: Produce one validated professional answer DTO from shared context, evidence and project state with deterministic fallback.
Implementation-Boundary: Bounded synthesis contract only; provider path remains separately approval-gated.
Source-of-Truth: docs/prm_mature_product_contract.md.
Files:
  - src/assistant/memory_research.py
  - src/assistant/professional_workflows.py
  - tests/test_prm_professional_workflows.py
Schema-Interface-Changes: professional_answer.v1 with explicit compatibility adapter.
Privacy-Boundary: Provider sees only approved bounded cited snippets.
Failure-Behavior: Validator/provider failure returns labelled deterministic limited answer.
Acceptance-Criteria:
  - id: AC-1; description: Every source-derived fixture claim maps to a citation and one workflow; test: tests/test_professional_answer.py::test_claim_citation_and_single_workflow.
  - id: AC-2; description: Current-fact fixture returns verification_required without action; test: tests/test_professional_answer.py::test_current_fact_fallback.
Executable-Tests:
  - python3 -m pytest tests/test_prm_professional_workflows.py tests/test_memory_research.py -q
Verification:
  - python3 -m pytest tests/test_prm_professional_workflows.py tests/test_memory_research.py -q
Integration-Checks: Render DTO through existing research and brief paths.
Eval-Impact: Adds groundedness/action-specificity rubric.
Cost-Budget: approval_required_before_provider; max_model_calls=1; max_retries=1
Migration-Backward-Compatibility: Existing memory-research payload remains adapter-readable.
Human-Approvals: Provider budget/egress before live model use.
Non-Goals: autonomous browse/write/build approval
Operator-Validation-Impact: enables attributable professional answer labels

### PRM-MAT-5: Mature Telegram Conversation UX

Owner: codex
Phase: A
Type: project:governance
Status: proposed
Depends-On: PRM-MAT-4
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: required
Property-Required: conditional
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Primary Telegram UX exposes technical/runtime language and fragmented conversation state.
Objective: Render answer-first Russian UX, start/help commands, session boundaries and final-chunk actions from the shared DTO.
Implementation-Boundary: Renderer/copy/session policy; no durable proposal rewrite.
Source-of-Truth: docs/prm_mature_product_contract.md and docs/operator_context_contract.md.
Files:
  - src/bot/handlers.py
  - tests/test_handlers.py
  - docs/operator_quickstart.md
Schema-Interface-Changes: none
Privacy-Boundary: No IDs/path/debug data in normal messages.
Failure-Behavior: Friendly Russian local-evidence/expiry/clarification responses.
Acceptance-Criteria:
  - id: AC-1; description: Start-command fixture contains examples/boundaries/actions and no flag/runtime strings; test: tests/test_handlers.py::test_prm_start_is_operator_facing.
  - id: AC-2; description: Chunked answer attaches buttons only to final chunk; test: tests/test_handlers.py::test_actions_on_final_chunk.
Executable-Tests:
  - python3 -m pytest tests/test_handlers.py tests/test_telegram_delivery.py -q
Verification:
  - python3 -m pytest tests/test_handlers.py tests/test_telegram_delivery.py -q
Integration-Checks: Manual fixture screenshots reviewed for mobile line lengths and Russian-only copy.
Eval-Impact: Adds visual/length/language checks.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: Retain research, brief and chat command overrides.
Human-Approvals: Public screenshots only.
Non-Goals: dashboard or second bot
Operator-Validation-Impact: first coherent answer surface
### PRM-MAT-6: Durable Post-Answer Proposal And Confirmation Lifecycle

Owner: codex
Phase: B
Type: tool:unsafe compliance:audit
Status: proposed
Depends-On: PRM-MAT-5
Risk-Level: critical
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Save actions disappear on restart and can leak IDs or replay writes.
Objective: Replace volatile contexts with persistent chat-bound expiring idempotent proposal lifecycle.
Implementation-Boundary: Proposal storage/callback only; no automatic memory promotion.
Source-of-Truth: docs/prm_mature_product_contract.md.
Files:
  - src/assistant/prm_post_answer_actions.py
  - src/db/migrate.py
  - tests/test_prm_post_answer_actions.py
Schema-Interface-Changes: approved proposal table migration.
Privacy-Boundary: Store bounded summary/source refs; do not duplicate raw posts/questions.
Failure-Behavior: Expired/cancelled/replayed token performs no write and gives Russian message.
Acceptance-Criteria:
  - id: AC-1; description: Proposal survives restart fixture and binds correct chat; test: tests/test_prm_post_answer_actions.py::test_restart_and_chat_isolation.
  - id: AC-2; description: Repeat confirmation writes once; test: tests/test_prm_post_answer_actions.py::test_confirmation_idempotent.
Verification:
  - python3 -m pytest tests/test_prm_post_answer_actions.py -q
Integration-Checks: Callback payload is Telegram-limit-safe and final message has no internal IDs.
Eval-Impact: Adds replay/cancel/expiry/cross-chat suite.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: Keep existing confirmation semantics behind adapter.
Human-Approvals: Persistent schema migration and retention policy.
Non-Goals: unconfirmed durable writes
Operator-Validation-Impact: enables trustworthy saved-object evidence

### PRM-MAT-7: Automatic Interaction Receipts And Feedback Loop

Owner: codex
Phase: B
Type: compliance:audit cost:telemetry
Status: proposed
Depends-On: PRM-MAT-6
Risk-Level: critical
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: optional
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Useful-answer evidence is manual/schema-only and feedback is disconnected from answers.
Objective: Persist private transition-audited interaction ledger entries and update them via context-aware feedback.
Implementation-Boundary: Ledger and owner review/export only; no raw-question retention without approval.
Source-of-Truth: docs/prm_mature_product_contract.md.
Files:
  - src/db/prm19_dogfood_receipts.py
  - src/bot/handlers.py
  - tests/test_prm19_dogfood_receipts.py
Schema-Interface-Changes: approval-gated interaction ledger table.
Privacy-Boundary: Hash identity; exclude raw posts/provider payloads/public exports.
Failure-Behavior: Receipt failure does not lose answer; marks write status failed safely.
Acceptance-Criteria:
  - id: AC-1; description: Every answer fixture creates one receipt with unknown labels; test: tests/test_interaction_ledger.py::test_one_receipt_per_answer.
  - id: AC-2; description: Feedback button updates same interaction once; test: tests/test_interaction_ledger.py::test_feedback_transition_audit.
Verification:
  - python3 -m pytest tests/test_prm19_dogfood_receipts.py tests/test_interaction_ledger.py -q
Integration-Checks: Owner-only list/review and privacy-safe aggregate export fixture.
Eval-Impact: Supplies evaluation/recap inputs without value claim.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: Keep historical non-persisting PRM-19 builder.
Human-Approvals: Ledger migration and raw-question policy.
Non-Goals: dogfood start or public telemetry
Operator-Validation-Impact: creates auditable labels after approval

### PRM-MAT-8: Archive Freshness Orchestration And /refresh

Owner: codex
Phase: C
Type: workflow:autonomous rag:ingestion
Status: proposed
Depends-On: PRM-MAT-0
Risk-Level: critical
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Freshness is an opaque timer/manual command and the refresh command does not exist.
Objective: Define owner refresh orchestration with independent archive, reaction, vector and enrichment receipts.
Implementation-Boundary: No schedule/systemd activation without approval; preserve bounded ingestion rules.
Source-of-Truth: docs/prm_configuration_migration_plan.md.
Files:
  - src/assistant/prm_refresh_receipt.py
  - src/bot/handlers.py
  - tests/test_prm_refresh_receipt.py
Schema-Interface-Changes: refresh-run receipt only if durable need is approved.
Privacy-Boundary: Counts/timestamps only; no raw posts/log secrets.
Failure-Behavior: Archive success remains success when reaction fails; stale vector is explicit.
Acceptance-Criteria:
  - id: AC-1; description: Owner refresh fixture renders archive/reaction/vector/error independently; test: tests/test_prm_refresh_receipt.py::test_independent_statuses.
  - id: AC-2; description: Non-owner fixture cannot trigger refresh; test: tests/test_handlers.py::test_refresh_owner_only.
Verification:
  - python3 -m pytest tests/test_prm_refresh_receipt.py tests/test_handlers.py -q
Integration-Checks: Dry-run only; no live ingestion/vector rebuild/systemd action.
Eval-Impact: Adds freshness/failure-isolation checks.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: Retain approved CLI refresh command.
Human-Approvals: Schedule, timezone, rates and any canonical write.
Non-Goals: report/Radar/provider work
Operator-Validation-Impact: establishes visible freshness evidence

### PRM-MAT-9: Reaction Fast Lane And Adaptive Preference Proposals

Owner: codex
Phase: C
Type: rag:ingestion compliance:audit
Status: proposed
Depends-On: PRM-MAT-8
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Reactions are not a reliable recall/personalization path.
Objective: Connect personal reaction resolution, searchability, temporary boost, enrichment/proposal and receipt without permanent inference.
Implementation-Boundary: No reaction schedule/credential change; no atom dependency for recall.
Source-of-Truth: docs/prm_mature_product_contract.md.
Files:
  - src/db/reaction_fast_lane.py
  - src/ingestion/reaction_sync.py
  - tests/test_reaction_fast_lane.py
Schema-Interface-Changes: temporary reaction interest state only if approved.
Privacy-Boundary: Emoji is audit metadata, not preference text.
Failure-Behavior: Missing reaction means unknown; failure never blocks archive refresh.
Acceptance-Criteria:
  - id: AC-1; description: Successful reacted post is FTS searchable end-to-end; test: tests/test_reaction_fast_lane.py::test_reacted_post_recall.
  - id: AC-2; description: Repeated reaction proposes but cannot write preference; test: tests/test_reaction_fast_lane.py::test_preference_requires_confirmation.
Verification:
  - python3 -m pytest tests/test_reaction_fast_lane.py tests/test_reaction_sync.py -q
Integration-Checks: Render grouped reaction-recall fixture with source links/status.
Eval-Impact: Adds reaction searchability and weak-boost cases.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: Preserve existing reaction rows.
Human-Approvals: Reaction routine and durable preference policy.
Non-Goals: emoji sentiment or permanent implicit preference
Operator-Validation-Impact: provides two required validation questions

### PRM-MAT-10: Bounded Primary-Source Verification Execution

Owner: codex
Phase: D
Type: tool:call tool:unsafe compliance:control
Status: proposed
Depends-On: PRM-MAT-4
Risk-Level: critical
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Verification plans cannot confirm Telegram claims against trustworthy sources.
Objective: Implement bounded class-specific verification with cache and safe partial results behind explicit fetch approval.
Implementation-Boundary: GitHub/approved docs/vendor/arXiv metadata; no unrestricted browsing or code execution.
Source-of-Truth: docs/prm_mature_product_contract.md.
Files:
  - src/assistant/primary_source_verification.py
  - tests/test_primary_source_verification.py
  - docs/runbooks/primary_source_verification.md
Schema-Interface-Changes: separate external cache schema with TTL/hash/fetched-at.
Privacy-Boundary: Cache separate from archive; no raw corpus/provider payloads.
Failure-Behavior: SSRF/untrusted/timeout/content failure returns verification_required or partial.
Acceptance-Criteria:
  - id: AC-1; description: Fixture rejects private IP/redirect/content-size bypass; test: tests/test_primary_source_verification.py::test_network_boundaries.
  - id: AC-2; description: `www.*` is not sufficient official proof; test: tests/test_primary_source_verification.py::test_official_relation_required.
Verification:
  - python3 -m pytest tests/test_primary_source_verification.py -q
Integration-Checks: Fake transport traces Telegram versus primary evidence separately.
Eval-Impact: Adds source-class, SSRF, partial/support and cache cases.
Cost-Budget: max_fetches=3; max_retries=1; approval_required_before_live_fetch=true
Migration-Backward-Compatibility: Existing plan-only API remains safe default.
Human-Approvals: Live fetch, host policy, fetch/provider budget.
Non-Goals: automatic browse or third-party code execution
Operator-Validation-Impact: allows bounded verification questions after approval
### PRM-MAT-11: Queryable Saved Knowledge And Watch Topics

Owner: codex
Phase: B
Type: tool:schema tool:unsafe
Status: proposed
Depends-On: PRM-MAT-7
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Confirmed saved objects cannot reliably inform later questions or be managed by state.
Objective: Make confirmed notes/topics/links/decisions/actions/experiments/feedback/source cards queryable with history.
Implementation-Boundary: Confirmed objects only; no automatic conversation-to-memory conversion.
Source-of-Truth: docs/prm_mature_product_contract.md.
Files:
  - src/assistant/pi_memory.py
  - src/db/migrate.py
  - tests/test_pi_memory.py
Schema-Interface-Changes: approved object/state/history migration.
Privacy-Boundary: Save summaries/refs only; deletion/export follows retention policy.
Failure-Behavior: Duplicate returns proposal/link, not second object; failed state update preserves history.
Acceptance-Criteria:
  - id: AC-1; description: Topic/project/date/state query fixtures return cited saved objects; test: tests/test_saved_knowledge.py::test_query_filters.
  - id: AC-2; description: Closing action preserves prior history; test: tests/test_saved_knowledge.py::test_state_history.
Verification:
  - python3 -m pytest tests/test_pi_memory.py tests/test_saved_knowledge.py -q
Integration-Checks: Saved knowledge appears as secondary evidence, never supersedes fresh archive evidence.
Eval-Impact: Adds saved-memory recall cases.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: Map existing personal_memory_events.
Human-Approvals: Schema/retention/deletion policy.
Non-Goals: automatic note creation
Operator-Validation-Impact: enables saved-object count/usefulness evidence

### PRM-MAT-12: Professional Workflow End-To-End Integration

Owner: codex
Phase: D
Type: rag:generation eval:gate
Status: proposed
Depends-On: PRM-MAT-10
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Professional workflows are projections rather than reader-facing product slices.
Objective: Integrate each required workflow into shared context/evidence/DTO/Telegram/receipt/actions path.
Implementation-Boundary: One workflow slice per bounded subtask/PR; no generic multi-output answer.
Source-of-Truth: docs/prm_mature_product_contract.md.
Files:
  - src/assistant/professional_workflows.py
  - src/assistant/memory_research.py
  - tests/test_prm_professional_workflows.py
Schema-Interface-Changes: workflow-specific DTO sections only.
Privacy-Boundary: No fabricated portfolio/job-market proof.
Failure-Behavior: Missing evidence returns partial/no-action workflow result.
Acceptance-Criteria:
  - id: AC-1; description: Each workflow fixture renders mandated fields and one shared context ID; test: tests/test_prm_professional_workflows.py::test_end_to_end_workflows.
  - id: AC-2; description: Project action fixture requires direct evidence/current-goal acceptance criterion; test: tests/test_prm_professional_workflows.py::test_project_action_guard.
Verification:
  - python3 -m pytest tests/test_prm_professional_workflows.py tests/test_handlers.py -q
Integration-Checks: Verify visible Telegram sections and context-aware buttons for every workflow.
Eval-Impact: Adds workflow holdouts and anti-generic phrasing samples.
Cost-Budget: max_model_calls=1; max_retries=1; approval_required_before_provider=true
Migration-Backward-Compatibility: Keep current projections as adapters during rollout.
Human-Approvals: Provider usage if synthesis is enabled.
Non-Goals: automatic MVP/portfolio approval
Operator-Validation-Impact: supports 36 workflow questions

### PRM-MAT-13: Usage-Derived Weekly Recap V2

Owner: codex
Phase: E
Type: project:governance
Status: proposed
Depends-On: PRM-MAT-7, PRM-MAT-9, PRM-MAT-11, PRM-MAT-12
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: required
Property-Required: conditional
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Weekly recap is shallow and can confuse fixtures with real usage.
Objective: Project actual ledger/knowledge/reaction/action/verification use into a privacy-safe secondary recap.
Implementation-Boundary: No Report V2/Atlas/Frontier/Radar primary input.
Source-of-Truth: docs/prm_mature_product_contract.md.
Files:
  - src/output/prm_usage_weekly_recap.py
  - tests/test_prm_usage_weekly_recap.py
Schema-Interface-Changes: recap DTO only if durable export boundary needs it.
Privacy-Boundary: Aggregate/private local only; empty evidence says so.
Failure-Behavior: Missing usage produces explicit no-evidence recap.
Acceptance-Criteria:
  - id: AC-1; description: Fixture reports all nine target sections from ledger evidence; test: tests/test_prm_usage_weekly_recap.py::test_usage_projection.
  - id: AC-2; description: No-evidence fixture cannot claim change/usefulness; test: tests/test_prm_usage_weekly_recap.py::test_empty_usage_boundary.
Verification:
  - python3 -m pytest tests/test_prm_usage_weekly_recap.py -q
Integration-Checks: Confirm legacy report inputs are absent.
Eval-Impact: Adds recap provenance tests.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: Retain existing V3 as compatibility projection.
Human-Approvals: Any schedule/delivery change.
Non-Goals: report pipeline revival
Operator-Validation-Impact: summarizes real labels only

### PRM-MAT-14: Mature Evaluation And Holdout Suite

Owner: codex
Phase: E
Type: eval:gate eval:judge
Status: proposed
Depends-On: PRM-MAT-13
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Component tests do not prove cross-layer safety or professional usefulness.
Objective: Separate routing, retrieval, personalization, generation, write, verification and operator evaluation suites.
Implementation-Boundary: Fixtures/holdouts only; no threshold success claim.
Source-of-Truth: docs/prm_mature_acceptance_plan.md.
Files:
  - evals/prm_mat/
  - tests/test_test_tiers.py
  - docs/prm_mature_acceptance_plan.md
Schema-Interface-Changes: versioned eval manifests only.
Privacy-Boundary: Synthetic/redacted fixtures; no private corpus committed.
Failure-Behavior: Missing gold/human label remains unscored, not pass.
Acceptance-Criteria:
  - id: AC-1; description: Routing suite contains >=50 categorized holdouts; verify: python3 tools/prm_mat_eval.py --check routing.
  - id: AC-2; description: Write/verification suites exercise replay/SSRF negatives; verify: python3 tools/prm_mat_eval.py --check safety.
Verification:
  - python3 tools/prm_mat_eval.py --check all
Integration-Checks: CI tier maps focused/integration/security/full commands.
Eval-Impact: Creates authoritative holdout baseline.
Cost-Budget: no LLM judge required; judge calibration requires separate approval
Migration-Backward-Compatibility: Preserve existing RAG evals.
Human-Approvals: Thresholds and judge authority.
Non-Goals: generated labels as human evidence
Operator-Validation-Impact: defines measurement before collection

### PRM-MAT-15: Operations, Privacy, Cost, Backup, And Rollback

Owner: codex
Phase: E
Type: compliance:control cost:telemetry agent:recovery
Status: proposed
Depends-On: PRM-MAT-14
Risk-Level: critical
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Operator lacks one friendly health/freshness/cost/restore view and tested recovery boundary.
Objective: Define status, metrics, privacy retention, budgets, backup/restore and rollback runbooks with tested safe paths.
Implementation-Boundary: Do not install/start/change services or environment in this task without approval.
Source-of-Truth: docs/prm_mature_product_contract.md.
Files:
  - docs/runbooks/backup_restore.md
  - docs/runbooks/assistant_runtime.md
  - docs/COST_BUDGET.md
Schema-Interface-Changes: telemetry only after approved ledger policy.
Privacy-Boundary: No raw corpus in logs/receipts; hardened local data policy.
Failure-Behavior: Stale/provider/index failures are visible partials with safe fallback.
Acceptance-Criteria:
  - id: AC-1; description: Status fixture reports health/freshness/reaction/vector/budget without secrets; test: tests/test_prm_status.py::test_safe_status.
  - id: AC-2; description: Backup restore rehearsal artifact has checksum and rollback decision; verify: docs/runbooks/backup_restore.md contains rehearsal checklist.
Verification:
  - python3 -m pytest tests/test_prm_status.py -q
Integration-Checks: Dry-run/rehearsal only, no production mutation.
Eval-Impact: Adds failure/recovery budget assertions.
Cost-Budget: Provider/daily/monthly limits require explicit approval.
Migration-Backward-Compatibility: Retain existing safe runtime boundary.
Human-Approvals: Budgets, retention, encryption/permissions, operational schedule.
Non-Goals: service changes in planning
Operator-Validation-Impact: gives readable operational confidence signals
### PRM-MAT-16: Documentation, CI, And Developer Experience

Owner: codex
Phase: E
Type: eval:gate none
Status: proposed
Depends-On: PRM-MAT-15
Risk-Level: medium
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: conditional
Mutation-Required: conditional
Property-Required: not_required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Product docs, active runbooks and CI truth drift from the actual private assistant.
Objective: Consolidate product-first docs, runbooks, CI tier diagnosis and evidence index without deleting compatibility surfaces.
Implementation-Boundary: Documentation/CI config only; no broad refactor or legacy deletion.
Source-of-Truth: docs/prm_mature_product_gap_audit.md.
Files:
  - README.md
  - docs/README.md
  - .github/workflows/ci.yml
Schema-Interface-Changes: none
Privacy-Boundary: Demo fixtures/screenshots remain redacted.
Failure-Behavior: CI failure cause is recorded, not masked by local test success.
Acceptance-Criteria:
  - id: AC-1; description: Root README links product/quickstart/runbooks without systemd manual expansion; test: tests/test_repo_hygiene_handoff.py::test_readme_product_links.
  - id: AC-2; description: CI tier commands are documented and current failed workflow is diagnosed; verify: docs/EVIDENCE_INDEX.md contains CI run evidence.
Verification:
  - python3 tools/playbook_validate.py --root . --check references
Integration-Checks: Verify all active doc links and archived-surface labels.
Eval-Impact: CI runs focused/integration/security/full tiers.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: Legacy docs stay referenced as historical.
Human-Approvals: Public examples/screenshots.
Non-Goals: compatibility deletion
Operator-Validation-Impact: prevents misleading operating instructions

### PRM-MAT-17: Live Integration Smoke Acceptance

Owner: codex
Phase: F
Type: eval:gate workflow:autonomous
Status: proposed
Depends-On: PRM-MAT-5, PRM-MAT-6, PRM-MAT-7, PRM-MAT-8, PRM-MAT-9, PRM-MAT-10, PRM-MAT-11, PRM-MAT-12, PRM-MAT-14, PRM-MAT-15, PRM-MAT-16
Risk-Level: critical
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: required
Property-Required: required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Integrated behavior may differ from component fixtures.
Objective: Run an explicitly approved bounded manual smoke trace and record evidence without dogfood/release claim.
Implementation-Boundary: No dogfood start; no service/config/provider change outside approved trace.
Source-of-Truth: docs/prm_mature_acceptance_plan.md.
Files:
  - evals/prm_mat_smoke_receipt.json
  - docs/EVIDENCE_INDEX.md
Schema-Interface-Changes: none
Privacy-Boundary: Receipt is redacted/aggregate only.
Failure-Behavior: Any boundary failure blocks validation start.
Acceptance-Criteria:
  - id: AC-1; description: Approved smoke trace preserves interaction identity through answer, receipt and proposal; verify: python3 tools/prm_mat_smoke.py --check.
Verification:
  - python3 tools/prm_mat_smoke.py --check
Integration-Checks: One bounded real runtime trace after operator approval.
Eval-Impact: Confirms fixture-to-runtime parity only.
Cost-Budget: Explicit approved smoke budget.
Migration-Backward-Compatibility: none
Human-Approvals: Smoke runtime/provider/write scope.
Non-Goals: PRM-19 dogfood evidence
Operator-Validation-Impact: gate before four-week program

### PRM-MAT-18: Four-Week Operator Validation

Owner: operator
Phase: F
Type: eval:gate
Status: proposed
Depends-On: PRM-MAT-17
Risk-Level: critical
Public-Tests-Required: not_required
Critic-Required: required
Holdout-Required: not_required
Mutation-Required: not_required
Property-Required: not_required
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Mature product value has no real operator evidence.
Objective: Collect and review the approved 40-question private validation program.
Implementation-Boundary: Operator-led evidence only; no automatic success/release claim.
Source-of-Truth: docs/prm_operator_validation_plan.md.
Files:
  - docs/prm_operator_validation_plan.md
  - evals/prm_mat_operator_aggregate.json
Schema-Interface-Changes: none
Privacy-Boundary: Private ledger; committed aggregate excludes raw text.
Failure-Behavior: Unknown/missing labels do not count as useful.
Acceptance-Criteria:
  - id: AC-1; description: Aggregate records 40 categorized questions and labels provenance; verify: python3 tools/prm_mat_operator_eval.py --check.
Verification:
  - python3 tools/prm_mat_operator_eval.py --check
Integration-Checks: Weekly operator review records corrections and boundaries.
Eval-Impact: Produces sole user-value evidence source.
Cost-Budget: Operator-approved monthly budget.
Migration-Backward-Compatibility: none
Human-Approvals: Validation start and final interpretation.
Non-Goals: automatic dogfood/release success
Operator-Validation-Impact: this is the validation program

### PRM-MAT-19: Post-Validation Simplification And Release Candidate

Owner: codex
Phase: F
Type: project:governance
Status: proposed
Depends-On: PRM-MAT-18
Risk-Level: critical
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: required
Mutation-Required: conditional
Property-Required: conditional
Visual-Contract: required
Runtime-Verification: required
Correction-Budget: 2
User-Problem: Validated product can still retain needless complexity and unaddressed operator friction.
Objective: Convert approved evidence into bounded fixes, simplification candidates and a release-candidate decision packet.
Implementation-Boundary: No deletion/archive or release claim without separate approval.
Source-of-Truth: PRM-MAT-18 aggregate and docs/REVIEW_POLICY.md.
Files:
  - docs/prm_mature_product_gap_audit.md
  - docs/DECISION_LOG.md
Schema-Interface-Changes: none unless independently approved.
Privacy-Boundary: Aggregate evidence only.
Failure-Behavior: Unmet approved target remains blocked, not rationalized.
Acceptance-Criteria:
  - id: AC-1; description: Decision packet maps each gap to evidence, keep/fix/defer choice and approval; verify: docs/DECISION_LOG.md contains PRM-MAT-19 record.
Verification:
  - python3 tools/playbook_validate.py --root . --check readiness --check delivery
Integration-Checks: Re-run affected integration/holdout tests after each bounded correction.
Eval-Impact: Re-evaluates only changed slices.
Cost-Budget: No new provider spend without approval.
Migration-Backward-Compatibility: Compatibility changes are separately proposed.
Human-Approvals: Release candidate and any cleanup.
Non-Goals: self-declared release
Operator-Validation-Impact: turns evidence into explicit continuation choice

### PRM-MAT-20: Portfolio Case Packaging After Product Evidence

Owner: codex
Phase: F
Type: compliance:evidence
Status: proposed
Depends-On: PRM-MAT-19
Risk-Level: high
Public-Tests-Required: required
Critic-Required: required
Holdout-Required: not_required
Mutation-Required: not_required
Property-Required: not_required
Visual-Contract: required
Runtime-Verification: conditional
Correction-Budget: 2
User-Problem: Professional case material could overstate private-product evidence or expose private data.
Objective: Prepare approval-gated redacted case specification from verified product evidence.
Implementation-Boundary: Documentation/assets only after public-example approval.
Source-of-Truth: PRM-MAT-18/19 approved evidence.
Files:
  - docs/portfolio/case-study.md
  - docs/product_demo_spec.md
Schema-Interface-Changes: none
Privacy-Boundary: No raw Telegram text, question, secrets, local paths or unapproved screenshots.
Failure-Behavior: Insufficient/publicly unsafe evidence produces no case publication.
Acceptance-Criteria:
  - id: AC-1; description: Case draft labels maturity/evidence and passes privacy scan; test: tests/test_public_evidence.py::test_public_artifacts_are_redacted.
Verification:
  - python3 scripts/public_scorecard_demo.py --check
Integration-Checks: Human review approves every screenshot/example.
Eval-Impact: References approved aggregate evidence only.
Cost-Budget: max_cost_usd=0; max_model_calls=0; max_retries=0
Migration-Backward-Compatibility: none
Human-Approvals: Public portfolio examples and release wording.
Non-Goals: public launch
Operator-Validation-Impact: communicates evidence only after validation
