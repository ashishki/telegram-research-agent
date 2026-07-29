# PRM-16 Weekly Brief V3 And Legacy Surface Demotion - 2026-07-29

Status: implementation evidence
Scope: PRM-16 Weekly Brief V3 And Legacy Surface Demotion

## Gate

PRM-16 continued within the open PRM-13 through PRM-17 implementation block.
The next batched deep-review gate remains the PRM-13 through PRM-17 block review
before PRM-18. Immediate review is still required earlier for privacy egress,
unsafe writes, production migrations, vector backend adoption, external skill
approval, dogfood start, release claims, or compatibility-file
archive/delete/move.

## Scope

- Added `src/output/weekly_brief_v3.py` as a deterministic bounded projection.
- The DTO derives one main change, one `ACT` item, one `STUDY` item, one
  `WATCH` or `IGNORE` item, reaction summary, concrete project connection or
  honest zero, optional Radar card, and feedback request from supplied context.
- Added legacy-surface demotion metadata for `weekly_brief_v1` and
  `knowledge_atlas`.
- Added deterministic text validation that rejects generic fallback action
  phrasing.
- Radar failure is localized to the Radar card and `dependency_status.radar`;
  non-Radar sections and archive/assistant/Knowledge Library dependencies stay
  independently valid when their supplied evidence is valid.
- Added a static self-contained HTML renderer and visual contract receipt.
- No live report generation, Radar run, provider call, archive processing, or
  production database write was executed.

## Changed Files

- `src/output/weekly_brief_v3.py`
- `tests/test_weekly_brief_v3.py`
- `tools/test_tiers.py`
- `AGENTS.md`
- `docs/CODEX_PROMPT.md`
- `docs/TEST_STRATEGY.md`
- `docs/tasks.md`
- `docs/report_format.md`
- `docs/personal_research_memory_product_contract.md`
- `docs/final_acceptance_plan.md`
- `docs/audit/AUDIT_INDEX.md`
- `docs/audit/PRM16_WEEKLY_BRIEF_V3_2026-07-29.md`

## Verification

```text
PYTHONPATH=src python3 -m pytest tests/test_weekly_brief_v3.py -q
6 passed in 2.77s
```

```text
python3 tools/test_tiers.py focused-prm
90 passed, 6 subtests passed in 15.46s
```

```text
python3 tools/test_tiers.py fast-contract
143 passed, 6 subtests passed in 46.50s
```

Visual verification command for the changed renderer:

```text
PYTHONPATH=src python3 -m pytest tests/test_weekly_brief_v3.py -q
```

The targeted test includes static HTML contract checks plus WeasyPrint layout
smoke for `desktop_1440` (`1440x1000`) and `mobile_375` (`375x1000`) when
WeasyPrint is available. The deterministic receipt records
`browser_snapshot_status=not_run_playwright_unavailable`.

Final pre-push checks:

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
<no output>
```

## Boundary Evidence

- No live Telegram ingestion, reaction sync, LLM extraction, Frontier, Radar,
  report generation, full archive indexing, embeddings, external web research,
  external skill execution, production database migration, dogfood start,
  release claim, or compatibility-file archive/delete/move was performed.
- No production database contents were modified.
- Tests used synthetic fixture strings and temporary WeasyPrint rendering only.
- No raw Telegram text was written to docs or fixtures.
- Weekly Brief V3 remains a secondary projection, not a knowledge source.
- V1 Brief and Atlas were demoted by product metadata/docs only; no
  compatibility files were deleted, archived, or moved.
- PRM-8 vector/hybrid retrieval remains blocked.
- PRM-17 is next only if the human operator chooses to proceed within the
  PRM-13 through PRM-17 block.
