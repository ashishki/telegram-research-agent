# PA Playbook Integration — Observed CI Findings

Initial published head: daa53b087830f872ce35ca4de672031dceaa9352.
Observed planning run: 35333763373; job: 105563779190 (Python 3.10.21).

## Actual successful checks

- GitHub checked out the independent upstream submodule at exactly the pinned commit.
- Lock/gitlink/HEAD/URL/cleanliness verification passed.
- Six isolated bridge tests passed in CI.
- The full PA registry passed upstream schemas and design validation: 19 unique
  slices, matching task IDs/dependencies, valid references and compact context limits.

## Actual expected blocker

The unmodified current upstream task validator returned 19
TASK_DESIGN_APPROVAL_REQUIRED errors and zero warnings: one per planned PA
slice. This confirms the high-risk design cannot authorize its own implementation.
It is NOT a schema/dependency failure and must not be fixed by fabricated approval.
The real project verifier retains this blocking check until human design approval.

## Planning CI correction

The planning-only workflow now asserts that exact negative outcome while the
design is draft/review_required and every task/slice is still planned. It rejects
any other error/warning, started task, missing ID or unexpected zero exit. Once
the design is actually approved it requires the normal validator to pass.
This helper is NOT used to bypass the real project/release verifier.

Two added negative-parser tests plus six bridge tests were run locally:
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_playbook_bridge.py tests/test_pa_approval_guard.py -q`
Result: 8 passed on Python 3.13.5. These do not replace the next actual CI run.
Planning checkout now retains a parent commit for the whitespace diff check.

The original product CI remains separate. Baseline application failure is
preserved for PA-00. No product correctness, actual model review, user usefulness,
account permission or release approval is inferred from a planning CI result.
