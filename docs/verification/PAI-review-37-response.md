# Phase-C review #37 response — recheck pending

Reviewed source: cf3c00b; receipt PAI-review-continuation-37.json. Valid
FIX_P1_FIRST (one P1, two P2), independent OpenCode Go / mimo-v2.6-pro,
thinking disabled, 16000 output / 900 s. Implementation is not a review verdict.

The alleged absence of final delivery-grant validation is contradicted by the
existing execute_reserved_groups path: it locks/revalidates the selected grants
through the sender, and DeliveryExecutor already invokes _source_current for
both answer/watch paths. A real regression now revokes the Watch delivery grant
AFTER durable preparation and verifies zero sender calls, unknown attempt,
and no retry of that attempt. The next packet supplies the previously omitted
policy source so the reviewer can independently resolve this allegation.

Following the source-visibility part of the finding uncovered a real adjacent
gap: Watch notifications previously omitted their collection scope. The worker
now saves the exact sealed source request (without an operation reservation)
alongside each notification. Delivery reads that provenance and retains the
existing current source-grant and Graph-connection locks through the sender.
Revoking collection consent after collection blocks sending. Old notifications
without source authority require recollection; the runtime does not invent or
upgrade consent. The strict legacy notification codec receives only its declared
notification fields, while the original full payload digest also binds provenance.

Source locks are taken before the subscription lock, matching collection order.
A concurrency case holds the source grant after preparation, waits for dispatch
to reach source validation, and proves the subscription remains lockable until
the source lock is released. The sender completes once without a lock cycle.

The two P2 fixes: empty document/photo file IDs are denied before persistence;
both archive/mail collectors use WatchScheduler._now, honoring the injected
clock or default database clock. The default clock is None, so it is deliberately
not called as a function. Actual wiring tests cover the fixed and default paths.

Exact checks:

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_delivery.py tests/test_pai_scheduler.py tests/test_pai_ingress_jobs.py
```

Initial fixes: exit 0, 46 passed in 68.69 s, zero skips/failures.

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_delivery.py tests/test_pai_watch_wiring.py tests/test_pai_ingress_jobs.py
```

Final source-lock/clock wiring: exit 0, 35 passed in 60.61 s, zero skips/failures.
The new wiring file is registered in the existing strict pai-complete verifier.
Controlled synthetic logs: pai-validation-20261008/watch-fixes.log and
watch-origin-locks.log under .playbook-artifacts. No actual source/send/timer ran.

Phase-B #36 independently returned SHIP_OK; its P2 advisory about trusted
settlement is preserved. Actual monetary settlement is an internal accounting/
operator reconciliation method, not a product tool or authorization grant;
it requires actual provider usage/tariff or verified no-transport evidence.
It cannot clear an attempt fence. Existing provider scopes/window bounds remain.
Focused-prm on the phase-B repaired source: 652 passed in 132.56 s (pre-C-fix
evidence). Its run is not labeled as verification of these later Watch changes.

Changed source: runtime/ingress.py, scheduler.py, delivery.py, watch.py.
Tests: test_pai_delivery.py, test_pai_ingress_jobs.py, test_pai_watch_wiring.py.
Verifier: tools/test_tiers.py. Next: fresh independent #38 recheck with full
current policy/runtime/tests, then remaining D/E/F packets. Review-budget
increases are already owner-authorized as needed; other gates are unchanged.
