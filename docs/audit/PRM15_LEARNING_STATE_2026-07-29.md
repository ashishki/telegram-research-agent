# PRM-15 Learning-State Correction And Migration - 2026-07-29

Status: implementation evidence
Scope: PRM-15 Learning-State Correction And Migration

## Gate

PRM-15 continued within the open PRM-13 through PRM-17 implementation block.
The next batched deep-review gate remains the PRM-13 through PRM-17 block review
before PRM-18. Immediate review is still required earlier for privacy egress,
unsafe writes, production migrations, vector backend adoption, external skill
approval, dogfood start, release claims, or compatibility-file
archive/delete/move.

## Scope

- Replaced the old learning-stage vocabulary with PRM-15 states:
  `indexed`, `surfaced`, `opened`, `read`, `understood`, `explained`, `tried`,
  `applied`, `measured`, `rejected`, and `stale`.
- Added fixture-only `migrate_legacy_learning_records` support that preserves
  legacy rows and stores the prior state in `legacy_learning_state`.
- Legacy source URL or atom presence now maps only to `indexed` or `surfaced`.
- `opened`, `read`, `understood`, `explained`, `tried`, `applied`, and
  `measured` require explicit feedback, progress receipts, outcome evidence, or
  measured/test evidence.
- Source-backed atoms shown in projections are `surfaced`, not inferred `read`.
- No-feedback display remains `unknown`.
- No production database migration was executed.

## Changed Files

- `src/output/learning_layer.py`
- `tests/test_learning_layer.py`
- `tests/test_ai_report_contract.py`
- `tests/test_split_intelligence_reports.py`
- `tools/test_tiers.py`
- `AGENTS.md`
- `docs/CODEX_PROMPT.md`
- `docs/TEST_STRATEGY.md`
- `docs/tasks.md`
- `docs/personal_research_memory_product_contract.md`
- `docs/ROLLBACK_AND_REINDEX_PLAN.md`
- `docs/audit/AUDIT_INDEX.md`
- `docs/audit/PRM15_LEARNING_STATE_2026-07-29.md`

## Verification

```text
PYTHONPATH=src python3 -m pytest tests/test_learning_layer.py tests/test_ai_report_contract.py tests/test_intelligence_retrieval_items.py tests/test_split_intelligence_reports.py tests/test_dogfood_review.py -q
85 passed, 7 subtests passed in 23.65s
```

```text
python3 tools/test_tiers.py focused-prm
84 passed, 6 subtests passed in 16.34s
```

```text
python3 tools/test_tiers.py fast-contract
137 passed, 6 subtests passed in 53.59s
```

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
- Tests used synthetic fixture strings and temporary outputs only.
- No raw Telegram text was written to docs or fixtures.
- No learning progress state above `surfaced` is produced from source URL or
  atom presence alone.
- Candidate retrieval rows remain candidates, not gold labels.
- PRM-8 vector/hybrid retrieval remains blocked.
- PRM-16 is next only if the human operator chooses to proceed within the
  PRM-13 through PRM-17 block.
