# Product Spec

Status: proposed
Last updated: 2026-07-26

## Canonical Scope

The current active product spec is Personal Telegram Research Memory + Grounded
Assistant. The product is not yet implemented.

North star:

Search everything. Enrich what matters. Save what proves useful. Generate
reports only as a secondary projection.

## Primary User

One private operator who reads many Telegram channels about AI, engineering,
product, business, markets, and career development and wants to use that corpus
for practical work and life questions.

## Primary Outcome

The operator asks a natural-language question and receives:

- a concise answer;
- relevant context from the retained Telegram archive;
- concrete Telegram source links;
- grouped cases, tools, claims, approaches, and contradictions;
- freshness and date boundaries;
- a distinction between archive evidence and model background knowledge;
- insufficient_evidence when the corpus is weak;
- optional external verification when the question is unstable or high stakes;
- confirmation-gated options to save a Knowledge Note, Watch Topic, project
  link, decision, action, experiment, or feedback.

## Required Workflows

- Exact search for a remembered post.
- Concept search over a recent time window.
- Case search across multiple posts.
- Comparison of approaches.
- Project application.
- News and timeline questions.
- Reaction recall.
- Life and career context.
- Explicit no-answer.
- External verification with separated evidence classes.

## Non-Goals

- Public SaaS or multi-user architecture.
- Generic cross-domain personal memory platform.
- Full archive LLM enrichment backfill.
- Vector backend before FTS baseline evaluation.
- Raw Telegram corpus dump to an LLM provider.
- Automatic profile changes from reactions.
- Automatic durable memory from chat transcript.
- Weekly reports as the source of truth.

## Legacy Spec Status

Previous report-centered specifications remain historical context. The active
contract lives in docs/IMPLEMENTATION_CONTRACT.md and the product details live
in docs/personal_research_memory_product_contract.md.
