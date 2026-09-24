SLICE_REVIEW: STOP_SHIP

Reviewed read-only at `8699aa22b2a1e92a746d06a542703d1e76acd1f6`, diffed from pre-PA-09 `788414f`. Scope is within the 24-file budget; the PA-02 purpose mapping and test-tier edits are covered by the recorded scope amendment.

P1 — required runtime verification and the observable delivery outcome remain unavailable. `WatchJobStore` explicitly has no scheduler, source collector, or Telegram transport, and has no runtime integration outside synthetic tests. The PA-09 amendment expressly forbids service/timer/provider/Telegram-delivery/runtime-acceptance work, so this is an unresolved acceptance gate—not authorization to add it. The slice cannot claim that confirmed watches “arrive reliably” until a separately authorized adapter and runtime exercise exist. [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:1) [telegram_delivery.py](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/telegram_delivery.py:1)

Advisory — repeated identical feedback is not mutation-idempotent: `INSERT OR IGNORE` does not gate the subsequent pause/unsubscribe revision update, so repeated callbacks can keep incrementing `consent_revision`. Gate the lifecycle mutation on a newly inserted feedback receipt and add a duplicate/concurrent-feedback holdout. [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:1516)

Positive local findings: owner-bound expiring confirmation covers creates and revisions; event evidence baselines suppress version churn while preserving reversals; dispatch has exclusive final policy/grant checks and durable pre-send attempts; unknown outcomes require verifier-produced attestation before requeue; dedicated PA-09 suites are registered in `focused-prm`.

Verification: import/purpose-map smoke check and `git diff --check` passed. `python3 tools/test_tiers.py focused-prm` could not start because the read-only environment has no usable temporary directory; no test result is claimed.

This report does not approve the design, slice completion, runtime use, or release.