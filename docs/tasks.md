# Active Task Graph

Status: proposed
Last updated: 2026-07-29
Playbook SHA: 5583eca96c4d2d480b5574ed78bea63e0b07ebf0
Target repo baseline: ad8689fa25b89f77122c4cec7c7a6b9da3f500cf

## Operating Rules

- Product work now flows through PBR and PRM only.
- Historical IRX work remains preserved in prior roadmaps and git history.
- Do not add new product tasks to IRX.
- Do not run live Telegram ingestion, reaction sync, Frontier, Radar, report
  generation, full archive LLM backfill, embeddings, or external web research
  jobs from backlog grooming.
- Do not modify production database contents.
- Candidate retrieval queries are not gold evidence until the human operator
  approves expected evidence and citations.
- Human approval is required before accepting the product pivot ADR, starting
  dogfood, adopting a vector backend, approving external skills, or deleting
  compatibility files.
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
| Full archive search | Bounded SQLite FTS archive search is implemented as the local assistant retrieval slice; vector/hybrid retrieval remains blocked |
| Current SQLite FTS | Hardened as the persistent baseline for bounded archive search; not replaced by embeddings/vector storage |
| PI assistant retrieval | Uses bounded curated and SQLite FTS archive tools; broad raw corpus provider egress remains forbidden |
| Knowledge Library | Deterministic PRM-13 topic-page DTO and static HTML renderer implemented for bounded supplied topic evidence; not dogfooded or released |
| Project context support | Deterministic PRM-14 assistant tool combines active project descriptors, bounded archive retrieval, and curated knowledge into direct_implication, weak_watch, learning_relevance, or no_match labels without build/code/project mutation approval |
| Learning state | PRM-15 fixture-only migration/projection maps legacy source presence to indexed/surfaced only and requires explicit receipts for opened/read/understood/explained/tried/applied/measured |
| Weekly Brief V3 | PRM-16 deterministic secondary projection and static HTML renderer implemented for bounded supplied context; V1 Brief and Atlas are demoted to compatibility/internal surfaces |
| W29 reports | V1 Brief and Atlas rendered despite V2 preview code existing elsewhere |
| W29 reactions | Seven personal reactions resolved to posts, zero atoms, zero themes, zero ranking effects |
| Radar | Historical W29 Radar stage failed; PRM-16 V3 fixtures localize Radar failure to the Radar card |
| Dogfood | Not started for the new product |

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
PRM-10/PRM-11/PRM-12/PRM-16/PRM-17 -> PRM-18 -> PRM-19 -> PRM-20
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
Status: blocked
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
Status: planned
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
Status: planned
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
  - id: AC-1; description: all ten end-to-end acceptance scenarios have pass, fail, or blocked status with evidence links; verify: final acceptance receipt contains scenario table.
  - id: AC-2; description: Test Critic and privacy review findings are resolved or explicitly accepted by the human; verify: review receipt references approvals.
  - id: AC-3; description: dogfood gate blocks on private-data leakage, unsupported claims, retrieval metric failure, unsafe writes, or cost budget breach; verify: gate output shows blocking reasons.
Verification:
  - python3 -m pytest tests/ -q
  - evaluation and security review commands documented in release receipt
Files:
  - evals/
  - tests/
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
  Do not start dogfood while stop-ship criteria remain.

### PRM-19: Four-Week Operator Dogfood

Owner: human
Phase: PRM
Type: eval:gate
Status: planned
Depends-On: PRM-18
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
  Do not predefine success as the system ran.

### PRM-20: Post-Dogfood Simplification, Cleanup, And Archive

Owner: codex
Phase: PRM
Type: repo:hygiene
Status: planned
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
  Cleanup follows usage evidence; it is not a precondition for PRM-4.
