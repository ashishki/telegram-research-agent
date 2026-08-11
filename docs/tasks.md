# Active Task Graph

Status: proposed
Last updated: 2026-08-11
Playbook SHA: 5583eca96c4d2d480b5574ed78bea63e0b07ebf0
Target repo baseline: ad8689fa25b89f77122c4cec7c7a6b9da3f500cf

## Operating Rules

- Product work now flows through PBR and PRM only.
- Historical IRX work remains preserved in prior roadmaps and git history.
- Do not add new product tasks to IRX.
- Do not run live Telegram ingestion, reaction sync, Frontier, Radar, report
  generation, full archive LLM backfill, external embeddings, hosted vector
  services, or external web research jobs from backlog grooming. PRM-27 local
  vector sidecar indexing is authorized only inside ADR-004.
- Do not modify production database contents.
- Candidate retrieval queries are not gold evidence until the human operator
  approves expected evidence and citations.
- Human approval is required before accepting the product pivot ADR, starting
  dogfood, expanding vector work beyond ADR-004 local sidecar, approving
  external skills, or deleting compatibility files.
- Deep review is batched by milestone block. A task-level Critic-Required value
  means the task must be covered by the next block review, not that a separate
  deep-review agent must be run after every task.
- Immediate deep review still blocks continuation for privacy egress, unsafe
  writes, production data migration, vector backend adoption, external skill
  approval, dogfood start, release claims, or deletion/archive of compatibility
  files.

## Current Baseline

| Area | Status |
| --- | --- |
| Repository | Existing product, not greenfield; pre-retrofit commit ad8689fa25b89f77122c4cec7c7a6b9da3f500cf |
| Playbook | Current checkout pinned at 5583eca96c4d2d480b5574ed78bea63e0b07ebf0 |
| Product center | Pivot proposed from weekly report to Personal Telegram Research Memory + Grounded Assistant |
| Full archive search | Bounded SQLite FTS archive search plus PRM-27 local vector sidecar are implemented as local assistant retrieval slices; product RAG gates remain required before dogfood |
| Current SQLite FTS | Hardened as the persistent baseline for bounded archive search; PRM-27 adds an optional local vector sidecar without replacing FTS |
| PI assistant retrieval | Uses bounded curated and SQLite FTS archive tools; hybrid local vector retrieval is available behind explicit local flags; broad raw corpus provider egress remains forbidden |
| Knowledge Library | Deterministic PRM-13 topic-page DTO and static HTML renderer implemented for bounded supplied topic evidence; not dogfooded or released |
| Project context support | Deterministic PRM-14 assistant tool combines active project descriptors, bounded archive retrieval, and curated knowledge into direct_implication, weak_watch, learning_relevance, or no_match labels without build/code/project mutation approval |
| Local operator UX | `memory ask` gives a local-only evidence brief over bounded archive/curated/project context with no LLM calls, external search, startup migrations, service starts, or writes |
| LLM chat UX | PRM-18A contract, PRM-18B CLI harness, and PRM-18C Telegram UX/runbook implemented; Telegram provider-egress/router flags are enabled for manual testing, not dogfood |
| Research session assistant | Polished project-aware archive-plus-linked-source assistant target is documented by PRM-21; PRM-22 fixture-first linked-source resolver/cache, PRM-23 bounded `memory research` planner, and PRM-27 optional local hybrid retrieval are implemented; PRM-19 dogfood is still not started |
| Learning state | PRM-15 fixture-only migration/projection maps legacy source presence to indexed/surfaced only and requires explicit receipts for opened/read/understood/explained/tried/applied/measured |
| Weekly Brief V3 | PRM-16 deterministic secondary projection and static HTML renderer implemented for bounded supplied context; V1 Brief and Atlas are demoted to compatibility/internal surfaces |
| Runtime workflows | PRM-17 deterministic workflow registry and privacy-safe aggregate telemetry receipt implemented; scheduled runtime activation is not approved |
| Release gate | PRM-18 deterministic release/dogfood gate implemented; current post-PRM28 receipt records deterministic local no-vector RAG readiness, and PRM-27 local vector sidecar is implemented after a successor ADR, but PRM-19 dogfood is still not started |
| Runtime deployment | Legacy `telegram-bot.service` and `telegram-ai-split-report.timer` stopped and disabled on 2026-07-29; safe `telegram-prm-assistant.service` is installed/enabled/running for manual operator testing as of 2026-08-11 18:27 CEST; startup migrations remain skipped and this is not PRM-19 dogfood evidence |
| PRM-13..17 review gate | Batched deep review recorded; one telemetry budget-validation finding fixed before PRM-18 |
| PRM-18A..18C review gate | Batched deep review recorded on 2026-08-03; no unresolved stop-ship finding in this block, residual provider/runtime risks remain gated before PRM-19 |
| W29 reports | V1 Brief and Atlas rendered despite V2 preview code existing elsewhere |
| W29 reactions | Seven personal reactions resolved to posts, zero atoms, zero themes, zero ranking effects |
| Radar | Historical W29 Radar stage failed; PRM-16 V3 fixtures localize Radar failure to the Radar card |
| Dogfood | Not started for the new product; PRM-19 remains blocked until explicit human dogfood-start approval is recorded |

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
PRM-28 -> PRM-19 -> PRM-20
PRM-24..PRM-28 formalize the required full product RAG path. PRM-26 refines
the older PRM-8 hybrid/vector backend gate. PRM-27 is allowed only inside the
ADR-004 local-sidecar scope: no external embeddings, no hosted vector service,
no canonical DB mutation, no live web research, and no dogfood start.
```

## PBR Queue - Playbook Retrofit

### PBR-0: Current Playbook Differential Audit

Owner: codex
Phase: PBR
Type: project:governance
Status: proposed
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
Status: proposed
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
Status: proposed
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
Status: proposed
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
Status: proposed
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
Status: proposed
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
Status: proposed
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
Status: proposed
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
Status: proposed
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

### PRM-19: Four-Week Operator Dogfood

Owner: human
Phase: PRM
Type: eval:gate
Status: blocked
Depends-On: PRM-18C, PRM-28
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
  Run the actual product for four weeks and record real questions, useful answers, corrections, saved notes, watch topics, decisions, recovered reactions, time to useful answer, weekly cost, value score, friction score, and continuation decision.
Acceptance-Criteria:
  - id: AC-1; description: at least 30 real operator questions are recorded with privacy-safe metadata and usefulness labels; verify: dogfood receipt count and label coverage.
  - id: AC-2; description: saved notes, watch topics, project or life decisions, rejected answers, and corrections are counted separately; verify: dogfood summary table.
  - id: AC-3; description: continuation decision is based on value, friction, latency, cost, and user desire to keep using it; verify: human dogfood decision record.
Verification:
  - dogfood receipt review by human operator
Files:
  - docs/dogfood_4_week_plan.md
  - docs/EVIDENCE_INDEX.md
Context-Refs:
  - docs/final_acceptance_plan.md
  - docs/PRIVACY_THREAT_MODEL.md
Cost-Budget: |
  scope: phase
  max_cost_usd: 0 until human-approved dogfood budget is recorded
  max_model_calls: 0 until human-approved dogfood budget is recorded
  max_tool_calls: n/a
  max_retries: 1 per failed workflow
  approval_required_when: weekly budget or provider egress changes
Notes: |
  Do not predefine success as the system ran. PRM-28 now passes the accepted
  no-vector product RAG gate, and the current PRM-18 post-PRM28 receipt clears
  deterministic local stop-ship blockers. PRM-19 still cannot start until the
  human operator explicitly approves dogfood start.

### PRM-20: Post-Dogfood Simplification, Cleanup, And Archive

Owner: codex
Phase: PRM
Type: repo:hygiene
Status: blocked
Depends-On: PRM-19
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
  Use real dogfood evidence to remove unused reports, commands, modules, docs, and abstractions, split oversized modules only where maintenance evidence justifies it, archive historical IRX surfaces safely, and make one primary product path visible.
Acceptance-Criteria:
  - id: AC-1; description: each delete, archive, or move candidate cites current callers, dogfood evidence, migration risk, and verification command; verify: cleanup plan rows are updated before edits.
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
Cost-Budget: |
  scope: task
  max_cost_usd: 1.00
  max_model_calls: 10
  max_tool_calls: n/a
  max_retries: 1
  approval_required_when: deletion or archive affects compatibility surface
Notes: |
  Cleanup follows usage evidence; it is not a precondition for PRM-4. PRM-20 is
  currently blocked by missing PRM-19 dogfood evidence and requires explicit
  human approval before compatibility files are archived, deleted, or moved.

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
