# Review 51 — selected message body metadata

The reviewer independently resolved both #48 P1 allegations: cursor replays cannot bypass source scope/current authorization, and the global active-secret guard correctly protects other owners. Cursor lifetime remains a P2 advisory; version=1 is a read of an immutable stored version, not an ignored expected-version parameter.

The new selected-body parsing defect was present: read_message now uses the same typed metadata validation as sync/fetch, and validates body/contentType shape before HTML parsing. Four PostgreSQL/HTTP adapter counterexamples mutate the returned body/date/sender shape and require StorageError. None changes authorization or releases a possibly processed request.

Scoped command and actual result are recorded in PAI-validation-20261008.json after completion; an independent recheck remains required.
