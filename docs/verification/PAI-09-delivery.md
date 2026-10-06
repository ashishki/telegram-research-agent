# PAI-09 local engineering receipt

2026-10-06. Base 5b4347d; assigned branch, ADR-014 synthetic scope.

The common DeliveryExecutor uses shared durable policy for answer delivery,
Watch delivery and exact confirmed actions. Purposes remain answer.delivery,
watch.delivery and action.execute. A delivery attempt with unknown status
commits before provider I/O. Identity binds owner/source/result/content/
destination; restart, duplicates and lost ACK do not resend that identity.
Only a typed actual transport receipt establishes sent. A complete known
negative response establishes not_sent and still does not auto-retry.

The final guard holds grant then subscription/notification or effect-job fence
then attempt locks through one bounded adapter call. Pause/revoke winning first
prevents transport; dispatch winning first delays same-scope acknowledgement.
Persistent Watch quotas count sent and unknown attempts across restarts and
enforce the current local day. Current due/revision/lifecycle/quiet hours remain
final checks. An explicitly supplied stale/cancelled effect lease denies send.
The existing SQLite Watch sender/transaction boundary was preserved unchanged.

Reconciliation requires separate current read authority and an adapter's exact
attempt/destination/digest/evidence binding. Absence of lookup/evidence retains
unknown; a strong provider result establishes sent/not_sent without another
send. Confirmed action reconciliation uses its own connection/provider/resource
and action.reconcile purpose, with the same final policy and durable ledger.
Private ingress delivery-status and the explicit prm_handlers delivery seam
use these actual use cases. Automatic worker-to-live delivery remains a later
runtime configuration decision; no credential, account or service was enabled.

Connection-loss test initially exposed a real bug: psycopg's closed transaction
could exit without raising and a successful adapter return became sent. Final
delivery/policy/action/collection guards now reject closed scope connections;
the precommitted unknown fence remains. Actions also recheck proposal and
confirmation expiry after acquiring final locks, before I/O.

Changed: src/prm/runtime/delivery.py, tests/test_pai_delivery.py;
src/bot/prm_handlers.py, src/prm/runtime/ingress.py, scheduler.py,
src/prm/storage/actions.py, policy.py.

Verification:

```
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q tests/test_pai_delivery.py tests/test_assistant_jobs.py tests/test_assistant_actions.py tests/test_assistant_egress.py tests/test_pai_durable_actions.py tests/test_pai_ingress_jobs.py tests/test_pai_scheduler.py tests/test_pai_durable_policy.py
```

112 passed in 91.89s, zero skips/failures (before the additional action lookup
test). Current delivery file independently: 12 passed in 22.61s, zero skips.
Action lookup test alone: 1 passed in 3.88s. Connection-loss recheck: 1 passed
in 4.57s. Earlier expanded run: 1 failed/87 passed in 55.23s; preserved above,
fixed in code. Initial test import path failed collection and was corrected to
the repository's tests package; no acceptance behavior was weakened.

Actual PostgreSQL and a synthetic loopback HTTP provider accepting a send while
dropping ACK were used. Other provider calls are faked; no live send occurred.
`python3 tools/check_pai_plan.py`: 32 packets, 69 requirements, 10 scenarios;
20 future test files absent. `git diff --check`: passed.

Phase-C focused-prm floor and independent Mimo review are in progress. Prior
phase-B Mimo call #21 had no valid completion. Engineering evidence does not
grant formal/human/live/release acceptance. Next after the review/findings:
PAI-10 actual Chat composition, with all current external authority gates.
