# Entropy Core And Gensyn Integration

Status: planned reference integration
Last updated: 2026-05-29

## Purpose

Telegram Research Agent can emit research receipts for high-impact weekly
briefs and channel intelligence claims. Entropy Core vocabulary keeps the
evidence window explicit without making the private assistant depend on another
runtime.

Gensyn is a design reference for diverse analysis and evaluator/referee roles,
not a runtime dependency.

Before building custom Gensyn-shaped logic, run the Gensyn OSS reuse gate from
`repo://AI_workflow_playbook/docs/entropy_core_and_gensyn_reference_policy.md`.
Check official Gensyn repos first and record whether the result is dependency,
vendored component, adapted code, pattern-only reuse, or rejection.

## Entropy Core Use

Default level: receipt-compatible now; evidence-lookup compatible next.

Entropy Core is optional vocabulary only for this repository. Local receipt
generation, storage, delivery, verification, and inspection must not require an
Entropy Core runtime.

Planned local artifacts:

- `research_brief_receipt`
- `source_claim_receipt`
- `channel_intelligence_referee_verdict`
- `operator_usefulness_verdict`

Example:

```yaml
type: research_brief_receipt
source_project: telegram-research-agent
brief_week: 2026-W22
channels:
  - channel: example_channel
    message_window: "2026-05-22..2026-05-29"
artifacts:
  - path: data/output/briefs/2026-W22.md
evidence:
  - source_link: https://t.me/example/123
    claim_id: claim-001
verifier:
  method: operator_review
  status: pending
entropy_core:
  use_level: receipt_compatible
  runtime_dependency: false
```

The detailed local contract for `research_brief_receipt` lives in
`docs/research_brief_receipt.md` and keeps the same vocabulary for evidence
window, source set, artifact refs, verifier method, and verification status.

## Proof Layer Implementation

The Telegram Research Agent already has product-local receipts and verification
checks. Entropy Core should be used as a downstream proof contract, not as
runtime storage or generation logic.

Implementation path:

1. Add a stable Core-compatible schema id to `research_brief_receipt`.
2. Ensure receipt evidence refs point to canonical digest/evidence/source rows.
3. Add Core-style evidence lookup checks for delivered briefs and future
   channel intelligence receipts.
4. Use schema compatibility checks before changing receipt fields.
5. Keep usefulness, delivery behavior, Telegram source parsing, and operator
   review product-local.

Core value here: prove what inputs and evidence produced a brief, and make
stale or missing receipt evidence visible before the operator trusts a weekly
summary.

## Required Context-Refs

```yaml
Context-Refs:
  - repo://AI_workflow_playbook/docs/entropy_core_and_gensyn_reference_policy.md
  - repo://Entropy_Protocol/docs/ENTROPY_CORE_AND_GENSYN_REFERENCES.md
  - repo://Entropy_Protocol/products/signal-analytics-sandbox/docs/tasks.md#SAS-TTI-002
```

## Gensyn-Inspired Pattern

Allowed adaptation:

```text
summary lens + source-trust lens + project-relevance lens -> referee verdict -> brief
```

Not adopted: decentralized training, token incentives, on-chain coordination,
P2P swarm runtime, or model weight updates.
