# PA-02 — capability policy and egress boundary

Status: local, synthetic implementation only. The policy is default-deny and
does not enable a provider, obtain consent, create a grant, start a service, or
change a production database.

## Decision model

`prm.capabilities` provides a small in-memory registry. Its `CapabilityGrant`
is bound to the owner, optional connection, exact capability, explicit resource
references, operation, data class, purpose, provider policy, validity window,
revision and revocation. `AuthorizationRequest` contains only that metadata:
never prompts, source text, payloads, keys, tokens, account IDs, or provider
responses. A missing grant is a denial.

`CapabilityRegistry.authorize()` is a read-only preflight for UI/planning.
`authorize_and_reserve()` rechecks the current grant and reserves one budgeted
adapter operation. The returned reservation is consumed exactly once by the
adapter immediately before its external request. A revoked, expired, future,
wrong-owner/resource/operation/data-class/purpose/provider/revision or
fallback-forbidden request is denied. A reservation remains spent after an
adapter error or unknown outcome, so a retry needs explicit reconciliation and
another valid budgeted decision; it cannot silently duplicate an effect.

The only implemented budget is the grant's bounded request count. PA-16 owns
measured monetary/model routing budgets, and PA-13 owns durable external action
reconciliation. This slice never represents either as complete.

## Adapter application

| Boundary | Required grant before a request | Additional non-authority switches |
| --- | --- | --- |
| Anthropic text/vision client | exact `model.generate`/`model.vision`, `provider_anthropic`, declared data class, one-use reservation | none; a configured API key is insufficient |
| OpenAI text adapter | `model.generate`, `provider_openai`, `user_provided`, one-use reservation | existing adapter enable plus per-call switch still restrict execution but never authorize it |
| OpenAI archive context | a distinct `model.context_egress`, `provider_openai`, `private_archive` reservation | existing context switch; absent/invalid context grant omits context rather than leaking it |
| Telegram voice download | `media.voice_download`, `read`, `provider_telegram`, `user_provided` reservation | none |
| OpenAI transcription | `media.transcribe`, `model_egress`, `provider_openai`, `user_provided` reservation | API key supplies transport credentials only |

The public scope description lists capability, resources, operations, data
classes and permitted providers and explicitly says that a provider key is not
consent. It deliberately does not expose credential values or raw source data.

## Verification floor

The PA-02 tests prove no-consent/key-only denial before fake client/network use;
scope/provider/revision/revoke/expiry/fallback failure; a one-use budget
reservation; archive-context separation; and both Telegram download and model
transcription denial before network. Existing LLM, OpenAI adapter, synthesis and
voice tests now pass a matching synthetic authorization only for their fake
transport paths. No fixture calls a provider.
