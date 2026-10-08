# Review #40 — cancellation allegation contradicted by source/counterexamples

Reviewed 43e174b, receipt PAI-review-continuation-40.json. Reviewer downgrades
the conservative no-child aggregate to a P2 availability tradeoff, preserving
its fence. It repeats a P1 that warning text depends on pre-read state, although
the supplied source explicitly uses `current['attempts']>0` for both warning
and callback. The allegation remains open for another independent resolution.

The existing real status-read/claim case already passed. A second exact race
now claims strictly inside the cancel wrapper, immediately before the real
cancel UPDATE; the caller's original snapshot is queued, actual attempts is 1,
and the exact external-call warning is present. Neither test mocks publication
or bypasses the real PostgreSQL state transition.

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_ingress_jobs.py::test_cancel_warning_uses_actual_attempts_if_worker_claims_after_status_read tests/test_pai_ingress_jobs.py::test_cancel_warning_when_claim_occurs_strictly_before_cancel_update
```

Observed: 2 passed in 6.04 s, zero skips/failures. No runtime behavior change
was needed for this source mismatch. The prior 36-case observation remains.

Operator recovery for a prepared aggregate: inspect its exact part receipts and
use provider evidence where available. Missing part evidence does not authorize
another send. The completed immutable result remains available locally via
job-result/private reader under its current source/access scope. If the owner
explicitly asks for a new answer/send after reviewing that uncertainty, a NEW
request/job/intent can be created with a new identity and current bounded
delivery consent. It must never reset/delete the old attempt or automatically
resume it. No actual effect is claimed undone or never attempted from absence
of child rows alone. This is an availability limitation, not a fabricated failure.
