# Review 59 — source identity and truthful possible usage

The reviewer resolves the prior GitHub denial and durable prepared-read P1s. Its new missing-size allegation misreads the actual default: 128001 > 128000 already rejects missing size. Nonetheless metadata validation is strengthened to require a non-negative bounded integer size and a 40-hex blob SHA; malformed provider metadata must fail with typed StorageError, not partial evidence. Four negative cases exercise the adapter.

Research tool_calls intentionally bounds possible work, not a measured provider-call count. The result now explicitly labels tool_call_accounting=conservative_upper_bound and exposes unknown_tool_calls separately. Unknown prepared work must never be refunded or retried. This preserves the budget safety limit and prevents readers mistaking upper-bound usage for actual measured calls.

Canonical archive content is hashed in full to retain source identity. Hashing an arbitrary prefix as suggested would weaken provenance. Missing/non-string/blank source content is filtered before the comprehension expression executes; no such exception path remains.

Independent recheck pending; exact scoped tests and preserved failures appear in the validation ledger.
