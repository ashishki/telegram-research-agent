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

After the independent review remediation, the changed conversation/ingress
surface was rerun before its scoped fix commit:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_conversation.py tests/test_prm_application.py \
  tests/test_prm_utd_dispatch.py tests/test_prm_bot_dispatch.py \
  tests/test_prm_intent_archive_contract.py tests/test_callbacks.py
# 91 passed in 25.16s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 341 passed in 123.06s (0:02:03)
```

The targeted suite proves synthetic state transitions, topic/reset/cancel
boundaries, ambiguous/stale/expired/cross-actor plain-yes denials, model-context
omission and a synthetic authorized model seam. It does not prove an actual
provider response, delivery, mobile UX usefulness, durable restart retention,
provider-write execution, or external integration. The prohibited full
historical pytest suite was not run.

## Independent review and remediation

The required fresh read-only Role Runner `slice_review` examined initial PA-03
commit `d6e537babae040251cef9700a122c26b20d156ef` and returned `STOP_SHIP`.
The requested and observed runner telemetry was `gpt-5.6-terra` / `high`;
the validated result also records the Codex CLI version, read-only sandbox and
unchanged reviewer workspace. The local report SHA-256 is
`6138023f105329d78a19059f24b4d957d3feee0f1346f03e326daada478d3983` at
`.playbook-artifacts/runs/20260919T021550Z-slice_review-896b68cc/report.md`.
It is reviewer evidence, not approval.

The P1 remediation does all of the following:

- removes active `dispatch_prm_command` reads/writes of legacy
  `_PRM_DIALOG_STATE`; a bounded archive refinement now requires a visible
  `ConversationState` response, while legacy helpers remain inactive
  compatibility-only code;
- adds `ModelEgressAccess`, which preserves an actual typed PA-02 sealed
  reservation and its exact owner/connection/resource into the explicit bot
  ingress. `run_bot` accepts only an optional injected per-turn provider and
  still mints no grant or credential; omitted/malformed access stays deny; and
- requires `ConfirmationRef` hashes to all be identical and independently
  requires a canonical equal positive private chat/actor/owner tuple at plain
  yes resolution. Group/mismatch fixtures now reject before a proposal can be
  selected.

A fresh independent Terra/high recheck of this changed scope is still required
after the remediation commit. No P0/P1 finding is considered closed merely by
this implementer-run test result.

## Remaining gates and handoff

- Required independent Conversation/Test Critic recheck is pending for the
  scoped remediation; it is not replaced by these tests.
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
