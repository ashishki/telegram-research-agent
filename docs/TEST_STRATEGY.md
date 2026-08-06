# Test Strategy

Status: active
Last updated: 2026-07-29

## Purpose

The repository test suite is intentionally broad because the system reads a
private Telegram archive, routes bounded LLM calls, generates private artifacts,
and may later propose durable memory writes. Daily development should not depend
on running every integration and ops check after every small edit.

Use explicit tiers instead of ad hoc pytest subsets.

## Tiers

Commands are implemented by `tools/test_tiers.py`.

| Tier | Purpose | Command |
| --- | --- | --- |
| `focused-prm` | Current PRM RAG/assistant/code-review repair loop. | `python3 tools/test_tiers.py focused-prm` |
| `fast-contract` | Fast deterministic contract/unit subset, excluding date-sensitive ops. | `python3 tools/test_tiers.py fast-contract` |
| `ops-date-sensitive` | Isolated product ops date-window checks. | `python3 tools/test_tiers.py ops-date-sensitive` |
| `full` | Complete pytest suite. | `python3 tools/test_tiers.py full` |
| `block-review` | Playbook validator, full suite, and whitespace diff check for review gates. | `python3 tools/test_tiers.py block-review` |

Print exact commands without running them:

```bash
python3 tools/test_tiers.py focused-prm --print-only
python3 tools/test_tiers.py block-review --print-only
```

## Current Results

Recorded on 2026-07-29.

```text
PYTHONPATH=src python3 -m pytest tests/test_learning_layer.py tests/test_ai_report_contract.py tests/test_intelligence_retrieval_items.py tests/test_split_intelligence_reports.py tests/test_dogfood_review.py -q
85 passed, 7 subtests passed in 23.65s
```

PRM-16 targeted DTO/visual smoke:

```text
PYTHONPATH=src python3 -m pytest tests/test_weekly_brief_v3.py -q
6 passed in 2.77s
```

PRM-17 targeted workflow telemetry/privacy fixture:

```text
PYTHONPATH=src python3 -m pytest tests/test_workflow_telemetry.py -q
4 passed in 0.07s
```

PRM-18 targeted release/dogfood gate:

```text
PYTHONPATH=src python3 -m pytest tests/test_prm_release_gate.py -q
5 passed in 0.08s
```

Safe PRM assistant runtime boundary:

```text
PYTHONPATH=src python3 -m pytest tests/test_cli.py tests/test_handlers.py tests/test_callbacks.py -q
52 passed, 3 subtests passed in 18.79s
```

Local PRM memory ask:

```text
PYTHONPATH=src python3 -m pytest tests/test_local_memory_ask.py tests/test_cli.py -q
13 passed, 3 subtests passed in 4.95s
```

```text
PYTHONPATH=src python3 -m pytest tests/test_project_context.py tests/test_pi_tools.py tests/test_pi_chat.py -q
47 passed, 6 subtests passed in 5.59s
```

```text
python3 tools/test_tiers.py focused-prm
102 passed, 6 subtests passed in 14.58s
```

```text
python3 tools/test_tiers.py fast-contract
209 passed, 9 subtests passed in 52.30s
```

PRM-13 targeted visual/layout smoke:

```text
PYTHONPATH=src python3 -m pytest tests/test_knowledge_library.py tests/test_test_tiers.py -q
8 passed in 7.15s
```

The full verifier receipt below is the historical PRM-18 release-gate readiness
run.

```text
python3 tools/verify_project.py --root .
PASS: playbook_contract exit=0
FAIL: project_tests exit=1
FAILED tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
1 failed, 1049 passed, 287 subtests passed in 412.02s (0:06:52)
```

```text
python3 tools/test_tiers.py ops-date-sensitive
1 failed, 3 passed in 3.86s
FAILED tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
```

The former `ops-date-sensitive` failure was live-evidence-window fixture drift.
As of PRM-22 local verification on 2026-08-03, product ops and source-trust
fixture timestamps are relative and the current verifier is green:

```text
python3 tools/verify_project.py --root .
PASS: playbook_contract exit=0
PASS: project_tests exit=0
1083 passed, 291 subtests passed in 465.66s (0:07:45)
```

```text
python3 tools/test_tiers.py ops-date-sensitive
4 passed in 5.05s
```

Do not hide future date-sensitive failures by deleting tests or weakening
assertions; fix fixtures to express their intended freshness window.

## Policy

- Use `focused-prm` before committing narrow PRM RAG/assistant changes.
- Use `fast-contract` before committing shared contract, router, telemetry, or
  privacy-boundary changes. It includes the Telegram bot handler/callback
  boundary tests for safe PRM runtime mode.
- Use `ops-date-sensitive` when changing product ops validation or when a block
  review needs an explicit known-failure receipt.
- Use `full` or `block-review` before closing a deep-review block, with known
  failures recorded exactly.
- Do not run live Telegram ingestion, live LLM extraction, report generation,
  embeddings, external web research jobs, or production database migrations as
  a substitute for these test tiers.
