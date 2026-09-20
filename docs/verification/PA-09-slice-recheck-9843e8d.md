SLICE_REVIEW: STOP_SHIP

Reviewed read-only at `9843e8d503d50f3c5b61570fda8216f5c1eee930`. No tests run.

P1 blockers:

- The diff changes disallowed files: `src/prm/capabilities.py` and `tools/test_tiers.py` are outside PA-09’s allowed-files list. This needs an explicit approved scope/design correction, not a silent exception.

- PA-09 has no authenticated confirmed-subscription or feedback ingress. [`record_feedback`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:1015) accepts only a job key and action, then can pause/unsubscribe or complete work. It receives no owner/chat/actor binding, so it cannot enforce the private-owner control boundary.

- The implemented runner is still detached from actual collection and Telegram transport: `WatchJobStore` is only referenced by its local tests. No PA-09 integration exists in `src/external_watch/` or [`telegram_delivery.py`](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/telegram_delivery.py:1). Thus the required runtime verification and observable “confirmed watches arrive and stop when revoked” outcome are not established.

- Grant revocation is checked during [`prepare_delivery`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:694), before the injected sender runs. [`deliver_claimed_job`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:863) rechecks subscription state, but not the current delivery grant immediately at the transport request. A revoke after preparation can still reach `sender`, violating the required final-send grant check.

Required correction direction: define owner-bound confirmed creation and feedback interfaces; bind a real authorized collection/delivery adapter to them; move the final grant/lifecycle/revision check into the transport-owned send boundary; add adversarial tests for cross-owner feedback and revoke/pause after lease/preflight but before send. Resolve the allowed-file mismatch through the governing design workflow before proceeding.

This review does not approve design, completion, runtime use, or release.