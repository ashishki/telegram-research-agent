# Cognition Manifest - Telegram Research Agent

---
artifact_kind: retrieval_manifest
project: telegram-research-agent
source_repo: telegram-research-agent
status: active
canonical: false
generated: false
tags: [private-research, deterministic-scoring, memory, cognition]
---

Version: 1.0
Last updated: 2026-05-25

## Purpose

Repo-local map that translates the project's existing runtime memory architecture into playbook-style engineering cognition surfaces.

## Authority Rules

- Code, tests, runtime docs, and database schema are authoritative.
- Runtime research memory is product data; it is not a cross-project engineering memory source unless summarized in reviewed docs.
- Obsidian and generated indexes are optional navigation layers.

## Project Identity

| Field | Value |
|-------|-------|
| Primary shape | Private deterministic research pipeline with bounded LLM generation |
| Governance level | Lean/Standard |
| Runtime tier | T1 private VPS |
| Active profiles | Operational memory, deterministic scoring, evidence preservation |

## Canonical Truth

| Surface | Path | Notes |
|---------|------|-------|
| Architecture | `docs/architecture.md`, `docs/memory_architecture.md` | System and memory model |
| Contract | `docs/IMPLEMENTATION_CONTRACT.md` | Implementation rules |
| Task graph | `docs/tasks.md` | Current backlog |
| Session state | `docs/CODEX_PROMPT.md` | Workflow state |
| Spec | `docs/spec.md` | System specification |
| Memory inspection | `docs/memory_inspection.md` | Debug commands |
| Operator workflow | `docs/operator_workflow.md` | Human workflow |
| Runtime schema | `src/db/schema.sql` | Product memory/storage truth |
| Audits/archive | `docs/archive/`, `docs/audit/` | Review history |

## Retrieval Scopes

| Scope | Start here | Include next |
|-------|------------|--------------|
| Scoring change | `src/config/scoring.yaml`, `src/processing/score_posts.py` | tests and project diagnostics docs |
| Project relevance | `src/config/projects.yaml`, `docs/memory_architecture.md` | diagnostics tests and operator workflow |
| Runtime memory issue | `docs/memory_inspection.md` | DB schema, evidence tests, archive reviews |
| Digest/report quality | `docs/report_format.md` | output tests, prompt docs, evidence tests |
| Reviewer packet | task ACs and contract | architecture/memory docs, relevant tests |

## Local/VPS Agent Context Workflow

Agents do not automatically discover the cognition vault. The operator or orchestrator must pass a repo-local manifest, vault project map, or generated context packet path into the agent task.

Expected sibling layout on any machine that runs agents:

```text
ai-stack/
|-- projects/<repo>/
`-- engineering-cognition-vault/
```

Local project work:

```bash
cd ai-stack/engineering-cognition-vault
./scripts/sync_from_projects.sh --no-pull --commit --push
```

VPS project work:

1. Commit and push code, docs, evals, ADRs, findings, or postmortems in this repo.
2. Refresh the vault on the machine that owns vault sync:

```bash
cd ai-stack/engineering-cognition-vault
git pull --ff-only
./scripts/sync_from_projects.sh --commit --push
```

If an agent runs on the VPS, clone the vault next to `projects/` and pass packet paths explicitly:

```text
../engineering-cognition-vault/10-projects/<project>.md
../engineering-cognition-vault/90-context-packets/<role>-<project>-<scope>.md
```

Do not write canonical decisions, eval results, or findings directly into the vault. Write them into this repo first, then regenerate the vault.

---

## Known Gaps

| Gap | Impact | Migration step |
|-----|--------|----------------|
| No playbook-style `docs/DECISION_LOG.md` | Decisions live across docs and archive | Add decision log only for future architecture/runtime changes |
| No playbook-style `docs/EVIDENCE_INDEX.md` | Proof lookup depends on tests and memory docs | Add evidence index if recurring findings or eval baselines expand |
| No ADR directory | Decision lineage is harder to traverse | Create ADRs only for new major memory/runtime changes |

## Generated Artifacts

| Artifact | Path | Policy |
|----------|------|--------|
| Cognition index | `generated/cognition/index.json` | Optional generated artifact; exclude raw Telegram exports |
| Context packets | `docs/context-packets/` | Commit only major review/regression packets |

