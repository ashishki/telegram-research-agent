# UTD-1 Focused Safety Review

Date: 2026-08-28
Scope: UTD-1 profile/watch UX and isolated OpenAI provider boundary
Review type: immediate focused review required by `docs/REVIEW_POLICY.md`; **not** UTD-DR-1.

## Scope reviewed

- one-bot routing in the existing PRM Telegram runtime;
- confirmation-gated UTD profile draft and watch preview;
- programme, career, AI, ISSO, benefits and spouse/family scope;
- `America/Chicago`, cadence, daily cap, expiry, pause and source mute;
- synthetic public UX fixtures for deadline, benefit, spouse event, career event and AI research;
- default-deny OpenAI adapter using `gpt-5.6-terra` only behind explicit provider egress and separate context-egress gates.

## Safety findings

1. **No executable watch was introduced.** Confirmed `watch_topic` metadata sets `monitoring_authorized=false`, `delivery_authorized=false`, `provider_egress_authorized=false`, and `source_status=preview_only`. There is no collector, timer, service, source fetch or Telegram notification path in UTD-1.
2. **Exact confirmation remains the durable-write boundary.** Draft/onboarding callbacks write only to the existing expiring proposal store. Canonical profile intent is appended through the existing `confirm_memory_proposal` path only after the dedicated confirmation callback.
3. **One-bot coherence is preserved.** Natural UTD questions fail closed to a UTD preview; explicit archive wording still enters the existing PRM archive path. No second bot or report timer was created.
4. **Family eligibility fails closed.** The preview explicitly requires stated spouse/family eligibility and forbids inference from generic student eligibility.
5. **Draft retention was tightened during review.** Cancelled and expired UTD draft payloads are scrubbed from `prm_post_answer_proposals`. A confirmed proposal remains in that already-bounded store only until its existing 30-minute expiry so exact confirmation replay remains idempotent; the canonical confirmed event is append-only memory.
6. **Provider egress is default-deny.** Local PRM remains the default. OpenAI calls require both the feature flag and per-call provider approval; archive context additionally requires an independent environment flag and per-call context approval. The adapter is not wired into UTD runtime execution.

## Verification evidence

Before the final retention correction, the focused UTD suite passed locally (`19 passed`) covering profile preview/confirmation, expiry, pause/mute, spouse/family behavior, one-bot dispatch/callbacks, five UX fixtures and provider egress. The retention correction is narrow and adds explicit scrub assertions; final repository CI is the authoritative post-commit verification.

No full-suite run was used. No live UTD source request, timer, Telegram delivery, dogfood run, production DB migration, external web job or provider call was performed by this implementation/review.

## Remaining gates

- UTD-2 real sanitized source-contract evidence remains human/operator work.
- UTD-3 operator labels/relevance policy remains human/operator work.
- UTD-DR-1 remains planned and must run only after UTD-1, UTD-2 and UTD-3 are complete, before UTD-4.
- UTD-4 live shadow collection remains blocked pending the required evidence, deep review and explicit operator approval.
