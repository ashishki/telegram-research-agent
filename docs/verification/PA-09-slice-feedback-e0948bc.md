SLICE_REVIEW: STOP_SHIP

Reviewed `e0948bc08037f679a349c1969453e373529ddcea` against pre-PA-09 `788414f`. Read-only review; no approval of design, completion, runtime use, or release.

P1 — the required observable/runtime outcome is unimplemented. `WatchJobStore` explicitly excludes scheduler, collection, Telegram transport, and default DB selection; it is only referenced by synthetic tests. No authorized adapter connects it to [`telegram_delivery.py`](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/telegram_delivery.py:1) or collection. This cannot establish “arrive reliably” or required runtime verification. The scope amendment forbids that integration, so it remains an explicit external acceptance gate—not authorization to add it.

P1 — changed-deadline handling is not a first-class durable contract. [`WatchNotification`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:191) has no source deadline/versioned deadline field; its `due_at` is the job’s send time, used by claiming logic. Deduplication fingerprints omit it, and queueing only replaces one supplied notification rather than atomically recalculating all future reminder stages when a deadline moves. This does not prove the PA-09 changed-deadline criterion. Define a source-bound deadline instant/timezone and atomic stage-recalculation invariant, with forward/backward-change holdouts.

Positive local evidence: private, expiring confirmation; exact background-purpose grants; evidence-baseline dedupe; final policy/grant checks; durable pre-send attempts; verifier-gated unknown-send reconciliation; and feedback idempotency are present.

Verification: `git diff --check 788414f..HEAD` passed. `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm` could not start because this read-only environment has no usable temporary directory; no test pass is claimed.