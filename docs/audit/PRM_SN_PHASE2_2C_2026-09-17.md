# PRM-SN-2C — archive health receipt

Date: 2026-09-17

`/refresh` remains owner-only and read-only. It now projects canonical archive
coverage from SQLite using a read-only URI: row count and actual maximum
`posts.posted_at`. It does not start ingestion, migrations, index building,
timers, provider calls, or writes.

The operator rendering separates coverage from refresh lifecycle: it shows the
coverage timestamp and says `последняя попытка: неизвестно` because this path
has no durable attempt ledger. Missing/unreadable source is an error; an empty
archive is stale; existing archive coverage is `новых данных нет`. Supplied
component receipts still render partial, stale-index and source-failure states
separately. Status-request time is never used as archive freshness.

Verification:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  tests/test_prm_refresh_receipt.py tests/test_prm_utd_dispatch.py \
  tests/test_prm_post_answer_actions.py -q
32 passed in 25.14s
```

`py_compile` and `git diff --check` passed. No receipt persistence was added,
so no schema/retention immediate review was triggered. The accumulated Phase 2
deep review remains required before Phase 3.
