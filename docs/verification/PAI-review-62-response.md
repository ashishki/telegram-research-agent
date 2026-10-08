# Review 62 — preparation and accepted accounting boundaries

Review #62 independently confirms the real compound invalid-reply/accounting masking fix, then identifies adjacent accepted-response and pretransport classification paths.

ScopePreparationUnknown now remains its actual typed nonretryable preparation error with attempt refs and external_call_attempted=False. Other failures before HTTP surface ModelPreparationUnknown; the durable preparation fence is retained. No never-attempted transport is called an unknown provider response and no unconfirmed DB preparation is reset.

A positively observed valid reply survives both final compound settlement acknowledgement failure and success-path observer failure. The returned frozen ModelAccountingReceipt retains actual text/model/token fields and accepted delivery outcome, usage_recorded=False, cost=None, accounting_status=unconfirmed, exact attempt/operation refs and retry_allowed=False. This preserves the answer for all existing callers without turning an accepted call into retryable failure. Cancellation remains independently fenced before result completion. Known invalid responses retain their distinct typed error even if observer fails.

Real HTTP cases cover invalid reply, accepted reply with observer failure, accepted reply followed by synthetic lost settlement acknowledgement, reconstructed-client denial and distinct preparation unknown. Exact scoped result and final independent recheck remain required. P2 mutable legacy exception and endpoint-path advisories are preserved; no endpoint expansion or human approval is inferred.
