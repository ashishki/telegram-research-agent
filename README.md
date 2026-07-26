# Telegram Research Agent

Private, single-operator Telegram research system.

Current direction: **Personal Telegram Research Memory + Grounded Assistant**.
The old weekly-report pipeline remains in the repository as compatibility and
implementation history, but it is no longer the product center.

## Current Status

Planning retrofit only. As of this repository state, the system does **not**
yet provide full-archive assistant search, hybrid RAG, Knowledge Library topic
pages, confirmation-gated Knowledge Notes, or a proven dogfood result.

Verified baseline before this retrofit:

- target repo commit inspected:
  `ad8689fa25b89f77122c4cec7c7a6b9da3f500cf`
- Playbook commit used:
  `5583eca96c4d2d480b5574ed78bea63e0b07ebf0`
- local SQLite has `raw_posts`, `posts`, and `posts_fts`
- PI Assistant search is curated-only and explicitly excludes raw Telegram
  archive retrieval
- W29 delivered Brief/Atlas artifacts use `split_ai_report.v1`
- W29 detected 7 personal reacted posts, but 0 linked atoms, 0 linked topics,
  and 0 ranking effects

## Product Direction

North star:

```text
Search everything.
Enrich what matters.
Save what proves useful.
Generate reports only as a secondary projection.
```

The target product has one conversational entrypoint. A natural-language
question should return a concise answer, relevant Telegram context, concrete
Telegram source links, freshness boundaries, contradictions or uncertainty,
and `insufficient_evidence` when the archive does not support the answer.

## Implemented Today

- Telegram ingestion into local SQLite.
- Normalized `posts` and `posts_fts` storage.
- Knowledge Atom and Idea Thread infrastructure.
- V1 weekly Brief and Knowledge Atlas compatibility artifacts.
- IRX V2 preview infrastructure in code, but not the delivered W29 surface.
- Read-only Hermes/PI facade over curated intelligence items.
- Reaction snapshot and receipt infrastructure.
- Report V2 rollout gate and historical IRX task record.

## Planned, Not Yet Implemented

- Persistent full-archive FTS assistant search as the first value milestone.
- Reaction fast lane where reacted posts are searchable even when enrichment
  fails.
- Selective enrichment into cases, tools, practices, warnings, claims, topics,
  notes, watch topics, decisions, and experiments.
- Retrieval evaluation over a human-approved gold query set.
- Hybrid/vector retrieval only after FTS baseline failures justify it.
- Knowledge Library topic pages as the primary saved-knowledge experience.
- Weekly Brief V3 as a secondary projection from actual usage.

## Unsupported Claims

Do not claim:

- full Telegram archive RAG exists;
- the assistant can search every retained post;
- vector retrieval is selected or installed;
- W29 proved user value;
- four-week dogfood has started;
- public/portfolio value is proven.

Public evidence boundary: this remains a secondary portfolio project with
0/4 verified public dogfood weeks. The current public ledger is
docs/evidence/public_dogfood_status.json. The committed public scorecard demo is
synthetic evidence; it is not a dogfood run.

## Primary Operator Workflow

Planned v1 workflow:

1. Ask Hermes a natural-language question.
2. Hermes searches the Telegram archive and, when useful, curated knowledge.
3. Hermes answers with Telegram source links and evidence boundaries.
4. If the answer is useful, Hermes proposes a Knowledge Note, Watch Topic,
   project link, decision, action, or experiment.
5. Nothing is saved permanently without explicit confirmation.

## Main Local Commands

```bash
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
python3 tools/verify_project.py --root .
python3 -m pytest tests/ -q
```

Legacy operational commands remain available for compatibility, but do not use
them as proof that the new product exists:

```bash
python3 src/main.py ingest
python3 src/main.py sync-reactions --days 14
python3 src/main.py weekly-intelligence-v2 --week 2026-W28 --threads-limit 24 --atoms-limit 8
python3 src/main.py report-v2-rollout-gate --week 2026-W28 --json
```

Do not run live ingestion, reaction sync, report generation, Frontier, Radar,
LLM extraction, embeddings, or full archive indexing during planning-only
sessions.

## Canonical Docs

- [Project Brief](docs/PROJECT_BRIEF.md)
- [Product Pivot Audit](docs/product_pivot_current_state_audit.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation Contract](docs/IMPLEMENTATION_CONTRACT.md)
- [Product Contract](docs/personal_research_memory_product_contract.md)
- [Roadmap](docs/personal_research_memory_roadmap.md)
- [Final Acceptance Plan](docs/final_acceptance_plan.md)
- [Active Tasks](docs/tasks.md)
- [Codex Handoff](docs/CODEX_PROMPT.md)

Private generated outputs under `data/output/**` remain ignored by default.
