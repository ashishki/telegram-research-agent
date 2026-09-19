# PA-03 conversation evidence — 2026-09-19

Status: locally verified, synthetic/offline implementation of the PA-03
conversation boundary. This evidence does **not** change the design's
mechanical `review_required` state, create a durable retention policy, grant a
provider/account, enable a job, or claim production, owner-usefulness or
release acceptance.

## Implemented boundary

- `ConversationState` is a bounded in-memory state keyed by an opaque hashed
  conversation reference. It carries visible response object references,
  bounded message references, an explicit `current_confirmation_ref`, pending
  request IDs and a 20-minute expiry. There is no DB migration or raw-dialogue
  retention: a process restart clears this state by design.
- A plain `yes`/`да` resolves only one visible, unexpired confirmation whose
  response ref, proposal ref/version and chat/actor/owner hashes exactly match.
  The caller must supply the current authoritative proposal version; without
  PA-13's loader, the active path fails closed and neither reroutes nor
  executes. New topic, cancellation, expiry, missing identity, changed version,
  restart and malformed multiple-preview state all deny selection.
- “Shorten” and “second item” are object-bound controls: without a visible
  response/list they are ordinary new-topic text. A selected shortening is
  local and never re-egresses a prior model answer. Every ordinary new topic
  clears response objects and confirmation state before routing.
- General conversation now routes to explicit `chat`, rather than silently to
  archive retrieval. Authorized chat accepts only a reserved PA-02 model
  decision and sends just the current direct user text to the established model
  adapter. Prior messages, response objects, topic summaries and confirmations
  are deliberately omitted from provider context. Absent grant, model failure
  and unknown provider outcome are distinct truthful states; usage recording is
  suppressed and no durable cost telemetry is created.
- The application exposes `cancel(request_id)` over globally generated opaque
  in-flight request IDs. Cancellation clears confirmation authority, prevents a
  post-boundary model result from being rendered and makes no write. `/new` and
  `/cancel` use that local state and do not invoke archive retrieval or a model.

PA-13 remains responsible for an actual provider-write confirmation/execution
and reconciliation path. PA-04 remains responsible for bounded,
provenance-selected private archive context; PA-03 never sends that context to
a model.

## Verification

All tests below ran in the writable implementation environment on Python
3.10.12 with synthetic IDs/content only. No provider, Telegram polling,
production DB, live job, credential or account was accessed.

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_conversation.py tests/test_prm_application.py \
  tests/test_prm_utd_dispatch.py tests/test_prm_intent_archive_contract.py
# 60 passed in 2.52s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 338 passed in 68.65s (0:01:08)

python3 -m py_compile src/prm/conversation.py src/prm/application.py \
  src/prm/contracts.py src/prm/routing.py src/bot/prm_handlers.py
git diff --check
# passed; no output

python3 tools/check_personal_assistant_plan.py
# PA plan: 19 consistent slices; schemas, references, dependencies and context limits passed.
# Design state: review_required; no product, human-approval or runtime claim.

python3 tools/playbook.py --check-pin
# Playbook pin verified; no model, hook or application runtime enabled.
```

The targeted suite proves synthetic state transitions, topic/reset/cancel
boundaries, ambiguous/stale/expired/cross-actor plain-yes denials, model-context
omission and a synthetic authorized model seam. It does not prove an actual
provider response, delivery, mobile UX usefulness, durable restart retention,
provider-write execution, or external integration. The prohibited full
historical pytest suite was not run.

## Remaining gates and handoff

- Required independent Conversation/Test Critic review is pending for this
  scoped implementation; it is not replaced by these tests.
- Plain-language confirmation intentionally resolves no live action until
  PA-13 supplies an authoritative proposal/version loader and execution
  reconciliation. Existing PA-00 callback controls remain separately bound.
- No active durable grant source exists, so active Telegram chat truthfully
  returns `provider_egress_required` until a separately authorized transport
  supplies a reserved decision.
- The two pre-existing untracked local files remain unstaged and untouched.

After independent review and any required scoped remediation, PA-04 is the
next dependency-ready slice: connect authorized, source-bound archive synthesis
without widening PA-03's direct-user-text model boundary.
