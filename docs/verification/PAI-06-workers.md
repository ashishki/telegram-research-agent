# PAI-06 — durable queue and process worker

Engineering: local_verified; accumulated phase-B review next.

PostgreSQL enqueue can share the domain transaction. Queue admission and
idempotency are atomic; claim uses FOR UPDATE SKIP LOCKED, database time,
bounded attempts, priority, lease generation/token and heartbeat. Fenced
checkpoint/completion validates current input owner/ref/version/digest.
Unsupported payloads quarantine; cancellation/expiry/stale generation prevent
writes. Safe compute retries use bounded backoff. Effect expiry is permanently
awaiting_reconciliation, never a compute retry or automatic send.

Only versioned refs/consent metadata fit job payloads; callables, credentials
and authorization snapshots are rejected. ComputeWorker runs in a separate
process and produces its own persisted result. No scheduler/service/timer is
enabled; live research/render/effect handlers remain later composition work.

Acceptance:
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q tests/test_pai_workers.py tests/test_assistant_jobs.py tests/test_assistant_research.py
45 passed in 22.50 s; zero skips/failures. Includes two-process claim race,
killed-worker recovery, exact checkpoint/new generation, stale writes,
unknown effects, atomic rollback, backpressure, priorities, heartbeat and retry.

Phase-B floor:
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/test_tiers.py focused-prm
652 passed in 110.62 s. No historical full pytest suite was run.

Next: independent accumulated phase-B Mimo diff review, resolve P0/P1/recheck,
then PAI-07 real ingress/background jobs and composition. Formal acceptance,
private accounts/egress and production/release remain separate from this evidence.
