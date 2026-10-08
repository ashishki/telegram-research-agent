# Review 63 — durable accounting and constructor-bound preparation metadata

Accounting-unconfirmed is now persisted in the existing owner-scoped durable model attempt (provider_outcome=accepted, accounting_status=unconfirmed, exact operation refs, bounded known model/token metrics, cost=None, usage_recorded=False). Model text is not duplicated into the accounting marker. The typed returned receipt remains accepted and nonretryable. If this durable write also fails, ModelAccountingUnconfirmed carries the accepted receipt and exact fence refs with retry_allowed=False instead of a raw storage error.

Chat application result payload explicitly retains accounting_status=unconfirmed; the ordinary worker persists it with the actual answer. A full application/HTTP/CostCache failure test verifies this result survives storage. The direct receipt tests independently reconstruct/read the durable marker and verify no model text or fabricated zero price there.

ScopePreparationUnknown now declares attempt_ref and external_call_attempted=False at construction. ScopedModelClient constructs this preserved exception type with the logical attempt reference; no ad-hoc field injection is required. The known DB-preparation fence remains nonretryable and never becomes an unknown provider transport.

This response is implementation evidence only. Actual scoped result and independent P1 recheck are required; no approval is asserted here.
