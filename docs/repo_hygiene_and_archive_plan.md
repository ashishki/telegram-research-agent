# Repo Hygiene And Archive Plan

Status: draft; cleanup is blocked until PRM-4 and initial retrieval eval

## Inventory

| Category | Paths | Current status |
| --- | --- | --- |
| active runtime modules | `src/ingestion`, `src/processing`, `src/db`, `src/main.py` | preserve |
| active assistant/RAG modules | `src/assistant`, `src/output/intelligence_retrieval_items.py`, `src/assistant/semantic_retrieval.py` | reusable but curated-only |
| V1 compatibility modules | `src/output/weekly_intelligence_brief.py`, `src/output/knowledge_atlas_report.py`, split report paths | keep until PRM-16 |
| IRX V2 modules | `src/output/weekly_intelligence_brief_v2.py`, `src/output/knowledge_atlas_report_v2.py`, `src/output/report_v2_rollout.py` | historical/reusable |
| legacy report generators | digest, recommendations, study plan, visual report modules | classify after dogfood |
| generated private artifacts | `data/output/**` | ignored; do not commit new private outputs |
| public sanitized fixtures | `examples/public_scorecard_demo`, `tests/fixtures` | preserve |
| historical docs | `docs/intelligence_report_v2_*`, `docs/portfolio_*`, `docs/archive/**` | preserve as history |
| duplicate docs | `docs/ARCHITECTURE.md` vs `docs/architecture.md` | uppercase canonical, lowercase legacy |
| systemd units | `systemd/*` | stale status unverified |

## Cleanup Candidates

| Path | Current callers | Why it may be obsolete | Evidence needed | Earliest milestone | Verification |
| --- | --- | --- | --- | --- | --- |
| `docs/architecture.md` | historical docs | superseded by uppercase canonical architecture | references migrated or labelled | PBR-7 | `rg "docs/architecture.md"` |
| `docs/intelligence_report_v2_roadmap.md` | README/history | active IRX queue closed | PRM path adopted and linked | PRM-20 | doc link check |
| `src/output/weekly_intelligence_brief.py` | orchestrator/tests | V1 report surface | Brief V3 proven and compatibility adapter exists | PRM-20 | pytest affected report tests |
| `src/output/knowledge_atlas_report.py` | orchestrator/tests | V1 Atlas audit surface | Knowledge Library and Audit Explorer split proven | PRM-20 | pytest affected atlas tests |
| `src/assistant/semantic_retrieval.py` | PI facade/tests | curated-only transient search may be superseded | archive search and curated search merged behind new facade | PRM-13 | assistant tool tests |
| `systemd/telegram-ai-split-report.*` | deployment docs | report-centered timer | new workflow runbook and dogfood evidence | PRM-17 | systemd dry-run/doc check |

## Rules

- Do not start a broad refactor before PRM-4.
- Do not delete history to make the repo look cleaner.
- Split oversized modules only when usage evidence shows maintenance pain.
- Generated private outputs remain ignored.
- Final user path must become visible within five minutes after PRM-20.
