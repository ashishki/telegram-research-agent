# Privacy Threat Model

Status: draft
Last updated: 2026-07-29

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
| unstable/high-stakes claim answered from stale Telegram evidence | deterministic external-verification requirement; Telegram evidence is discovery context only |
| local operator question leaks raw snippets to provider | `memory ask` is local-only: no LLM calls, no external search, no bounded snippet provider egress |
| chat transcript becomes memory silently | session context is not durable memory |
| hidden memory write from assistant tool loop | proposal plus exact confirmation token required; write trace records `write_performed` |
| read-only assistant turn mutates production DB telemetry | PI chat suppresses `llm_usage` database writes during planning/generation |
| autonomous workflow telemetry leaks raw private text | PRM-17 telemetry records aggregate metrics and redacted field names only |
| release or dogfood gate receipt leaks raw private text | PRM-18 receipt schema rejects raw payload keys and requires privacy flags to remain false |
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

## External Verification Rule

Pricing, legal, medical, financial, career-market, visa, freshness, news, and
explicit external-verification questions must produce a local verification
requirement unless approved external evidence is already available.

The PRM-11 assistant path does not call external sources. It records:

- Telegram/archive evidence as discovery context only;
- external evidence as `not_run_unapproved`;
- no automatic Telegram archive snippet collection for verification-only routes;
- `external_skill_used=false`;
- no stored research note until human confirmation.

## Confirmation Rule

No saved Knowledge Note, Watch Topic, project link, decision, experiment,
preference, profile/config edit, or external side effect is durable without
explicit human confirmation.

PRM-12 confirmation semantics:

- proposal tools are read-only and return `persisted=false`;
- `confirm_save_proposal` is the only confirmed memory-write tool;
- confirmation requires the exact proposal object and confirmation token;
- confirmed memory writes require the migrated canonical `personal_memory_events`
  schema and do not create tables lazily;
- confirmed memory writes append events to `personal_memory_events`;
- replaying the same proposal/token returns the existing event without a new
  write;
- edit, delete, and rollback confirmations validate their targets before
  writing;
- edit, delete, and rollback are represented as new audit events, not
  destructive updates to prior events;
- ordinary chat text and voice transcripts are not durable memory.

## Release Gate Receipt Rule

PRM-18 release receipts are privacy-safe evidence indexes. They may cite local
docs, tests, and sanitized eval receipts, but must not include Telegram raw
text, provider payloads, prompts, completions, generated private reports, or
production database mutations.

The current implementation enforces this in `evals/prm_release_gate.py` by:

- rejecting forbidden raw payload keys such as `raw_post_text`,
  `telegram_text`, `provider_payload`, `prompt`, and `completion`;
- requiring every committed receipt to keep raw egress, external skill use,
  provider payload logging, production DB mutation, and private report commit
  flags set to `false`;
- keeping `dogfood_started=false` and `release_claimed=false` for PRM-18.

The committed PRM-18 receipt,
`evals/prm18_release_gate_receipt_2026-07-29.json`, blocks dogfood start until
explicit human approval and accepted or cleared stop-ship criteria exist.
