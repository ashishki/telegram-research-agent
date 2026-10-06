# PAI-02 — actual PostgreSQL foundation

Engineering: local_verified; independent phase-B review pending.
Local work proceeds under ADR-014. Formal design/slice acceptance is unchanged.

Implemented: explicit synthetic backend target; process-local connections and
unit of work; checksum/versioned transactional migration; owner-scoped immutable
object versions with digest verification and CAS heads; explicit migration CLI.
Unknown/missing backend, production/default target, privileged role, foreign
server marker, ambient libpq configuration and altered schema fail closed.
SQLite archive adapter and IDs remain unchanged.

Real tests create an isolated PostgreSQL 14.24 process and two unprivileged SQL
roles, exercise concurrent separate processes, rollback, version/owner isolation,
parameterized SQL, actual pg_dump/pg_restore, corruption and migration CLI, then
stop that process and remove only its temporary directory. No service or
production database is accessed.

Driver: psycopg 3.3.6, isolated .venv-pai, official pure wheel verified before
installation: SHA256 a1db9f7148b06a28606767efaca51fa6f9398c5c0a3810519be69d7000bdb631.
Sources: https://pypi.org/project/psycopg/3.3.6/ ;
https://www.psycopg.org/psycopg3/docs/basic/transactions.html ;
https://www.postgresql.org/docs/14/backup-dump.html .

Acceptance command:
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q tests/test_pai_storage.py tests/test_assistant_contracts.py tests/test_archive_search.py

Initial failures were preserved: missing runuser in reduced PATH (13 passed,
16 fixture errors), then libpq rejecting service="" (1 fixture error). Fixed
absolute runuser path and explicit refusal of ambient PG configuration; no test
was weakened or skipped. Final result: 31 passed in 9.55 s; 31 cases, zero skips/failures.

Setup: python3 -m venv --system-site-packages .venv-pai; install the pinned
psycopg wheel from requirements.txt (the initial installation used pip
--require-hashes --only-binary=:all: --no-deps with the hash above).
Storage is disabled until the caller supplies a complete SyntheticTarget.
Migrations require explicit --target synthetic-test, instance identity,
loopback port, dedicated migrator and expected schema version. No .env/DSN
or fallback path is loaded.

Next card: PAI-03, durable shared grants/reservations/budget accounting.
