# Privacy Threat Model

Status: draft
Last updated: 2026-08-03

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
| LLM chat hides provider egress from the operator | PRM-18A..PRM-18C must require an explicit provider-egress switch and print privacy flags in every LLM-backed answer |
| chat transcript becomes memory silently | session context is not durable memory |
| hidden memory write from assistant tool loop | proposal plus exact confirmation token required; write trace records `write_performed` |
| read-only assistant turn mutates production DB telemetry | PI chat suppresses `llm_usage` database writes during planning/generation |
| autonomous workflow telemetry leaks raw private text | PRM-17 telemetry records aggregate metrics and redacted field names only |
| release or dogfood gate receipt leaks raw private text | PRM-18 receipt schema rejects raw payload keys and requires privacy flags to remain false |
| source URL loses provenance | archive document identity preserves Telegram link |
| linked-source cache leaks raw provider payloads or private post text | PRM-22 cache records store source URL, normalized title, content hash, bounded excerpt, status, and redacted failure reason only |
| linked-source resolver crawls live web by default | PRM-22 uses fixture/fake fetchers by default and refuses live HTTP, external skills, and provider summarization without explicit approval/budget switches |
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

The local `memory ask` command is the no-egress default. Planned LLM-backed
`memory chat` or `memory ask --llm-approved` modes must not send private archive
snippets to a provider unless the operator passes an explicit provider-egress
approval switch for that run.

## PRM-18A Chat Mode Split

| Mode | Command surface | Provider egress | Required user-visible line |
| --- | --- | --- | --- |
| Local evidence brief | `memory ask "<question>"` and `memory ask --json "<question>"` | none; model calls `0` | `mode=local-only`, `bounded_telegram_snippet_provider_egress=false`, `raw_telegram_corpus_egress=false`, `durable_writes=false` |
| LLM-backed one-shot | `memory ask --llm-approved --allow-provider-egress "<question>"` | bounded cited snippets only after explicit switch | `mode=llm-approved`, model calls/cost estimate, bounded-snippet egress flag, raw corpus egress false, durable writes false |
| LLM-backed interactive CLI | `memory chat --allow-provider-egress` | bounded cited snippets only after explicit switch | same as LLM-backed one-shot for every answer |
| Telegram PRM assistant | `/chat <question>` or ordinary text in `prm-assistant` mode | same LLM contract after PRM-18C and approved runtime start | same as LLM-backed CLI; service start remains separate approval |

The provider may receive only the retrieved snippets required for the cited
answer. It must not receive broad archive dumps, full database exports, uncited
raw Telegram corpus, provider payload logs, or durable chat transcript writes.
If the operator omits the egress switch, LLM-backed surfaces must remain
local-only or refuse before provider invocation.

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

## Linked Source Research Rule

PRM-22 implements linked-source extraction and cache receipts as a fixture-first
assistant layer. The default resolver may extract URLs from selected Telegram
evidence and classify article, docs, GitHub, paper, video, product, and unknown
source types, but it does not crawl live links by default.

Linked-source cache receipts may contain:

- source URL and normalized URL;
- source type;
- fetched-at timestamp from the fake or approved fetcher;
- normalized title;
- content hash and hash algorithm;
- bounded text excerpt;
- extraction status;
- redacted failure reason;
- Telegram evidence refs, not Telegram raw text.

They must not contain raw Telegram post text, raw provider payloads, prompts,
completions, secrets, or full failure payloads. Live HTTP fetches, external
skills, provider summarization, and durable cache writes over private
production inputs remain refused unless the operator records explicit approval,
budget, and any required trust record for that run.

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
