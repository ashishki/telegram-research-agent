# Phase-C review #39 response — cancel race fixed; parent-fence claim disputed

Receipt PAI-review-continuation-39.json, source 15db746; valid FIX_P1_FIRST.
Independent Mimo retains two P1s. No implementer verdict substitutes for recheck.

Cancellation had a real narrow race: queued/retry_wait could become leased
between the first status read and cancel. The warning and cancellation callback
now use the authoritative post-cancel attempt count, covering that transition.
The executable case claims a real job after the first read, then cancels it;
the exact warning/callback and cancelled status are verified.

The multipart finding's own execution analysis confirms that existing aggregate
rows stop another sender loop and parent reconciliation already checks exact
child evidence. It then calls the conservative unknown parent with zero children
a blocker and suggests making it automatically resumable. That recommendation
contradicts the current prepared-effect/unknown no-blind-retry boundary. A new
case interrupts immediately after aggregate preparation, verifies zero child
attempts, then calls delivery and reconciliation again: no send and no invented
provider evidence occur. This is intentionally conservative. Source contains
no resume/send-in-reconciliation path. The independent reviewer must resolve
the claim against the actual counterexample and the agreed recovery boundary.
Do not remove a non-replayable parent based only on missing child rows.

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_ingress_jobs.py tests/test_pai_delivery.py
```

First run: 1 failed / 4 passed in 5.07 s, from passing a callback to the fixture's
JobQueue kwargs. Corrected the test setup to the actual ingress callback field.
Final: 36 passed in 42.42 s, zero skips/failures. Source change: ingress.py;
tests: test_pai_ingress_jobs.py and test_pai_delivery.py. Existing scheduled
lease/cancellation and per-part proof assertions remain intact.

Native planning preparation temporarily showed an unselected depth. The
existing explicit delegation and assigned designed_slices selection are recorded
in PAI-00-reconciliation.md and PAI-01-durable-design.md (authorized workflow
continuation). Re-generated planning artifacts were reselected through the real
interactive pinned select-plan under that same delegation, with human:owner
as the established alias; no new feature design acceptance was inferred.
The native tooling prepare-only gate now passes, 131737 bytes, provider_call=false.
No fresh owner decision or approval was fabricated from budget permission.

Next: fresh bounded C recheck; continued D/E/F source reviews and independent
native tooling audit are already within ongoing review-budget authority.
