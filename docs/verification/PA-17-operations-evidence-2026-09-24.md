# PA-17 — operations, recovery and security (local evidence)

Date: 2026-09-24
Boundary: local contracts only. No service start, timer, network call,
database migration, restore or deployment is performed.

## Implemented

`src/prm/operations.py`:

- `HealthSnapshot` / `ComponentSignal`: honest overall state
  (`healthy|degraded|down|unknown`); unknown stays unknown and the snapshot
  exposes only component names, states and opaque refs.
- `FailurePolicy` + `policy_for`: explicit, typed outcomes for `rate_limited`
  (retry with backoff), `provider_outage` (retry later, reconcile first),
  `disk_full` (no retry, blocks send, human required), `revoked_token` (no
  retry, re-consent/human), `duplicate_execution` (reuse receipt), `timeout`
  (reconcile, no retry) and `unknown` (fail closed).
- `plan_recovery`: never blindly retries — human-required failures abandon,
  unknown outcomes reconcile, retryable ones resume with backoff.
- `duplicate_outcome`: a duplicate execution returns the original receipt and
  never acts twice.
- `build_migration_rehearsal`: refuses the live path and any copy nested inside
  it; the plan requires a separate copy, verification, and an approval-gated
  swap.
- `require_deployment_approval`: production deployment is denied unless the
  exact approval ref is present.
- `secret_ref` stores only an opaque reference; `redact_text` masks API keys and
  bot tokens in logs/snapshots.

## Verification

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_ops.py
# 7 passed

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 576 passed
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py retrofit-boundaries
# 150 passed
```

The suite is registered in `focused-prm`.

## Remaining gates

Runtime verification remains: an actual worker restart, a real 429/outage, a
disk-full rehearsal, token revocation and duplicate execution on live workers,
plus a real migration/restore rehearsal on a copy with operator approval. This
slice is the local safety contract only and does not enable any production
operation.
