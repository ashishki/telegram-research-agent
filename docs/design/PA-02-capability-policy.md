# PA-02 — capability policy and egress boundary

Status: local, synthetic implementation only. The policy is default-deny and
does not enable a provider, obtain account/provider consent, start a service,
or change a production database. Its only runtime authority is a bounded,
non-persistent return envelope created from an already authenticated private
Telegram update; it is not a stored grant or connection consent record.

## Decision model

`prm.capabilities` provides a small in-memory registry. Its `CapabilityGrant`
is bound to the owner, optional connection, exact capability, explicit resource
references, operation, data class, purpose, provider policy, validity window,
revision and revocation. `AuthorizationRequest` contains only that metadata:
never prompts, source text, payloads, keys, tokens, account IDs, or provider
responses. An optional `operation_ref` is an opaque, caller-issued idempotency
key, never a prompt or payload. A missing grant is a denial.

`CapabilityRegistry.authorize()` is a read-only preflight for UI/planning.
`authorize_and_reserve()` rechecks the current grant and reserves one budgeted
adapter operation. The returned reservation retains its exact owner,
connection, resource, grant ID and revision, and the adapter rechecks all of
them against the registry immediately before it consumes the reservation and
makes a transport call. A revoked, expired, future,
wrong-owner/connection/resource/operation/data-class/purpose/provider/revision
or fallback-forbidden request is denied. A reservation remains spent after an
adapter error or unknown outcome. OpenAI model/context egress additionally
requires the same opaque `operation_ref` on its text and optional context
decisions. The in-memory registry holds that key as reserved, accepted or
unknown: a duplicate or unknown key is denied even when a grant budget exceeds
one. Only explicit `not_delivered` reconciliation can reopen an unknown key;
`delivered` leaves it blocked. Automatic client and SDK retries are disabled
for this boundary. PA-13 must supply durable reconciliation before a live path
can outlast this in-memory guard.

Adapter authorization is matched against the reservation's sealed original
request, including owner, connection, resource, capability, operation, data
class, provider, purpose, grant revision and operation ref. The duplicated
fields on a public `AuthorizationDecision` are diagnostic metadata only: a
copied or relabelled decision cannot change the request that reaches transport.
Every deny before a provider call permanently invalidates its exact reservation
before releasing only its in-memory operation-key hold; a later reservation for
the key cannot reactivate the stale one, and its conservative grant budget is
never refunded. Immediately before an OpenAI request, every reservation whose
data can enter that request is atomically committed as a group. A committed
reservation cannot be abandoned or release its key during an in-flight request;
only a wholly uncommitted group can be invalidated before transport.

The final adapter check obtains its expected purpose from the closed
`TRANSPORT_PURPOSES` table, not from a category or caller argument:
Anthropic/OpenAI query egress is `answer.request`; OpenAI private archive
context is `answer.context`; and both authorized Telegram voice reads and the
matching OpenAI transcription are `voice.transcription`. An unknown
provider/capability/operation tuple has no mapping and fails closed. This means
a syntactically valid reservation for one purpose cannot be repurposed by an
adapter transport for another purpose.

The only implemented budget is the grant's bounded request count. PA-02 does
not persist `llm_usage` or cost telemetry after a model call: model egress does
not imply an ungranted durable local write. PA-16 owns an explicit
cost/telemetry capability and measured routing budgets, and PA-13 owns durable
external-action reconciliation. This slice never represents either as
complete.

## Adapter application

| Boundary | Required grant before a request | Additional non-authority switches |
| --- | --- | --- |
| Anthropic text client | exact owner/resource plus `model.generate`, `provider_anthropic`, declared data class and one-use reservation; its non-null connection ref must equal the opaque SHA-256 derivative of the exact Anthropic credential loaded for the transport | none; a configured API key is insufficient and a caller-supplied connection label cannot authorize a different active credential |
| Direct local-path vision | denied before temporary storage, a file read or provider call; PA-15 must supply an immutable ingress-verified attachment binding before vision can egress | a configured API key or a `model.vision` reservation cannot bind arbitrary caller-selected bytes |
| OpenAI text adapter | exact owner/resource plus `model.generate`, `provider_openai`, `user_provided`, one-use reservation and opaque operation ref; its non-null connection ref must equal the opaque SHA-256 derivative of the exact OpenAI credential loaded for the transport | existing adapter enable plus per-call switch still restrict execution but never authorize it; a caller-supplied connection label cannot authorize a different active credential |
| OpenAI archive context | exact owner/archive resource plus a distinct `model.context_egress`, `provider_openai`, `private_archive` reservation bound to that same non-null active OpenAI credential ref and operation ref | existing context switch; absent/invalid context grant omits context rather than leaking it; a transport exception returns a non-durable receipt with an `unknown` delivery outcome and blocks that operation ref until reconciliation |
| Telegram voice download | exact owner/file resource plus two distinct `media.voice_download`, `read`, `provider_telegram`, `user_provided` reservations: one each for `getFile` and file download; connection ref must equal an opaque derivative of the exact bot token used | no token or derivative is logged, returned or published |
| OpenAI transcription | `media.transcribe`, `model_egress`, `provider_openai`, `user_provided` reservation, exactly bound to the Telegram attachment ID returned by the two authorized Telegram reads; connection ref must equal an opaque derivative of the exact OpenAI credential used | egress accepts only the fixed HTTPS `api.openai.com/v1/audio/transcriptions` endpoint; endpoint overrides, query/fragment variants and HTTP redirects are denied, and raw voice bytes remain in request memory only |
| PA-originated Telegram delivery | exact authenticated private owner/chat tuple plus an `assistant.result_delivery`, `deliver`, `provider_telegram`, `private_archive` reservation for every rendered Telegram chunk/message **and callback acknowledgement**; its connection ref must equal an opaque bounded SHA-256 derivative of the exact bot token used for that call | one shared sender/ack boundary covers PRM text/result, UTD/callback text, callback acknowledgement and PRM voice status. The active ingress may create at most eight in-memory, one-use decisions for a single equal private chat/actor/owner tuple, valid for two minutes and bound to the exact receiving bot token. It can only return that inbound turn's response to the same chat: it is not persisted, displayed as an active consent grant, usable for provider egress/read/background work/third-party delivery, or reusable after process loss. An omitted, expired, revoked or owner/resource/purpose/connection-mismatched decision suppresses the final send or acknowledgement; the token and its derivative are never logged, returned or published, and bot token/private chat are not consent |

PA-02 applies this boundary only to the explicit transports in the table:
Anthropic text, OpenAI text/context, Telegram voice `getFile`/file download,
OpenAI transcription, and PA-originated Telegram delivery. Telegram update
ingress, non-PRM handler sends and other pre-existing non-LLM HTTP paths are
ambient platform behavior, not evidence that PA-02 has granted or enforced
every external side effect. Their exact inventory and enforcement remain for
the bounded slices that own those paths; they must not inherit PA-02 completion
claims.

The active PA `/status`, `/refresh` and `/reactions` routes do not delegate to
their historical legacy handlers because those handlers have no PA-02 final-send
decision. They fail closed before that dispatch until an owning slice gives the
legacy operations a bounded capability/receipt contract. Similarly, PA `/utd`
must consume an exact `assistant.utd_draft` / `write` / `provider_local` /
`user_provided` / `utd.draft` decision bound to the authenticated private owner
and chat before it creates an onboarding draft. PA-02 supplies no runtime
source for that decision, so UTD onboarding fails closed before a local write.
All PA callback namespaces, including `prma:`, `prmc:`, `utdp:`, `utdc:`,
`utds:` and `utdw:`, likewise fail closed before callback validation, row load
or mutation; a later owning slice must design and check an exact
callback-specific authority immediately before each write. The private
`/privacy` renderer uses the return envelope only to display the empty
durable-grant registry; it does not create a durable grant or mistake the
envelope for account/provider consent. Without a matching current delivery
decision its actual Telegram send is suppressed. These are default-deny
boundaries, not claims that the deferred operations or a live permission UI
have been enabled.

The same envelope is not local persistence authority. PA-02 therefore creates
no active post-answer proposal context, interaction receipt or action keyboard:
an undeliverable, expired, revoked or mismatched return decision must not leave
an answer-derived durable record. PA-13 must introduce and enforce its own
exact local-write/confirmation authority before that action surface returns.

The public scope formatter lists capability, resources, operations, data
classes and permitted providers and explicitly says that a provider key is not
consent. It deliberately does not expose credential values or raw source data.
It is a contract helper only: PA-02 intentionally has no durable grant source
or live operator route, so this does not claim that an account-facing permission
screen has been delivered.

## Verification floor

The PA-02 tests prove no-consent/key-only denial before fake client/network use;
scope/provider/revision/revoke/expiry/fallback failure; current-state
revalidation after reservation; cross-owner/connection/resource substitution
and cross-purpose transport substitution denial; one-use budget accounting; no automatic retry after unknown provider
outcome even with a larger grant budget; archive-context separation; direct local-path vision denial before a
read/provider call; and all three real voice transport layers (`getFile`, file
download, transcription) with separate matching synthetic reservations. Voice
tests also prove raw download bytes never create a local staging file. Result
delivery tests prove a revoked/missing/mismatched decision reaches no fake
Telegram sender, including a reservation bound to another configured bot
connection. Synthetic private text, voice and callback ingress prove the
bounded return envelope reaches the final send/ack gate, while
group/mismatched identity ingress receives no envelope, send or callback
network acknowledgement; `/privacy` shows default deny without creating a
durable grant. Credential-A/credential-B and null-connection substitutions for
both text-model adapters reach no fake provider transport; valid, denied,
revoked and revision-stale model decisions leave the configured synthetic usage
database unchanged. Existing
LLM, OpenAI adapter, synthesis and voice tests now pass a matching synthetic
authorization only for their fake transport paths. No fixture calls a provider.
