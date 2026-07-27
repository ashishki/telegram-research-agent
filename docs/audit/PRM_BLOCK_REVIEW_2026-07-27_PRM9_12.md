# PRM-9 Through PRM-12 Block Review - 2026-07-27

Status: active block-review receipt after corrective deep-review repair
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
- `978a81c feat(assistant): add confirmed memory saves`;
- the corrective repair recorded in
  `docs/audit/PRM_DEEP_REVIEW_PRM9_12_2026-07-27.md`.

This review does not claim dogfood start, release readiness, vector backend
adoption, gold-query approval, external-source execution, approved external
verification evidence, or production database migration.

## Review Result

Result: pass after corrective repair, with known non-blocking verifier failure.

Findings:

- The first block-review receipt was too shallow. Valid meta/process,
  architecture/privacy, and code/tests reviewers returned
  `PACKET_REVIEW_RESULT: ISSUES_FOUND`; dispositions are recorded in
  `PRM_DEEP_REVIEW_PRM9_12_2026-07-27.md`.
- The assistant catalog separates read-only tools, proposal tools, and the one
  confirmation-gated write tool through an explicit allowlist.
- External verification remains local-only; external skills are not approved or
  executed.
- Confirmed memory writes require exact proposal plus confirmation token,
  pre-existing canonical `personal_memory_events` schema, idempotent replay
  handling, and target validation for edit/delete/rollback.
- Edit, delete, and rollback are audit events, not destructive updates.
- Chat save requests produce proposals only and do not persist transcript text.
- PI chat suppresses content-free `llm_usage` database writes during read-only
  planning/generation.
- Insufficient-evidence turns without grounding evidence use deterministic
  fallback rather than unsupported generated archive claims.

Residual risks and open boundaries:

- The full verifier still has the known date-sensitive product ops fixture
  failure listed below.
- PRM-8 vector/hybrid retrieval remains blocked.
- PRM-13 through PRM-20 remain planned, not implemented.
- The saved-memory event table is defined by canonical schema/migration
  surfaces. No production database migration was run.
- Candidate retrieval rows remain candidates, not gold labels.

## Verification

Focused PRM evidence after corrective deep-review repair:

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

Final pre-push checks for the corrective deep-review repair:

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
- The full verifier generated `.playbook-artifacts` for the repair worktree;
  the committed receipt records the exact known failure and the generated stdout
  was whitespace-sanitized for `git diff --check`.
- No raw Telegram text was written to docs or fixtures.
- Human operator remains final completion authority.
