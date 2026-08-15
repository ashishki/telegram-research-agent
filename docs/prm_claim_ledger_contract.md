# PRM Claim Ledger Contract

Status: active
Schema: `prm_claim_ledger.v1`

Each factual answer path builds an internal claim ledger before public rendering.

```yaml
claim_id:
claim_text:
claim_type:
freshness:
support_status:
evidence_refs:
independent_source_groups:
confidence:
project_relevance:
operator_action_relevance:
```

Supported statuses: `supported`, `partially_supported`, `unsupported`, and
`contradicted`.

Rules:

- Unsupported source-derived claims cannot enter factual prose.
- Partial claims must remain cautious.
- Recommendations are labelled separately from source facts.
- Current-fact claims stay blocked unless primary-source verification ran.
- Claim IDs remain internal and may appear only in private traces.
