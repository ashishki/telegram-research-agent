SLICE_REVIEW: STOP_SHIP

Reviewed read-only at `a11373990d5e86877a39aa5566a8105ed531aba8`.

P1 blocker: unknown-send reconciliation is not durable across a worker restart. A crash during `sender()` rolls back the transaction; expiry later marks the lease `unknown`, but records no `pa_watch_unknown_attempts` row. The suite explicitly asserts that no reconciliation requirement exists for this case. [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:965) [test_assistant_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/tests/test_assistant_jobs.py:98)

Even for an exception path that does persist an unknown-attempt record, reconciliation depends on PA-02’s explicitly in-memory operation group. A restarted registry cannot establish the original operation’s unknown state, so it cannot reconcile or safely requeue it. [capabilities.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/capabilities.py:488) [capabilities.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/capabilities.py:726) [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:1127)

This fails PA-09’s required restart/unknown-send reconciliation outcome and WATCH-04’s durable states, receipts, and reconciliation procedure. The correction needs a durable pre-send attempt/reconciliation record and an adapter-owned, owner/destination/operation-bound reconciliation contract that survives process restart; it must remain fail-closed and never authorize a blind retry. Add a restart-after-send-start holdout.

Scope/file boundaries otherwise appear respected, and the prior confirmation, final-preflight, dedupe, DST, and double-send fixes are represented in local holdouts. `git diff --check 788414f^..a113739` passed.

The scoped PA-09 pytest command could not start because this read-only sandbox has no usable temporary directory; this is an environment limitation, not a passing result. No design, completion, runtime use, or release is approved.