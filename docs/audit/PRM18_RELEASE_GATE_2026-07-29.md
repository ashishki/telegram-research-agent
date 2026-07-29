# PRM-18 Release Gate - 2026-07-29

Status: implementation evidence
Scope: PRM-18 End-To-End Evaluation And Security Review

## Gate

PRM-18 implements a deterministic release/dogfood gate. The current receipt is
blocked and does not start dogfood or claim release readiness.

PRM-19 remains blocked until the human operator explicitly approves dogfood
start and accepts or clears the PRM-18 blockers. PRM-20 remains blocked until
real PRM-19 dogfood evidence exists and the human operator explicitly approves
any compatibility-file archive, deletion, or move.

## Scope

- Added `evals/prm_release_gate.py`.
- Added sanitized PRM-18 receipt
  `evals/prm18_release_gate_receipt_2026-07-29.json`.
- Added `tests/test_prm_release_gate.py`.
- Added the PRM-18 test to `focused-prm` and `fast-contract` tiers.
- Updated final acceptance, privacy, dogfood, repo hygiene, task graph,
  evidence index, test strategy, audit index, and handoff docs.

## Release Gate Receipt

Current receipt summary:

- schema: `prm_release_gate.v1`;
- dogfood gate: `blocked`;
- dogfood started: `false`;
- release claimed: `false`;
- acceptance scenarios: 0 passed, 0 failed, 11 blocked;
- blocked evaluation areas: data, retrieval, generation, UI, and end-to-end;
- passed deterministic contract areas: tool, agent, privacy, and cost;
- active stop-ship blockers: unsupported claims and retrieval metric failure;
- human dogfood-start approval: missing.

The receipt is an evidence classifier. It does not run live Telegram ingestion,
reaction sync, LLM extraction, LLM judges, browser automation, Frontier, Radar,
report generation, full archive indexing, embeddings, external verification, or
external web research.

## Changed Files

- `.playbook-artifacts/project_verification.json`
- `.playbook-artifacts/project_verification/project_tests/stdout.txt`
- `AGENTS.md`
- `docs/CODEX_PROMPT.md`
- `docs/EVIDENCE_INDEX.md`
- `docs/PRIVACY_THREAT_MODEL.md`
- `docs/TEST_STRATEGY.md`
- `docs/audit/AUDIT_INDEX.md`
- `docs/audit/PRM18_RELEASE_GATE_2026-07-29.md`
- `docs/dogfood_4_week_plan.md`
- `docs/final_acceptance_plan.md`
- `docs/repo_hygiene_and_archive_plan.md`
- `docs/tasks.md`
- `evals/prm18_release_gate_receipt_2026-07-29.json`
- `evals/prm_release_gate.py`
- `tests/test_prm_release_gate.py`
- `tools/test_tiers.py`

## Verification

```text
PYTHONPATH=src python3 -m pytest tests/test_prm_release_gate.py -q
5 passed in 0.08s
```

```text
python3 tools/test_tiers.py focused-prm
99 passed, 6 subtests passed in 23.17s
```

```text
python3 tools/test_tiers.py fast-contract
152 passed, 6 subtests passed in 43.24s
```

Full verifier:

```text
python3 tools/verify_project.py --root .
project_commit=8201636c204846c3e82fda3a213a2d1b3560c727
PASS: playbook_contract exit=0
FAIL: project_tests exit=1
required_failures=1
FAILED tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
1 failed, 1049 passed, 287 subtests passed in 412.02s (0:06:52)
```

Known failure detail:

```text
E       AssertionError: Lists differ: ['needs_live_event', 'needs_live_event'] != ['passed', 'passed']
```

The known failure is the date-sensitive product-ops live-evidence fixture. This
PRM-18 change set does not alter product ops validation.

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
- Tests used synthetic fixture strings and sanitized metadata only.
- No raw Telegram text, provider payload, prompt, completion, generated private
  report, or production DB contents were committed.
- PRM-8 vector/hybrid retrieval remains blocked.
- PRM-19 is blocked by missing human dogfood-start approval and current PRM-18
  blockers.
- PRM-20 is blocked by missing PRM-19 dogfood evidence and compatibility-file
  archive/delete/move approval.
