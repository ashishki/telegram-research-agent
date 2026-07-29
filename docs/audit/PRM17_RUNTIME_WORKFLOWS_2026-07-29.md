# PRM-17 Runtime, Autonomous Workflows, Observability, Cost, And Rollback - 2026-07-29

Status: implementation evidence
Scope: PRM-17 Runtime, Autonomous Workflows, Observability, Cost, And Rollback

## Gate

PRM-17 closes the implementation portion of the open PRM-13 through PRM-17
block. Do not start PRM-18 until the PRM-13 through PRM-17 batched deep review
is recorded, unless the human operator explicitly changes the plan. Immediate
review is still required earlier for privacy egress, unsafe writes, production
migrations, vector backend adoption, external skill approval, dogfood start,
release claims, or compatibility-file archive/delete/move.

## Scope

- Added `src/processing/workflow_telemetry.py`.
- Added a deterministic autonomous workflow registry for ingestion, archive
  indexing, reaction fast lane, selective enrichment, Weekly Brief V3,
  Knowledge Library projection, backup snapshot, and rollback/reindex dry-run.
- Each workflow contract lists trigger, inputs, outputs, idempotency key, retry
  policy, fallback, receipt, and rollback.
- Added aggregate telemetry receipt schema `workflow_telemetry_receipt.v1`.
- Telemetry records index freshness, queue age, retrieval latency, generation
  latency, model cost, model calls, tool calls, no-answer count/rate, error
  class, and budget approval requirement.
- Telemetry excludes raw post text, provider payloads, prompts, completions, and
  raw Telegram corpus egress. Raw fields supplied to fixtures are represented
  only by redacted field names.
- Updated autonomous workflow, cost, rollback/reindex, and privacy docs.
- No scheduled runtime job was activated.

## Changed Files

- `src/processing/workflow_telemetry.py`
- `tests/test_workflow_telemetry.py`
- `tools/test_tiers.py`
- `AGENTS.md`
- `docs/CODEX_PROMPT.md`
- `docs/AUTONOMOUS_WORKFLOW_CONTRACT.md`
- `docs/COST_BUDGET.md`
- `docs/ROLLBACK_AND_REINDEX_PLAN.md`
- `docs/PRIVACY_THREAT_MODEL.md`
- `docs/TEST_STRATEGY.md`
- `docs/tasks.md`
- `docs/final_acceptance_plan.md`
- `docs/audit/AUDIT_INDEX.md`
- `docs/audit/PRM17_RUNTIME_WORKFLOWS_2026-07-29.md`

## Verification

```text
PYTHONPATH=src python3 -m pytest tests/test_workflow_telemetry.py -q
4 passed in 0.08s
```

```text
python3 tools/test_tiers.py focused-prm
94 passed, 6 subtests passed in 18.26s
```

```text
python3 tools/test_tiers.py fast-contract
147 passed, 6 subtests passed in 42.58s
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
- Tests used synthetic fixture strings only.
- No raw Telegram text was written to docs or fixtures.
- PRM-8 vector/hybrid retrieval remains blocked.
- PRM-18 must not start until the PRM-13 through PRM-17 deep-review gate is
  recorded.
