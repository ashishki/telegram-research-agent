SLICE_REVIEW: STOP_SHIP

Reviewed HEAD `161ecd680b3a7f878d9c08ee18a17af23bec5573` against `788414f`; read-only review, no tests run.

P1 blockers:

- PA-09 has no durable worker, collection integration, Telegram transport integration, or runtime verification. [`watch_jobs.py`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:1) explicitly excludes all of these, so it cannot deliver the required observable outcome or enforce policy at the actual final-send boundary.
- Background collection accepts any reserved `read` authorization. [`collection_allowed`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:477) reuses the decision’s own capability/purpose rather than requiring a watch-specific background-collection scope. This violates the boundary that read consent is distinct from background-job consent.
- Pause/revocation can race after [`prepare_delivery`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:674) returns and before a future sender acts. There is no transport-owned atomic final preflight, so “before final send” is not established.
- Duplicate suppression is keyed by caller-controlled `delivery_stage`; arbitrary distinct stages for one subject/version can enqueue repeated alerts. [`WatchNotification`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:146) permits broad stage values and [`idempotency_key`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:176) includes them.
- Required `focused-prm` verification does not include either new PA-09 test module. [`tools/test_tiers.py`](/srv/openclaw-you/workspace/telegram-research-agent/tools/test_tiers.py:15) omits `test_assistant_jobs.py` and `test_assistant_subscriptions.py`.

Required correction direction: define owner-bound confirmed subscription creation/feedback, a fixed background-watch permission scope, bounded event/version reminder policy, and one transport-owned final authorization/lifecycle check with durable outcome reconciliation. Register PA-09’s dedicated tests in the required tier, then obtain an independent recheck.

This review does not approve the design, slice completion, runtime use, or release.