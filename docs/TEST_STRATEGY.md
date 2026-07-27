# Test Strategy

Status: active
Last updated: 2026-07-27

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

Recorded on 2026-07-27.

```text
python3 tools/test_tiers.py focused-prm
59 passed, 6 subtests passed in 2.09s
```

```text
python3 tools/test_tiers.py fast-contract
112 passed, 6 subtests passed in 47.21s
```

```text
python3 tools/test_tiers.py ops-date-sensitive
1 failed, 3 passed in 3.86s
FAILED tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
```

The `ops-date-sensitive` failure is the known live-evidence-window fixture
failure. It is intentionally isolated from `focused-prm` and `fast-contract`;
do not hide it by deleting the test or weakening the assertion.

## Policy

- Use `focused-prm` before committing narrow PRM RAG/assistant changes.
- Use `fast-contract` before committing shared contract, router, telemetry, or
  privacy-boundary changes.
- Use `ops-date-sensitive` when changing product ops validation or when a block
  review needs an explicit known-failure receipt.
- Use `full` or `block-review` before closing a deep-review block, with known
  failures recorded exactly.
- Do not run live Telegram ingestion, live LLM extraction, report generation,
  embeddings, external web research jobs, or production database migrations as
  a substitute for these test tiers.
