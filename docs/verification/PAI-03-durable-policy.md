# PAI-03 — shared durable policy and budget

Engineering: local_verified; accumulated phase-B Mimo review pending.

PostgreSQL now owns grant revisions/revocation, per-revision call counters,
request/job/day/month window balances, operation groups and scoped reservation
members. The existing CapabilityRegistry validators and text/context contract
are reused. The public transport helper recognizes this explicit durable
backend and commits the whole operation atomically; there is no in-memory
allowance fallback during a database outage.

A prepared operation persists before I/O; unknown usage stays conservatively
charged and its operation ID cannot be reused after restart or window rollover.
Known usage settles by locked CAS/idempotent update. Optional context can be
abandoned before dispatch without authorizing its egress. Budget windows cannot
be overwritten to reset already incurred spend. Price None denies reservation.
The actual adapter entrypoint execute_reserved rechecks grant rows under locks
through one bounded transport; external I/O is faked in these tests.

Acceptance:
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q tests/test_pai_durable_policy.py tests/test_assistant_permissions.py tests/test_assistant_egress.py tests/test_assistant_grant_codec.py
86 passed in 11.43 s; zero skips/failures. Includes real two-process contention,
revocation/revision, restart/unknown/new funding, compound transport and outage.
Initial compound fixture used archive.read instead of the existing closed
model.context_egress contract; corrected the fixture, not the scope policy.

New policy schema is transactional and checksum/versioned, separate from the
PAI-02 immutable object foundation. Current default ingress is not wired to it
until PAI-07; this is storage/transport behavior, not product/live acceptance.
Next: PAI-04 durable confirmations, attempts and receipts.
