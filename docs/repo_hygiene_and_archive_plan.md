# Repo Hygiene And Archive Plan

Status: draft; cleanup/archive work requires operator production-test evidence
and explicit human compatibility-file approval

## Inventory

| Category | Paths | Current status |
| --- | --- | --- |
| active runtime modules | `src/ingestion`, `src/processing`, `src/db`, `src/main.py` | preserve |
| active assistant/RAG modules | `src/assistant`, `src/output/intelligence_retrieval_items.py`, `src/assistant/semantic_retrieval.py` | reusable but curated-only |
| V1 compatibility modules | `src/output/weekly_intelligence_brief.py`, `src/output/knowledge_atlas_report.py`, split report paths | keep until PRM-20 has operator usage evidence and explicit archive/delete/move approval |
| IRX V2 modules | `src/output/weekly_intelligence_brief_v2.py`, `src/output/knowledge_atlas_report_v2.py`, `src/output/report_v2_rollout.py` | historical/reusable |
| legacy report generators | digest, recommendations, study plan, visual report modules | classify after operator production tests |
| generated private artifacts | `data/output/**` | ignored; do not commit new private outputs |
| public sanitized fixtures | `examples/public_scorecard_demo`, `tests/fixtures` | preserve |
| historical docs | `docs/intelligence_report_v2_*`, `docs/portfolio_*`, `docs/archive/**` | preserve as history |
| duplicate docs | `docs/ARCHITECTURE.md` vs `docs/architecture.md` | uppercase canonical, lowercase legacy |
| systemd units | `systemd/*` | stale status unverified |

## Cleanup Candidates

| Path | Current callers | Why it may be obsolete | Evidence needed | Earliest milestone | Verification |
| --- | --- | --- | --- | --- | --- |
| `docs/architecture.md` | compatibility redirect | content moved to archive; uppercase architecture is canonical | redirect retained for historical links | PRM-20 | doc link check |
| `docs/intelligence_report_v2_roadmap.md` | compatibility redirect | content moved to archive; active IRX queue closed | redirect retained for historical links | PRM-20 | doc link check |
| `src/output/weekly_intelligence_brief.py` | orchestrator/tests | V1 report surface | Brief V3 proven and compatibility adapter exists | PRM-20 | pytest affected report tests |
| `src/output/knowledge_atlas_report.py` | orchestrator/tests | V1 Atlas audit surface | Knowledge Library and Audit Explorer split proven | PRM-20 | pytest affected atlas tests |
| `src/assistant/semantic_retrieval.py` | PI facade/tests | curated-only transient search may be superseded | archive search and curated search merged behind new facade | PRM-13 | assistant tool tests |
| `systemd/telegram-ai-split-report.*` | deployment docs | report-centered timer | new workflow runbook and operator usage evidence | PRM-17 | systemd dry-run/doc check |

## PRM-UX-13 Simplification Handoff

| Candidate | Current callers | Operator production-test evidence | Migration risk | Decision | Verification |
| --- | --- | --- | --- | --- | --- |
| Legacy report commands and modules | existing CLI/runtime/tests | not collected yet | compatibility callers may remain | leave untouched | focused affected tests before any later proposal |
| Legacy service and timer templates | compatibility archive | operator-approved archive on 2026-08-13 | accidental restart or scheduled report delivery | archived with README | static path check; no service action |
| Duplicate/lowercase documentation | historical links | not collected yet | stale external or internal references | label as compatibility history only | `rg` references before any later proposal |

No delete, move, archive, or rename is authorized by this table. A future
PRM-20 change must replace `not collected yet` with operator production-test
evidence and obtain explicit human compatibility approval for each candidate.

Exception recorded 2026-08-12: the operator approved moving the four
report-era documents listed in `docs/legacy_surfaces.md` into
`docs/archive/legacy_report_era/` while retaining redirect stubs. No other
candidate is approved by that decision.

Exception recorded 2026-08-13: the operator approved moving the two legacy
weekly split-report repo systemd templates into
`systemd/archive/legacy_report_era/`. This did not modify installed host units
or authorize any service start, stop, enable, disable, or removal.

Exception recorded 2026-08-13: the operator approved moving the Hermes PI,
Portfolio Grade Intelligence, Report Quality, and Weekly Radar roadmaps into
`docs/archive/legacy_report_era/` with redirect stubs at their former paths.
This decision does not authorize moving other roadmap or compatibility files.

Exception recorded 2026-08-13: the operator approved moving the Project Plan,
Next Development Roadmap, and Development Cycle into
`docs/archive/legacy_report_era/` with redirect stubs. This decision does not
authorize moving active product contracts.

Exception recorded 2026-08-13: the operator approved the global archive of
remaining legacy repo systemd templates. All templates except
`telegram-prm-assistant` and bounded PRM archive refresh now live in
`systemd/archive/legacy_report_era/`. Installed host units were not modified.

## Rules

- Do not start a broad refactor before PRM-4.
- Do not delete history to make the repo look cleaner.
- Split oversized modules only when usage evidence shows maintenance pain.
- Generated private outputs remain ignored.
- Final user path must become visible within five minutes after PRM-20.
- PRM-20 is blocked until real operator production-test evidence exists.
- Deletion, archive, or move of compatibility files requires explicit human
  approval even if a cleanup row lists the path as a candidate.
- `docs/legacy_runtime_inventory.md` names code that remains active through
  callers or tests and cannot be archived as documentation-only cleanup.
