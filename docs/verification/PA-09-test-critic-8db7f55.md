TEST_CRITIC: STOP_SHIP

No P0 found. P1 blockers:

- Double-send race remains untested and possible: two callers holding the same lease can both pass preflight/quota and invoke `sender`; only one later receipt update wins. The test races claim only, not concurrent delivery. [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:966)

- Pause/revocation is not proven at the actual final synthetic send boundary. Lifecycle is checked before the quota transaction commits; after that, only the grant is rechecked before `sender`. A pause after that commit can still send. The test pauses inside mocked `prepare_delivery`, earlier than this window. [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:995)

- Reconciliation is not evidence-bound: any caller-built opaque `evidence_ref` with `"not_delivered"` requeues an unknown job. The focused test blesses precisely that assertion, so it does not prove receipt/reconciliation evidence or prevent a blind retry. [watch_jobs.py](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:1071)

- DST/quiet and reminder dedupe tests are insufficient. The DST test never finishes the claimed job; its later assertion is satisfied by lease expiry/`unknown`, not the stated receipt-based no-repeat behavior. It also lacks fall-back, quiet-end release, and deadline-stage duplicate holdouts. [test_assistant_subscriptions.py](/srv/openclaw-you/workspace/telegram-research-agent/tests/test_assistant_subscriptions.py:150)

- Background collection uses a distinct capability in code, but the tests lack the essential negative case that a foreground/read grant cannot construct or pass the watch-collection boundary.

Owner-bound preview/one-use confirmation and cross-owner feedback rejection are locally covered. The two suites are registered in `focused-prm`. I could not execute them because the read-only environment has no writable temporary directory; this is not a test failure.

The missing live Telegram/provider/service/timer exercise is the explicitly forbidden runtime gate, not a finding or requested action in this review.