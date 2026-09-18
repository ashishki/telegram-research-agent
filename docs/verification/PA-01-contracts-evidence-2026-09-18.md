# PA-01 contracts and acceptance foundation — 2026-09-18

Status: locally verified PA-01 foundation. This evidence does not change the
preserved mechanical `review_required` feature-design state, record a formal
Playbook approval, claim human acceptance of PA-01, enable a capability, or
claim a provider, runtime, release, or live-action result.

## Authority and workflow observation

The active owner instruction explicitly says that the design is approved,
PA-00 is accepted, and PA-01 should begin from `f011d3b` on the published PA
branch. It also specifically requires that the historic STOP_SHIP-derived
`review_required` state not be hand-edited or represented as formal approval.
This implementation follows the direct scoped instruction while preserving that
distinction.

The normal pinned Feature Workflow was invoked rather than editing any
`.playbook-artifacts` file:

```text
python3 tools/feature_workflow.py --root . next --feature-id PA
# No ready slice. - fresh approved design is required

python3 tools/feature_workflow.py --root . plan --task PA-01
# status=needs_input, recommendation=designed_slices

python3 tools/feature_workflow.py --root . start --task PA-01 --feature-id PA --slice-id PA-01
# planning decision needs_input blocks workflow draft/start/check
```

Those expected mechanical outcomes remain a pending Playbook-recording gate;
they were not bypassed in metadata. No reviewer was launched, following the
owner's instruction to defer the next Deep Review to the PA-00..PA-02 boundary.

## Implemented, offline-only foundation

- Six separate Draft 2020-12 contracts define `CapabilityGrant`, `ToolResult`,
  `EvidenceItem`, `BriefDocument`, `ActionProposal`, and `ActionReceipt`.
- The public synthetic corpus validates every contract and covers PA-02 through
  PA-18 with useful, negative, adversarial, recovery, and final-human-gate
  scenarios across archive, web, mail, calendar, Canvas, GitHub, documents and
  user input.
- The PA-01 tests enforce schema closure, grant/action/unknown-outcome failure
  cases, provenance/result-version/idempotency linkage, coverage completeness,
  and absence of credential-shaped corpus fields/values.
- `fast-contract` now includes the PA-01 test, so this contract floor is not a
  one-off command.

No production database, account, credential, Telegram message, archive record,
provider call, service, timer, migration, or live delivery was accessed or
changed. The two pre-existing untracked local files were preserved.

## Commands and results

Environment: Python `3.10.12`; `PYTHONPATH=src` and
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` for pytest commands.

```text
python3 tools/playbook.py --check-pin
# Playbook pin verified; no model, hook or application runtime enabled.

python3 tools/check_personal_assistant_plan.py
# PA plan: 19 consistent slices; schemas, references, dependencies and context limits passed.
# Design state: review_required; no product, human-approval or runtime claim.

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_assistant_contracts.py
# 5 passed in 0.24s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py fast-contract
# 394 passed in 131.48s (0:02:11)

python3 tools/check_pa_approval_guard.py --help
# Expected approval guard verified for 19 planned tasks.
# PLANNING CHECK ONLY: formal programme progression remains blocked until real design approval; project verifier is unchanged.

git diff --check
# no output; passed
```

The prohibited full historical pytest suite was not run. The first direct PA-01
test run before the final schema refinement also passed (5 passed in 0.22s);
the commands above are the exact current-diff result.

## Remaining gates and next command

PA-01 still needs the applicable human acceptance/review evidence before any
status is represented as completed. The preserved formal approval recorder
still needs a valid resolution that does not overwrite historic review state.
The requested Deep Review remains accumulated at the PA-00..PA-02 boundary.
The next safe implementation command after this scoped publication is
`python3 tools/feature_workflow.py --root . plan --task PA-02`; PA-02 itself
remains synthetic/offline until its grant and security gates are satisfied.
