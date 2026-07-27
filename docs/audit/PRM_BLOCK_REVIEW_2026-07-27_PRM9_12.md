# PRM-9 Through PRM-12 Block Review - 2026-07-27

Status: active block-review receipt
Authority: `docs/REVIEW_POLICY.md`, `docs/tasks.md`,
`docs/PRIVACY_THREAT_MODEL.md`, `docs/tool_eval.md`,
`docs/generation_eval.md`

## Scope

This review closes the PRM-9 through PRM-12 implementation block:

- PRM-9: assistant intent router and bounded tool catalog;
- PRM-10: grounded answer generation contract and telemetry;
- PRM-11: on-demand external verification requirement path;
- PRM-12: confirmation-gated save/watch flow.

Implementation commits covered include the PRM-9/PRM-10 assistant slices and
corrective fixes already recorded in
`docs/audit/PRM_DEEP_REVIEW_CONSOLIDATED_2026-07-27.md`, plus:

- `f2a0e4c feat(assistant): add external verification gate`;
- `978a81c feat(assistant): add confirmed memory saves`.

This review does not claim dogfood start, release readiness, vector backend
adoption, gold-query approval, external-source execution, approved external
verification evidence, or production database migration.

## Review Result

Result: pass with known non-blocking verifier failure.

Findings:

- No new stop-ship finding was identified in the PRM-11 or PRM-12 continuation
  diff.
- The assistant catalog separates read-only tools, proposal tools, and the one
  confirmation-gated write tool.
- External verification remains local-only; external skills are not approved or
  executed.
- Confirmed memory writes require exact proposal plus confirmation token and
  append `personal_memory_events` rows.
- Edit, delete, and rollback are audit events, not destructive updates.
- Chat save requests produce proposals only and do not persist transcript text.

Residual risks and open boundaries:

- The full verifier still has the known date-sensitive product ops fixture
  failure listed below.
- PRM-8 vector/hybrid retrieval remains blocked.
- PRM-13 through PRM-20 remain planned, not implemented.
- The saved-memory event table is created only by an explicitly confirmed write
  path. No production database migration was run.
- Candidate retrieval rows remain candidates, not gold labels.

## Verification

Focused PRM evidence from the PRM-12 implementation receipt:

```text
PYTHONPATH=src python3 -m pytest tests/test_pi_tools.py tests/test_pi_chat.py -q
33 passed, 6 subtests passed in 2.19s
```

```text
python3 tools/test_tiers.py focused-prm
59 passed, 6 subtests passed in 2.09s
```

```text
python3 tools/test_tiers.py fast-contract
112 passed, 6 subtests passed in 47.21s
```

Full gate:

```text
python3 tools/verify_project.py --root .
PASS: playbook_contract exit=0
FAIL: project_tests exit=1
verify_project: required_failures=1 result=/srv/openclaw-you/workspace/telegram-research-agent/.playbook-artifacts/project_verification.json
```

Project test summary:

```text
FAILED tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
1 failed, 1012 passed, 287 subtests passed in 414.22s (0:06:54)
```

Known failure details:

```text
AssertionError: Lists differ: ['needs_live_event', 'needs_live_event'] != ['passed', 'passed']
```

Final pre-push checks for the PRM-12 implementation commit:

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
- PRM-12 fixture writes used temporary SQLite databases only.
- No raw Telegram text was written to docs or fixtures.
- Human operator remains final completion authority.
