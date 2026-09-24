SLICE_REVIEW: STOP_SHIP

Reviewed read-only at `8db7f55d58751548087ce3fabf17929b64e7988b` (PA-09 commits `161ecd6..8db7f55`).

P1 blockers:

- `revise_subscription` accepts a caller-built replacement with arbitrary source refs, destination, schedule, quiet hours, and lifecycle, then activates it using only a private tuple and revision CAS. It bypasses the immutable expiring preview/confirmation used for initial subscription creation. A widened watch or changed delivery destination therefore lacks the required exact confirmation. [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:564)

- Unknown-send reconciliation is still assertion-based. Any caller can construct `WatchReconciliationEvidence(..., "not_delivered", opaque_ref, ...)`; `reconcile_unknown` does not validate the evidence’s provenance, owner, delivery receipt, or PA-02 operation linkage before re-queueing. This permits a blind retry dressed as reconciliation. [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:284) [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:1071)

- Required runtime verification and the observable delivery outcome remain unproven. `WatchJobStore` is referenced only by synthetic tests, while no authorized adapter binds it to collection or `telegram_delivery.py`. The scope amendment rightly forbids enabling such runtime delivery now, so this is an explicit unresolved gate—not authorization to enable it.

Required correction direction: make every consent-bearing subscription revision a one-use, owner-bound preview/confirmation (leaving only narrowly defined pause/cancel controls direct); require authoritative, owner-bound reconciliation evidence before re-queue; retain runtime delivery as an explicit blocked acceptance gate until separately authorized.

Evidence: `git diff --check 788414f^..HEAD` passed. The two PA-09 suites are registered in `focused-prm`; their execution could not run in this read-only sandbox because no writable temporary directory is available.

This review does not approve design, completion, runtime use, or release.