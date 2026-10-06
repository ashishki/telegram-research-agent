# PAI-08 local engineering receipt

2026-10-06. Base 741a47d; assigned branch. ADR-014 local synthetic scope.

PostgreSQL now stores exact expiring single-use subscription previews,
confirmed schedule revisions, next due slots, scheduler generation/token/lease,
occurrences, material-change baselines, pending notifications and subject
completion. Enqueue and schedule advancement share one transaction. Two fresh
processes create one occurrence. Queue capacity failure leaves the old due slot;
expired scheduler leases recover with a new generation. Downtime coalesces to
one collection, advancing from the current clock instead of replaying history.
Daily/weekly civil-time slots handle spring gaps and avoid a second folded-hour
occurrence. Only explicit one-shot methods run; no timer/service was enabled.

The actual collection worker loads current durable read grants, reserves shared
request/job/day/month budgets, checks current subscription and job fences under
locks through bounded fake I/O, then commits material changes and job result
together. Caller version churn does not create another notification. A changed
source deadline cancels waiting older evidence and recalculates reminder time.
Quiet hours and per-subscription caps filter eligible candidates; persistent
delivery quota/attempt ownership and final delivery checks are the next PAI-09
card. Collection grants never imply delivery grants. No actual send is claimed.

Private ingress routes exact Watch confirmation/status/pause/unsubscribe/done/
resume to these use cases when an explicit scheduler is injected. Status
distinguishes saved intent from an observed recent tick. Snooze and individual
subject completion use the same owner-bound scheduler API. Old UTD watches do
not grant any scope here.

Dependency fix: durable policy now refreshes database time after grant-lock
acquisition; an expiry during lock wait cannot authorize dispatch. A real
contended PostgreSQL test holds the final grant row through its expiry and
observes zero adapter calls.

Changed: new src/prm/runtime/scheduler.py, tests/test_pai_scheduler.py;
src/prm/runtime/ingress.py, src/prm/storage/jobs.py, src/prm/storage/policy.py,
tests/test_pai_durable_policy.py.

Verification:

```
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q tests/test_pai_scheduler.py tests/test_assistant_jobs.py tests/test_assistant_subscriptions.py tests/test_pai_durable_policy.py tests/test_assistant_permissions.py tests/test_assistant_egress.py tests/test_assistant_grant_codec.py
```

119 passed in 38.30s; zero skips/failures. Initial scheduler run: 10 passed in
19.83s. Prior expanded run with ingress: 52 passed in 45.05s. New expiry wait
test alone: 1 passed in 4.57s. Actual isolated PostgreSQL; source I/O synthetic.
`python3 tools/check_pai_plan.py`: 32 packets, 69 requirements, 10 scenarios;
21 future test files remain absent. `git diff --check`: passed.

Independent phase-B review remains pending (Mimo call #21 invalid completion).
Phase-C accumulated review follows PAI-09. No new paid call; 21/30 consumed.
Local_verified is engineering evidence, not formal/human/live/release approval.
Next: docs/PA_IMPLEMENTATION_TASKS.md#pai-09; common delivery/reconciliation.
