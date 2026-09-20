SLICE_REVIEW: STOP_SHIP

Reviewed read-only at `730729a98aad392a60090b158e89084191341187`. No tests run.

P1 blockers:

- Unknown-send reconciliation still permits a caller assertion to requeue work. `reconcile_unknown` accepts caller-created `WatchReconciliationEvidence`, then deletes the durable attempt record and requeues on `"not_delivered"` without adapter/provider-verifiable evidence or a retained reconciliation audit receipt. The persisted pre-send attempt improves crash recovery, but does not prevent a blind retry. [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:1236)

- The public delivery interfaces disagree on durable attempt/receipt semantics. `prepare_delivery` documents `finish_delivery` as the adapter path, but only `deliver_claimed_job` persists the pre-send attempt. `finish_delivery(..., outcome="sent")` also accepts no transport receipt. Thus a caller following the documented API can mark a job sent without a receipt or crash-recoverable reconciliation record. [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:845) [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:1425)

- The observable PA-09 outcome and required runtime verification remain unproven: `WatchJobStore` is referenced only from synthetic tests; no authenticated subscription ingress, collection adapter, or `telegram_delivery.py` binding exists. The scope amendment expressly forbids enabling these now, so this is an explicit unresolved acceptance gate, not authorization to add runtime delivery.

The latest commit correctly adds a durable pre-send attempt for the `deliver_claimed_job` crash path, but does not close the reconciliation/receipt contract. This review does not approve design, completion, runtime use, or release.