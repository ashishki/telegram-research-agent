# PRM-9 Through PRM-12 Deep Review - 2026-07-27

Status: active corrective deep-review evidence
Scope: PRM-9 assistant router, PRM-10 grounded answers, PRM-11 external
verification requirement path, PRM-12 confirmation-gated memory writes
Authority: `docs/REVIEW_POLICY.md`, `docs/tasks.md`,
`docs/PRIVACY_THREAT_MODEL.md`, `docs/AGENT_HARNESS_DESIGN.md`

## Gate

This is the deep-review gate required before PRM-13. PRM-13 remains planned and
was not started during this repair.

The first nested read-only reviewer attempt could not see `/srv/...` and then
found stale `/tmp` clones, so that output was discarded. A fresh temporary clone
was created from current local HEAD before valid reviewer runs:

```text
/tmp/prm9-12-review-current.NOGwcr/repo
d48b582e31c86ceb1c0235f2089bfd6fcf558c35
```

Valid reviewer outputs:

- `/tmp/prm9_12_meta_review.md`
- `/tmp/prm9_12_arch_review.md`
- `/tmp/prm9_12_code_review.md`

All valid reviewer outputs returned `PACKET_REVIEW_RESULT: ISSUES_FOUND`.

## Findings And Disposition

| Reviewer | Finding | Disposition |
| --- | --- | --- |
| Meta/process | P1: final verifier evidence in the block receipt conflicted with the committed verifier artifact. | Block receipt now records exact current verifier output and notes the artifact generation boundary. |
| Meta/process | P2: `docs/tasks.md` baseline and PRM statuses were stale for PRM-9 through PRM-12. | Baseline now describes bounded SQLite FTS assistant retrieval; PRM-1 through PRM-7 and PRM-9 through PRM-12 are `implemented`; PRM-8 is `blocked`; PRM-13 remains `planned`. |
| Meta/process | P3: harness docs omitted `propose_decision`. | `docs/AGENT_HARNESS_DESIGN.md` now includes `propose_decision` and the confirmed write tool. |
| Architecture/privacy | High: PI chat LLM calls could append content-free `llm_usage` rows outside confirmed save flows. | PI chat wraps planning/generation LLM calls with `suppress_usage_recording`; telemetry records `llm_usage_db_write_performed=false`; regression test added. |
| Architecture/privacy | Medium: `personal_memory_events` was lazily created by the confirmed write handler. | `personal_memory_events` is now in canonical schema and migration verification; confirmed writes require existing schema and return `schema_missing` without creating a DB. |
| Architecture/privacy | Low: architecture/harness catalog docs were stale. | Architecture and harness docs now list implemented catalog and trace labels. |
| Code/tests | High: PI tool blocking was denylist-based and custom catalogs were not validated before execution. | Catalog validation is now explicit allowlist-based and `call_pi_tool` validates supplied catalogs before lookup/execution. |
| Code/tests | High: confirmed memory writes were replayable and did not validate edit/delete/rollback targets. | Replayed proposal/token returns `already_confirmed` without appending; edit/delete/rollback targets are validated before writes. |
| Code/tests | High: insufficient-evidence generation could return unsupported LLM archive claims. | `answer_pi_chat` replaces insufficient-evidence/no-grounding model text with deterministic fallback. |
| Code/tests | Medium: proposal/write trace semantics were stale. | `needs_confirmation`, `confirmed_write`, `proposal_only_no_write`, and `confirmation_gated_write*` traces are now covered. |

## Changed Files

- `.playbook-artifacts/project_verification.json`
- `.playbook-artifacts/project_verification/project_tests/stdout.txt`
- `AGENTS.md`
- `src/assistant/pi_chat.py`
- `src/assistant/pi_memory.py`
- `src/assistant/pi_tools.py`
- `src/db/migrate.py`
- `src/db/schema.sql`
- `src/llm/client.py`
- `tests/test_pi_chat.py`
- `tests/test_pi_tools.py`
- `docs/AGENT_HARNESS_DESIGN.md`
- `docs/ARCHITECTURE.md`
- `docs/CODEX_PROMPT.md`
- `docs/COST_BUDGET.md`
- `docs/PRIVACY_THREAT_MODEL.md`
- `docs/TEST_STRATEGY.md`
- `docs/generation_eval.md`
- `docs/tasks.md`
- `docs/tool_eval.md`
- `docs/audit/AUDIT_INDEX.md`
- `docs/audit/PRM_BLOCK_REVIEW_2026-07-27_PRM9_12.md`
- `docs/audit/PRM_DEEP_REVIEW_CONSOLIDATED_2026-07-27.md`
- `docs/audit/PRM_DEEP_REVIEW_PRM9_12_2026-07-27.md`

## Verification

```text
PYTHONPATH=src python3 -m pytest tests/test_pi_tools.py tests/test_pi_chat.py -q
39 passed, 6 subtests passed in 14.25s
```

```text
python3 tools/test_tiers.py focused-prm
65 passed, 6 subtests passed in 12.74s
```

```text
python3 tools/test_tiers.py fast-contract
118 passed, 6 subtests passed in 58.27s
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
1 failed, 1018 passed, 287 subtests passed in 310.27s (0:05:10)
```

Known failure details:

```text
AssertionError: Lists differ: ['needs_live_event', 'needs_live_event'] != ['passed', 'passed']
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

## Boundary Evidence

- No live Telegram ingestion, reaction sync, LLM extraction, Frontier, Radar,
  report generation, full archive indexing, embeddings, external web research,
  external skill execution, production database migration, dogfood start,
  release claim, or compatibility-file archive/delete/move was performed.
- No production database contents were modified.
- Tests and confirmed-save fixtures used temporary SQLite databases only.
- No raw Telegram text was written to docs or fixtures.
- Candidate retrieval rows remain candidates, not gold labels.
- PRM-8 vector/hybrid retrieval remains blocked.
- PRM-13 is next only if the human operator chooses to proceed beyond this
  recorded deep-review gate.
