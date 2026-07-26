# Playbook Retrofit Audit

Date: 2026-07-26

Target repo commit inspected:
`ad8689fa25b89f77122c4cec7c7a6b9da3f500cf`

AI Workflow Playbook commit used:
`5583eca96c4d2d480b5574ed78bea63e0b07ebf0`

## Required State Commands Run

Target repository:

- `git status`: clean on `master`
- `git branch --show-current`: `master`
- `git log --oneline -30`: latest commit `ad8689f ci: expose public evidence boundary`
- `git diff --stat`: no output before edits
- `git ls-files | sort`: recorded in session output
- `git rev-parse HEAD`: `ad8689fa25b89f77122c4cec7c7a6b9da3f500cf`

Playbook repository:

- `git status`: clean on `master`
- `git branch --show-current`: `master`
- `git log --oneline -20`: latest commit `5583eca docs: add runnable RAG eval example and smoke reports`
- `git rev-parse HEAD`: `5583eca96c4d2d480b5574ed78bea63e0b07ebf0`

## Initializer Inspection

Command run:

```bash
python3 /srv/openclaw-you/workspace/AI_workflow_playbook/tools/init_playbook_project.py --help
```

Current initializer supports:

- `--mode {lean-core,lean,standard,strict}`
- `--project-name`
- `--operational-pain`
- `--current-workaround`
- `--first-proof-metric`
- `--verify-argv`
- `--with-cost-architecture`
- `--with-rag-eval`
- `--external-skill`
- `--install-claude-hooks`
- `--force`
- `--dry-run`

Safe proposed command was dry-run only:

```bash
python3 /srv/openclaw-you/workspace/AI_workflow_playbook/tools/init_playbook_project.py . \
  --mode standard \
  --project-name telegram-research-agent \
  --operational-pain "Weekly report artifacts omit reacted posts and do not provide full-archive grounded assistant search for the private Telegram corpus." \
  --current-workaround "Operator manually inspects generated reports, Telegram history, and repository artifacts to recover useful posts and verify claims." \
  --first-proof-metric "A human-approved query set can retrieve exact Telegram source links from the canonical archive without requiring Knowledge Atoms." \
  --verify-argv '["{python}", "-m", "pytest", "tests/", "-q"]' \
  --with-cost-architecture \
  --with-rag-eval \
  --dry-run
```

Verdict: direct initialization into the target was not used because it would
create `docs/ARCHITECTURE.md` while `docs/architecture.md` already existed and
would skip existing authority docs without reconciliation.

## Reconciliation Action

- Created `docs/ARCHITECTURE.md` as the new canonical pivot architecture.
- Marked `docs/architecture.md` as legacy report-era reference.
- Updated `docs/IMPLEMENTATION_CONTRACT.md` instead of accepting generated
  template defaults.
- Updated `docs/tasks.md` to PBR/PRM queues instead of preserving IRX as active.
- Copied current Playbook tools, schemas, and templates mechanically from the
  pinned Playbook checkout and generated verifier scaffold in `/tmp`.
- Added `jsonschema>=4.18.0` to `requirements.txt` because the pinned Playbook
  validator requires `Draft202012Validator`.
- Did not use `--force`.
- Did not install Claude hooks.
- Did not pass external-skill activation flags.

## Artifact Inventory

| Artifact | Pre-retrofit state | Retrofit state |
| --- | --- | --- |
| `docs/PROJECT_BRIEF.md` | missing | created |
| `docs/ARCHITECTURE.md` | missing | created as canonical |
| `docs/architecture.md` | existing report-era authority | preserved, labelled legacy |
| `docs/IMPLEMENTATION_CONTRACT.md` | existing report-centered v3 | updated to v4 proposed pivot contract |
| `docs/spec.md` | existing supporting spec | updated as proposed pivot product spec |
| `docs/tasks.md` | existing IRX active backlog | replaced with compact PBR/PRM queues |
| `docs/CODEX_PROMPT.md` | existing long handoff | updated as compact Playbook handoff |
| `AGENTS.md` | missing | created as handoff pointer |
| `docs/DECISION_LOG.md` | missing | created |
| `docs/IMPLEMENTATION_JOURNAL.md` | missing | created |
| `docs/EVIDENCE_INDEX.md` | missing | created |
| `docs/REVIEW_POLICY.md` | missing | created |
| `docs/README.md` | existing docs index | updated |
| `.playbook/project_verification.json` | missing | created |
| `.playbook/delivery_execution_model.json` | missing | created |
| `tools/playbook_validate.py` | missing | copied from Playbook |
| `tools/verify_project.py` | missing | generated from Playbook initializer |
| `tools/receipt_run.py` | missing | copied from Playbook |
| `schemas/task.schema.json` | missing | copied from Playbook |
| `templates/tasks_schema.md` | missing | copied from Playbook |
| CI workflow files | `.github/workflows/ci.yml` existed | preserved, not overwritten |
| external-skill trust records | missing | trust tasks documented; no skill approved |

## Conflicting Authority Docs

- `docs/ARCHITECTURE.md` vs `docs/architecture.md`: uppercase is canonical
  after this retrofit; lowercase remains legacy until PBR-7 migration.
- `docs/IMPLEMENTATION_CONTRACT.md` old v3 vs proposed v4: v4 records the pivot
  but product implementation still waits on ADR acceptance.
- `docs/tasks.md` old IRX queue vs new PBR/PRM queue: IRX is historical;
  PBR/PRM are active.
- `docs/hermes_pi_assistant_roadmap.md` and
  `docs/curated_semantic_retrieval.md` still reject raw archive RAG as current
  scope; they remain component history until PRM tasks update runtime docs.

## Playbook Fit Decisions

- Adoption mode: Standard.
- RAG: ON.
- Tool-Use: ON.
- Agentic: ON because current/target assistant behavior uses a bounded
  multi-tool loop; this does not imply high-autonomy runtime.
- Planning: OFF.
- Compliance: OFF.
- Autonomous workflow module: required for ingestion, indexing, enrichment
  queue, reaction fast lane, and weekly routines.
- Runtime tier: T1.
- Hermes Agent reuse: `pattern_only`, not direct runtime dependency.
- Delivery model: Codex Direct bootstrap, split_orchestrated ongoing delivery.

## Hermes Reuse Gate

Official sources checked on 2026-07-26:

- `https://github.com/nousresearch/hermes-agent`
- `https://hermes-agent.nousresearch.com/docs/`

Classification: `pattern_only`.

Reason: official Hermes Agent provides a broad persistent gateway/skills/learning
runtime. This project only needs bounded tool catalog, messaging-interface
patterns, confirmation gates, and session-memory separation. T3 runtime needs
are not proven.

## External Skill Inventory

| Skill or capability | Status | Required action |
| --- | --- | --- |
| `reddit-skill` | project-disabled | create trust record before any use |
| `x-research` | project-disabled | create trust record before any use |
| `yandex-search-api` | project-disabled | create trust record before any use |
| `yandex-wordstat` | project-disabled | create trust record before any use |
| `telegram-channel-parser` | project-disabled | create trust record before any use |
| `crawl4ai-seo` | project-disabled | create trust record before any use |
| Hermes/community skill | rejected for v1 runtime | reconsider only through ADR |
| Archify/visualization skill | project-disabled for PRM v1 | trust record required before product use |

No external skill is approved or activated by this planning session.
