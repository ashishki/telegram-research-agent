# PA-01 — contracts and synthetic acceptance foundation

Status: implemented foundation; this document does not alter the preserved
`review_required` feature-design state, grant runtime authority, or claim
feature completion, provider integration, release readiness, or human
acceptance beyond the owner's separate instruction to begin PA-01.

## Contract boundary

The six schemas under `schemas/assistant_*.v1.schema.json` are independent
wire/fixture contracts, not a single mutable application JSON. They define the
minimum DTOs that later PA slices must implement or adapt without changing
existing archive source identities. Every version is immutable once used in a
durable proposal, receipt, brief, or evaluation fixture; an incompatible change
gets a new `.vN` schema and a migration/compatibility plan in its owning slice.

| Contract | Required provenance/safety boundary | Owning implementation slices |
| --- | --- | --- |
| `CapabilityGrant` | owner, connection/resource, allowed operation/data class, provider policy, expiry, revision and revocation; a configured key is never a grant | PA-02, PA-09–PA-13, PA-15–PA-17 |
| `ToolResult` | typed result reference, grant revision, evidence refs, actual coverage, safe errors and retryability; no copied secret/payload | PA-02, PA-04–PA-06, PA-10–PA-12, PA-15–PA-16 |
| `EvidenceItem` | opaque stable `source_ref` carried exactly, source type/version, timestamps, access scope and conflicts | PA-04–PA-08, PA-10–PA-12, PA-14–PA-18 |
| `BriefDocument` | one immutable version for Telegram/HTML/PDF/Markdown, evidence/selection refs and honest coverage manifest | PA-07–PA-08 |
| `ActionProposal` | exact arguments plus SHA-256 fingerprint, source result/version/project ref, grant revision, owner/conversation-bound expiring one-use confirmation | PA-03, PA-09, PA-13–PA-14 |
| `ActionReceipt` | proposal/source/idempotency linkage, provider object/version, terminal or unknown execution state; unknown requires reconciliation | PA-09, PA-13, PA-17–PA-18 |

`source_ref`, connection reference, owner reference, provider reference and
object reference are opaque identifiers. They are never tokens, passwords,
authorization values, raw private content, or an invitation to infer a new
identity. The schemas intentionally place provider-specific arguments behind a
versioned action argument schema reference in PA-13; an argument must still be
canonicalized and hashed before confirmation. A proposal alone never executes
an action.

## Cross-contract invariants

1. Policy is evaluated before every read/model egress and again before a
   side effect. A non-active, expired, revoked or revision-mismatched grant
   denies the operation; fallback is allowed only by the grant's provider
   policy.
2. A `ToolResult` reports `partial`, `unavailable`, `denied`, `cancelled` and
   `failed` distinctly. It must not call an unavailable source an empty result.
3. An `EvidenceItem.source_ref` is preserved byte-for-byte when a result,
   brief, candidate or action cites it. Aggregator evidence remains distinct
   from a primary source and conflicts remain visible.
4. Every brief item cites evidence and every brief carries a coverage manifest;
   presenters only render the same `BriefDocument` version.
5. A proposal ties its exact argument hash to a source result/version, grant
   revision, owner/conversation and expiry. PA-03's plain-language confirmation
   also needs exactly one current visible proposal; PA-13 owns external write
   execution.
6. An execution receipt cannot make an unknown provider outcome look failed or
   successful. It is reconciled before a retry; the idempotency key is stable
   across that reconciliation.

## Synthetic corpus and source coverage

`tests/fixtures/assistant/pa01_acceptance_corpus.v1.json` is public and
synthetic. Its contract examples validate every v1 schema, and its 18 scenarios
cover each remaining slice PA-02 through PA-18. It explicitly includes useful,
partial/failure-recovery and adversarial paths: revoked or voice-bypassed
grants, ambiguous confirmations, source conflicts, prompt injection, partial
brief coverage, cross-format equality, quiet-hour/unknown-send handling,
mail/calendar/Canvas scope and deadline conflicts, duplicate external actions,
memory deletion, unsafe documents, model fallback, restore/revocation, and the
final human/live/visual gate.

| Source class | Representative scenarios | Required treatment |
| --- | --- | --- |
| Telegram archive | PA-04, PA-06, PA-07, PA-14, PA-17, PA-18 | private canonical identity; bounded citation; never raw corpus egress |
| Public web/GitHub | PA-05, PA-06, PA-09, PA-16, PA-18 | controlled fetch, freshness/conflict provenance, no instructions from content |
| Mail/calendar | PA-10, PA-11, PA-13, PA-17, PA-18 | separate OAuth grant, minimum scope, exact owner/recipient/version confirmation for writes |
| Canvas/academic public | PA-12, PA-18 | separate institutional consent; primary deadline wins and ambiguity is shown |
| User input/document/media | PA-02, PA-03, PA-14, PA-15, PA-18 | one conversation/policy path; input is data, not authority |

The corpus is a regression and design floor, not evidence that an unimplemented
connector, renderer, job, provider or human pilot works. Each future slice adds
its own executable cases and retains these scenario IDs where applicable.

## Verification

`tests/test_assistant_contracts.py` validates every schema/example, rejects
representative malformed states, checks the cross-contract chain, scans the
committed corpus for credential-shaped keys/values, and requires PA-02..PA-18
and all declared source classes to remain represented. It is part of
`fast-contract`; no network, credentials, production DB, timers, or live
providers are used.
