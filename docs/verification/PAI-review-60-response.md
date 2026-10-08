# Review 60 — synthetic counterexample supersedes static SHIP_OK

The static independent review returned SHIP_OK, but the real HTTP/accounting-failure test reproduced a concrete interaction omitted in its analysis: execute_reserved_groups wraps ModelResponseInvalid as ScopeTransportUnknown, so a direct exception-type catch did not preserve known-invalid classification; the generic usage observer could then mask no-retry with a raw accounting error. The failure is retained in known-reply-source-metadata-final.log (1 failed, 10 passed).

The transport now captures only a positively observed ModelResponseInvalid before the compound wrapper. After conservative settlement, the caller receives that typed non-retryable failure with fence refs regardless of wrapper/observer failure. Other transport failures remain typed LLMOutcomeUnknown; their observer failure likewise cannot replace the no-retry failure. No exception-chain guessing, zero billing or fence reset. Accounting status is unconfirmed when recording fails.

Fresh independent recheck and corrected actual HTTP tests required; #60 alone is not final acceptance of this changed boundary.
