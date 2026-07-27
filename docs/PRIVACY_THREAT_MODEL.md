# Privacy Threat Model

Status: draft

## Assets

- Telegram raw post text and metadata;
- Telegram session file and API credentials;
- operator reactions and feedback;
- project context;
- saved notes, watch topics, decisions, and experiments;
- provider API keys;
- generated private reports.

## Threats

| Threat | Control |
| --- | --- |
| raw corpus sent to LLM | bounded retrieval context only; no corpus dumps |
| raw post text in logs | log IDs/counts/snippet hashes, not full text |
| generated private artifacts committed | `data/output/**` ignored; review diff before commit |
| embedding provider egress | explicit human approval and ADR before external embeddings |
| external skill reads private data | skills disabled until trust record and approval |
| chat transcript becomes memory silently | session context is not durable memory |
| source URL loses provenance | archive document identity preserves Telegram link |
| deletion cannot be honored | retention/deletion path required before dogfood |

## Provider Egress Rule

Telegram evidence sent to a model must be:

- bounded to retrieved snippets;
- necessary for the answer;
- cited;
- excluded from ordinary logs;
- covered by the cost/privacy budget.

Trace fields must distinguish this allowed bounded context from forbidden broad
corpus egress:

- `bounded_telegram_snippet_provider_egress=true` when cited snippets are sent
  to answer generation;
- `raw_telegram_corpus_egress=false` for all approved PRM assistant paths.

## Confirmation Rule

No saved Knowledge Note, Watch Topic, project link, decision, experiment,
preference, profile/config edit, or external side effect is durable without
explicit human confirmation.
