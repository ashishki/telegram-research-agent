# PA-13 — confirmed external actions (local evidence)

Date: 2026-09-24
Boundary: local, synthetic only. No OAuth, network call, token storage, default
database, scheduler, delivery or live account is enabled. Nothing is sent or
written outside the test process.

## Implemented

`src/prm/confirmed_actions.py`:

- `ActionProposal` for `mail.send`, `calendar.create`, `calendar.update`,
  `calendar.cancel` only. Dangerous out-of-scope codes (`coursework.submit`,
  `payment.send`, `course.register`, `grades.write`, …) are refused by
  construction. Content is validated per action (recipient addresses, subject,
  body, timezone-aware calendar times) and bounded.
- `confirm_action` binds a one-use confirmation to the exact proposal version
  and a canonical content digest, and requires the exact private owner and actor
  (`owner_ref == actor_ref`).
- `execute_action` re-checks the version/digest, requires a freshly reserved
  PA-02 `action.execute` write grant, and enforces one-use through a
  deterministic idempotency key derived from proposal/version/digest: a repeated
  click returns the stored receipt and never calls the provider again.
- `ExecutionOutcome` distinguishes `succeeded`, `failed_known` and `unknown`.
  An unknown outcome is recorded and **never retried** until
  `reconcile_action` resolves it against the provider.
- A changed proposal version/content, an expired confirmation, another actor or
  a revoked grant cannot reuse an old permission.

## Verification

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_actions.py
# 7 passed

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 549 passed
```

The suite is registered in `focused-prm` (and therefore `fast-contract`).

## Remaining gates

Runtime verification is required and not claimed: a real provider write, real
idempotency against the provider, live reconciliation of an ambiguous send, and
delivery receipts on a real account. This slice is the local safety contract
only; the Telegram assistant remains fail-closed for external writes.
