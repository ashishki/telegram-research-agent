# Response to independent review #33 — one final recheck needed

Reviewed source: f28f51fd0c3072836e41163b3f67d57fefc8c08d.
Receipt: PAI-review-continuation-33.json. Valid FIX_P1_FIRST, one P1 / one P2;
requested/observed OpenCode Go / mimo-v2.6-pro, thinking disabled, 16000 output
/ 900 s. Scope includes declared excerpts, not a whole-program/role receipt.

The reviewer independently resolves #31's non-retryable error-boundary P1 and
vision-body bound P2. Its summary says the two #32 P0 allegations do not hold
against the supplied fixed code, and notes the current fixes for other #32
items. None of this grants design, live, governed role or human acceptance.
The new findings below remain open until a fresh independent recheck.

## P1: accepted response with unconfirmed accounting

`execute_fenced_media` now distinguishes a known accepted result from an
indeterminate transport. If accounting fails after the registry returned
successfully, it raises `MediaAccountingUnconfirmed`, with the accepted
receipt, exact validated result, attempt/operation refs, and retry_allowed=False.
The receipt says delivery_outcome=accepted and usage_recorded=False; price
remains None and no token measurements are invented. Ordinary exception text
contains no transcript/image answer. The durable fence and conservative ledger
remain intact; reconstruction under the same logical task cannot issue HTTP.

The actual MediaRuntime voice/image paths consume that accepted result and
return transcription/answer plus accounting_status=unconfirmed. The accepted
transcript is durably stored and temporary image input is cleaned. A cost
failure does not discard the valid answer or turn it into an unknown transport.
Provider rejection/malformed-response errors retain their distinct non-retryable
reason; their accounting failures still cannot mask the original error.

## P2: post-invocation compound denial needs a fence-bearing error

`execute_reserved_groups` now raises `ScopeTransportUnknown` with prepared
operation refs and retry_allowed=False after invocation started. Partial
preparation still uses the separate ScopePreparationUnknown path. The new
actual denial test verifies one invocation, unknown terminal operations,
conservative spend retained, and denial of reservations for the same refs.

## Exact verification and preserved failures

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_media_runtime.py tests/test_test_tiers.py
```

Initial exit 1: 1 failed / 13 passed in 50.03 s. Existing tier metadata tests
still expected the historical five tiers and removed archive/pi-chat selectors,
while the current implementation already declares eight and the active PRM
floor. Expectations now assert the exact eight tiers, active archive/application/
conversation coverage, historical pi-chat exclusion, strict PAI matrix enforcement
and registration of the new recovery cases. The full historical tier remains
prohibited. No old historical product suite was restored or run.

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_media_runtime.py tests/test_pai_durable_policy.py tests/test_pai_chat_runtime.py tests/test_test_tiers.py
```

First integration run: exit 1, 1 failed / 13 passed in 82.68 s. The supplied
one-pixel PNG fixture had invalid data and the restricted extractor correctly
rejected it. The fixture now constructs a valid deterministic PNG with proper
chunk CRCs; no parser/boundary was weakened or mocked to bypass the failure.

Corrected final run: exit 0, 38 passed in 145.07 s, zero skips/failures. It covers
actual loopback HTTP accepted responses/ACK loss, accepted accounting failure
through both actual media paths, durable transcript storage/input cleanup,
non-replay across new clients/assets, compound denial/preparation, settlement,
chat scope/history, and exact verifier registration. The command
`.venv-pai/bin/python tools/test_tiers.py pai-complete --print-only` exited 0
and includes `tests/test_pai_review_recovery.py` under --require-spec-matrix.
The earlier whole-tier pass remains its own exact-SHA observation; it has not
been repeated or projected onto this changed source.

Changed source: `src/prm/runtime/model_errors.py`, `media_attempts.py`, `media.py`,
`src/prm/storage/policy.py`. Tests: `tests/test_pai_media_runtime.py`,
`tests/test_pai_durable_policy.py`, `tests/test_test_tiers.py`. Verifier:
`tools/test_tiers.py` includes the new recovery suite. Any applicable tooling
audit/hash gate must still be honored; an advisory source verdict is not that
governed audit. Review/handoff/packet documentation changes are separate.

All 33 approved paid calls are consumed, including failed/inconsistent ones.
Concrete hash-bound packet #34 is prepared and uninvoked: a single fresh
read-only actual-finding recheck of this code/tests, same provider/model,
16000 output / 900 s, no private corpus/account data/secrets. It requires an
explicit 33-to-34 budget extension. No automatic retry or model swap is
authorized. Original formal/human/live gates remain separate and unfilled.
