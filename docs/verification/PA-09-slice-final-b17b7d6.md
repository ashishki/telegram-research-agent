SLICE_REVIEW: STOP_SHIP

Reviewed read-only at `b17b7d65ccc24b4e5d1c52f9b64239cc2b35c120`. No tests run.

- P1: “Confirmed” subscription creation is not enforced. [`register_subscription`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:429) verifies the private tuple but accepts any caller-built subscription; it has no immutable preview/confirmation binding, expiry, or confirmation receipt. The module has no production caller outside its synthetic tests.

- P1: Unknown reconciliation is not evidence-bound. [`reconcile_unknown`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:970) accepts an arbitrary `"delivered"`/`"not_delivered"` assertion and optional opaque string, then records a receipt or requeues the job. This permits a blind retry through the reconciliation API—the exact outcome PA-09 must prevent.

- P1: The local runner can manufacture a false unknown-send case. When `access_for_job` returns `None` or raises, [`run_once`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:942) leaves the claimed job leased. Lease expiry later changes it to `unknown`, although no transport was attempted. It should durably cancel/defer as known-not-sent and release/abandon the reservation; add a holdout asserting that state.

- P1: Runtime delivery remains absent. The watch module explicitly has no Telegram transport or service, while [`telegram_delivery.py`](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/telegram_delivery.py:1) is not bound to the watch authorization/outbox path. The scope amendment correctly prohibits live delivery now, so this is an explicit unresolved runtime-acceptance gate—not a request to enable it. The slice cannot claim its observable delivery outcome or required runtime verification until a separately authorized adapter and runtime exercise exist.

The amendment covers `src/prm/capabilities.py` and `tools/test_tiers.py`; that earlier scope mismatch is resolved. This review does not approve design, slice completion, runtime use, or release.