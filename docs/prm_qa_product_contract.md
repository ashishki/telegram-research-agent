# PRM-QA Product Contract

Status: active
Date: 2026-08-15

The product target is Personal Telegram Research Memory + Grounded Professional
Assistant:

```text
ordinary Telegram text or voice
-> deterministic task routing
-> job-specific retrieval policy
-> evidence quality assessment
-> claim ledger
-> grounded answer contract
-> concise Telegram rendering
-> usefulness feedback
-> confirmation-gated save/watch/action/experiment
```

## Supported Jobs

1. Find a known post.
2. Search a concept semantically.
3. Find practical cases.
4. Compare approaches.
5. Explain changes over time.
6. Apply evidence to a named project.
7. Prepare an editor brief.
8. Explain a difficult concept and suggest an experiment.
9. Recall reacted material.
10. Recall confirmed saved knowledge.
11. Refuse unsupported current facts.
12. Optionally verify a current claim through approved primary sources.

## Honesty Rules

- Generated/silver evals are regression evidence, not user-value proof.
- Source count is not source independence.
- Telegram repeats are not independent corroboration by default.
- Current facts require explicit primary-source verification.
- Project actions require explicit project identity and direct evidence.
- Durable saves, watches, links, actions, experiments, and decisions remain
  confirmation-gated.
- API embedding egress is allowed only for approved bounded sidecar/eval or
  explicitly approved runtime scopes; public artifacts still exclude raw
  private text, source URLs, prompts, completions, and provider payloads.
