# Response to independent review #31 — recheck pending

Fresh read-only OpenCode Go / mimo-v2.6-pro reviewed source at e492ca6.
Requested/observed thinking disabled, 16000 output / 900 s. Result:
FIX_P1_FIRST (one new P1 and one P2). Receipt: PAI-review-continuation-31.json.
The reviewer independently found both allegations in review #30 contradicted
by the current implementation. That old finding is resolved in this scope;
the new media finding remains open until independent recheck.

The owner directed credential lookup to Georgia-Community-Navigator. Its
selected credential was read only for the explicitly authorized OpenCode Go
request. Observed provider model: mimo-v2.6-pro. No credential value, private
corpus or account payload is in the packet, report or repository.

## Concrete changes

- `media_attempts.py` wraps the durable media transport and accounting as one
  non-retryable boundary. ACK loss, final authorization/storage errors and
  accounting failure after an accepted response surface `MediaOutcomeUnknown`
  (an `LLMOutcomeUnknown`) with exact attempt/operation refs and HTTP-attempt
  metadata. The durable logical fence and conservative budget stay intact.
- Definitive rejections and malformed provider responses retain their existing
  distinct typed reasons and `retry_allowed=False`, now with fence refs. An
  accounting exception cannot replace those errors with a raw exception.
  They do not become known failure eligible for another automatic request.
- Speech and vision read at most the modality byte limit plus one, validate
  expiry, MIME/signature, exact size and digest, and reject changed/symlinked
  media before model preparation. Local failures abandon only an unprepared
  reservation. Vision explicitly bounds the encoded request to 6,800,000
  bytes, matching its 5,000,000-byte image limit plus bounded question/JSON.
  Nested usage metadata is validated before it reaches accounting.

## Observed verification

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_media_runtime.py
```

Exit 0: 12 passed in 56.23 s, zero skips/failures. Tests include actual synthetic
HTTP ACK loss, accounting failure after a response, fresh client/asset replay
under the same logical task, original provider reason despite failed accounting,
real file growth, and encoded-body rejection before any model fence or HTTP.

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_cost_cache.py tests/test_pai_chat_runtime.py::test_unknown_model_call_has_logical_fence_across_fresh_reservations tests/test_pai_chat_runtime.py::test_local_payload_validation_creates_no_model_fence_and_can_be_corrected tests/test_pai_durable_policy.py::test_unknown_operation_accepts_later_known_actual_without_resetting_fence tests/test_pai_durable_policy.py::test_unpriced_settlement_is_idempotent_and_terminal_state_is_monotone
```

Exit 0: 7 passed in 32.03 s, zero skips/failures. Existing whole-tier passes
remain observations at their original SHA; they have not been rerun or relabeled
as validation of this change. No actual media-provider or live-account call ran.

Changed source/tests: `src/prm/runtime/media_attempts.py`, `model_errors.py`,
`speech.py`, `vision.py`, `tests/pai_runtime_fixtures.py`, and
`tests/test_pai_media_runtime.py`. Review packets/progress/handoff are updated
separately. Scope review #32 covers connection/source code independently of
this media boundary. Call #33 is reserved for actual findings in #31/#32.
These advisory source reviews do not grant governed role receipts, exact human
design approval, live access, production/release, or programme completion.
