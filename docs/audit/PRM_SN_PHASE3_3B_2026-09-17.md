# PRM-SN-3B — fixture-only primary-source verification receipt

Date: 2026-09-17. Final focused diff hash:
`cab045b0a8ef83680e836e2c569c1040706e1a710009366b84291b0385c8c9ac`.

`primary_source_verification` now uses declarative `fixture_responses`, never
a callable transport or network client. It accepts only canonical lowercase
ASCII HTTPS DNS hosts on the default port; trust records are exact validated
hosts; GitHub/arXiv built-ins are exact. MIME, redirect host/explicit-port,
cache, failure and claim-ledger paths fail closed. Cache entries are fixture
artifacts and cannot establish verification or claims.

Focused verification:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  tests/test_primary_source_verification.py tests/test_external_watch_fetch_safety.py \
  tests/test_prm_application.py -q
32 passed in 1.87s
```

Independent read-only review: session
`01a0b02a-cf96-7d01-9942-c987249340a5`; runner observed
`gpt-5.6-terra`, reasoning effort `high`; final result
`PACKET_REVIEW_RESULT: PASS`. Prior findings covering callable transport,
Unicode/IP/port/MIME and cache evidence boundaries were corrected before this
final review.

No live provider/network request, private-data egress, production write,
pilot action, delivery, commit or merge occurred. Rollback is to remove this
fixture-only reader from the local answer path; runtime remains capability-off.
