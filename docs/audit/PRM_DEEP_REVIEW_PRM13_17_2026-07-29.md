# PRM-13 Through PRM-17 Deep Review - 2026-07-29

Status: active deep-review evidence
Scope: PRM-13 Knowledge Library, PRM-14 project context, PRM-15 learning-state
correction, PRM-16 Weekly Brief V3, and PRM-17 autonomous workflow telemetry
Authority: `docs/REVIEW_POLICY.md`, `docs/tasks.md`,
`docs/PRIVACY_THREAT_MODEL.md`, `docs/TEST_STRATEGY.md`

## Gate

This is the batched deep-review gate required before PRM-18. PRM-18 was not
started during this review.

Review was performed locally in the main Codex session. Subagents were not
spawned: the current tool policy does not treat a request for deep review alone
as permission to delegate to child agents, and `docs/REVIEW_POLICY.md` makes
child agents optional.

## Reviewed Material

- Accumulated diff from `d48b582` through `d348d5b`.
- PRM receipts:
  - `docs/audit/PRM13_KNOWLEDGE_LIBRARY_2026-07-27.md`
  - `docs/audit/PRM14_PROJECT_CONTEXT_2026-07-28.md`
  - `docs/audit/PRM15_LEARNING_STATE_2026-07-29.md`
  - `docs/audit/PRM16_WEEKLY_BRIEF_V3_2026-07-29.md`
  - `docs/audit/PRM17_RUNTIME_WORKFLOWS_2026-07-29.md`
- New implementation modules:
  - `src/output/knowledge_library.py`
  - `src/assistant/project_context.py`
  - `src/output/learning_layer.py`
  - `src/output/weekly_brief_v3.py`
  - `src/processing/workflow_telemetry.py`
- Focused tests for Knowledge Library, project context, learning state, Weekly
  Brief V3, assistant routing, and workflow telemetry.
- Handoff/status docs and privacy/cost/rollback contracts.

## Findings And Disposition

| Area | Finding | Severity | Disposition |
| --- | --- | --- | --- |
| Workflow telemetry | `validate_workflow_telemetry_receipt` validated metric numeric types but accepted malformed budget values when `approval_required=false`; malformed cost/model-call receipts could pass the PRM-17 telemetry contract. | High | Fixed in `d348d5b`: budget cost fields must be non-negative numbers and model-call fields must be non-negative integers. Regression added in `tests/test_workflow_telemetry.py`. |
| Evidence process | The earlier PRM-17 full verifier receipt was produced on `1f9a639` and then followed by docs commit `9c1f364`. | Medium | Re-ran the full verifier after the corrective commit on `d348d5b` and recorded that exact result in this review. |
| Product boundary | PRM-13/16 static renderers and PRM-17 workflow contracts are fixture/static evidence only; there is no Playwright browser snapshot, dogfood evidence, live workflow activation, or release readiness. | Medium | Recorded as residual risk and boundary evidence. PRM-18 remains the release/eval/security gate. |

## Repair Evidence

Changed by the deep-review repair:

- `src/processing/workflow_telemetry.py`
- `tests/test_workflow_telemetry.py`

The budget validator now rejects malformed budget receipts:

```text
budget.weekly_cost_usd must be a non-negative number
```

Relevant code locations after repair:

- `src/processing/workflow_telemetry.py` budget validation around lines 390-406.
- `tests/test_workflow_telemetry.py` malformed-budget regression around lines
  138-145.

## Verification

```text
PYTHONPATH=src python3 -m pytest tests/test_workflow_telemetry.py -q
4 passed in 0.07s
```

```text
python3 tools/test_tiers.py focused-prm
94 passed, 6 subtests passed in 16.84s
```

```text
python3 tools/test_tiers.py fast-contract
147 passed, 6 subtests passed in 38.99s
```

Full gate after repair:

```text
python3 tools/verify_project.py --root .
project_commit=d348d5bab7da131451e79a7df383d9f072d90b80
PASS: playbook_contract exit=0
FAIL: project_tests exit=1
required_failures=1
FAILED tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
1 failed, 1044 passed, 287 subtests passed in 361.04s (0:06:01)
```

Known failure detail:

```text
E       AssertionError: Lists differ: ['needs_live_event', 'needs_live_event'] != ['passed', 'passed']
```

The known failure is the date-sensitive product-ops live-evidence fixture. It
remains isolated from `focused-prm` and `fast-contract`.

Final pre-push checks:

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
<no output>
```

## Residual Risk

- Playwright/browser screenshots were not produced for Knowledge Library or
  Brief V3; fixture visual evidence is static contract checks plus WeasyPrint
  smoke where available.
- No dogfood, release readiness, external verification execution, vector
  adoption, or scheduled workflow activation is claimed.
- Full pytest still has the known product-ops date-sensitive fixture failure.
- PRM-8 vector/hybrid retrieval remains blocked.

## Boundary Evidence

- No live Telegram ingestion, reaction sync, LLM extraction, Frontier, Radar,
  report generation, full archive indexing, embeddings, external web research,
  external skill execution, production database migration, dogfood start,
  release claim, or compatibility-file archive/delete/move was performed.
- No production database contents were modified.
- Tests used synthetic fixture strings and temporary rendering/database fixtures
  only.
- No raw Telegram text was written to docs or fixtures.
- Candidate retrieval rows remain candidates, not gold labels.
- PRM-18 is next only if the human operator chooses to proceed beyond this
  recorded deep-review gate.
