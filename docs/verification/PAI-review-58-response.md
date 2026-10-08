# Review 58 — replay diagnostics and known invalid replies

All replays still deny. ModelAttemptAlreadyRecorded now exposes recorded/requested digests and input_changed for independent audit; initial input digests must be 64 lowercase hex. This adds diagnostic precision without allowing divergent or identical retries.

Known malformed provider replies now raise typed ModelResponseInvalid(retry_allowed=False) with durable attempt/operation refs rather than transport-unknown. JSON/choice/message/usage detail shape is checked; cached tokens and reasoning tokens must be non-negative integers no greater than their respective totals. Observer/accounting failure cannot replace the typed invalid-reply failure with a raw exception; accounting_status is unconfirmed. The reservation stays conservatively settled unknown and the logical fence remains. No known invalid output authorizes retry or zero billing.

A real HTTP fixture returns malformed cached-token usage. The test also fails the usage observer, verifies typed no-retry/fence refs/unconfirmed accounting and forbids a reconstructed-client second HTTP call. Exact scoped results are recorded after completion. No acceptance is self-issued.
