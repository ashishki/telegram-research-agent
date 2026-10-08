# Phase-B review #35 response — independent recheck pending

Reviewed source: 465503dc0545ddeb0eb2cb51dbf401c0cd3fb187. Fresh read-only
OpenCode Go / mimo-v2.6-pro, thinking disabled, 16000 output / 900 s.
Valid FIX_P1_FIRST: three P1 allegations. Original receipt and exact source
manifest: PAI-review-continuation-35.json. No independent closure inferred here.

1. **Revoked grant replacement:** a higher revision could overwrite revoked_at.
   Replacement now atomically requires the old document to be unrevoked.
   A revoked identity stays terminal; new explicit consent uses a new grant ID.
   The real PostgreSQL regression verifies both denial and new-ID authorization.
2. **Saved confirmation:** the omitted domain ActionConfirmation already validates
   fields on construction; execution already compares proposal/version/digest/
   actor and consumes exactly one attempt. Durable loading now additionally
   checks an integrity checksum of the complete confirmation metadata and binds
   the loaded value to the exact current proposal/owner and its original default
   TTL. Confirmation expiry is clamped to the proposal expiry. Expired/foreign/
   corrupted or mismatched saved approvals cannot be returned as fresh approvals
   or dispatched. Missing checksums fail closed and require a new preview; no
   existing approval is repaired automatically. This is an integrity checksum,
   not an authorization mechanism or defense against a fully privileged DB actor.
   The local undeployed schema needs no production migration in this pass.
3. **Compound preparation:** the suggested automatic reset/refund of prepared
   operations would violate the existing potentially processed-attempt boundary.
   A new executable no-HTTP case demonstrates that a later explicit actual=0
   settlement releases the conservative charge while preserving the unknown,
   non-replayable operation fence. No transport is permitted after the denied
   second scope. Thus the claimed irrecoverable charge/allow requires independent
   resolution against this counterexample, not implementer dismissal.

Command:

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_durable_policy.py tests/test_pai_durable_actions.py tests/test_pai_action_runtime.py tests/test_assistant_actions.py
```

Observed: exit 0, 32 passed in 45.90 s, zero skips/failures. Log is controlled
synthetic output in .playbook-artifacts/pai-validation-20261008/foundation-fixes.log.
Before these fixes, the complete registered tier ran on the unchanged 465503d
snapshot (runtime code 1b09d5a): 259 passed in 883.59 s, all strict matrix cases,
zero skips/failures. It is dated pre-fix evidence, not validation of later changes.

Changed source: src/prm/storage/policy.py and src/prm/storage/actions.py.
Tests: tests/test_pai_durable_policy.py and tests/test_pai_durable_actions.py.
Next is one fresh phase-B actual-finding recheck including previously omitted
complete src/prm/capabilities.py and src/prm/confirmed_actions.py. Current owner
authorizes necessary bounded review-budget increases; no new permission loop.
No live/product egress, production state, services or human approval was used.
