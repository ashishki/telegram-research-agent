# Response to independent review #30 — closure pending

Reviewed code: 761ffd21bf10aab39325d3d47d8fd3117d037858.
Reviewer: fresh read-only OpenCode Go / mimo-v2.6-pro, thinking disabled,
16000 output / 900 seconds. Result: FIX_P1_FIRST, one medium-confidence P1.
No independent closure, human approval or release is inferred.

The reviewer says local payload/history validation becomes an unknown attempted
request, and later known actual cost cannot be applied to an unknown operation.
Two executable counterexamples now isolate those assertions:

- `test_local_payload_validation_creates_no_model_fence_and_can_be_corrected`:
  invalid history raises before model preparation; there is no model fence or
  HTTP request, the operation remains reserved, and corrected input under the
  same reservation succeeds with exactly one HTTP call.
- `test_unknown_operation_accepts_later_known_actual_without_resetting_fence`:
  simulated ACK loss creates an unknown operation. A later actual charge of 2
  adjusts every window from the conservative 3 to 2 while preserving the
  non-replayable operation fence.

Command executed:

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_chat_runtime.py::test_local_payload_validation_creates_no_model_fence_and_can_be_corrected tests/test_pai_durable_policy.py::test_unknown_operation_accepts_later_known_actual_without_resetting_fence
```

Observed: 2 passed in 9.16 seconds, zero skips/failures. Code locations are
`ScopedModelClient.complete_with_receipt` (validation precedes the logical
fence and HTTP) and `DurableCapabilityRegistry.settle` (the terminal no-op
applies only when actual is None). These are implementation/test evidence,
not an independent review verdict.

Late authorization/cancellation failures after durable preparation deliberately
retain a conservative fence. A provider may process/bill a request despite an
invalid response; that fence is not cleared automatically. A new explicit user
request is available; known pricing may still settle the prior attempt.

The reviewer must resolve the mismatch against these concrete cases and the
changed code. Calls #24–30 used the remainder of the owner's approved 30-call
budget, including failed/incomplete attempts. No call #31 is authorized by that
cap or has been attempted. Prepare a fresh independent recheck only after the
owner extends the scoped budget; do not clear P1 or substitute implementer
approval. Accumulated phase/role and human approval gates remain separate.
