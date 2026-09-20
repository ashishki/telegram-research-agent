# PA-09 — local durable-watch evidence

Date: 2026-09-20  
Implementation range: `788414f..289269d` (local PA-09 code); handoff/evidence
is recorded in the following documentation commit.  
Boundary: explicit local SQLite paths and synthetic fixtures only. No service,
timer, provider, Telegram account, credential, migration, delivery, deployment
or runtime acceptance was enabled.

## Implemented local contract

- `src/prm/watch_jobs.py` provides owner-bound expiring subscription
  preview/confirmation, including every consent-bearing revision; direct
  pause/unsubscribe is limited to an exact authenticated feedback receipt.
- Durable jobs use an idempotency key derived from canonical event identity,
  prior stage baseline and material evidence fingerprint. Version churn is
  ignored; a genuine A→B→A reversal is retained as a new transition.
- Source deadline instant/timezone are explicit for deadline notifications.
  `recalculate_deadline_reminders` atomically derives 14d/7d/1d/due stages,
  supersedes obsolete queued work and rolls all work back on a policy failure.
- Claim leases, durable pre-send attempt records, final policy/grant/quota
  checks, receipts and unknown-send state are separate. A restart after sender
  start remains unknown until an injected adapter-owned verifier returns a
  typed attestation bound to owner, destination, PA-02 operation and attempt.
  The default is deny; there is no automatic retry.
- Watch collection and delivery retain distinct PA-02 purpose mappings.
  The one-shot runner has only injected callbacks and never installs a timer.

Changed implementation/test files:

- `src/prm/watch_jobs.py`
- `src/prm/capabilities.py`
- `tools/test_tiers.py`
- `tests/test_assistant_jobs.py`
- `tests/test_assistant_subscriptions.py`

## Verification

Commands run from the repository root:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_jobs.py tests/test_assistant_subscriptions.py \
  tests/test_assistant_permissions.py tests/test_assistant_grant_codec.py \
  tests/test_assistant_egress.py tests/test_external_watch_subscription.py \
  tests/test_external_watch_delivery.py
# 141 passed in 17.58s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 470 passed in 93.81s

python3 -m py_compile src/prm/watch_jobs.py
git diff --check
```

The focused tier includes both dedicated PA-09 suites. The tests use temporary
SQLite databases, synthetic identifiers and injected callbacks; they are not
provider, Telegram, scheduler or owner-use evidence.

## Independent review record

All governed reviews used the pinned `tools/run_codex_role.py run` in a fresh,
read-only sandbox, requested and observed as `gpt-5.6-terra` with `high`
reasoning. Each Role Runner result records `workspace_unchanged: true`.

| Reviewed SHA | Run ID | Result | Local disposition |
| --- | --- | --- | --- |
| `161ecd6` | `20260920Tpa09-slice-161ecd6` | STOP_SHIP | Grant/background and runner P1s fixed. |
| `9843e8d` | `20260920Tpa09-recheck-9843e8d` | STOP_SHIP | Private control and scope P1s fixed. |
| `b17b7d6` | `20260920Tpa09-final-b17b7d6` | STOP_SHIP | Exact confirmation/reconciliation P1s fixed. |
| `8db7f55` | `20260920Tpa09-post-confirm-8db7f55` | STOP_SHIP | Revision confirmation and bound reconciliation P1s fixed. |
| `a113739` | `20260920Tpa09-final-a113739` | STOP_SHIP | Durable restart reconciliation P1 fixed. |
| `730729a` | `20260920Tpa09-restart-730729a` | STOP_SHIP | Attested reconciliation/receipt P1s fixed. |
| `937e41d` | `20260920Tpa09-attested-937e41d` | STOP_SHIP | Evidence-baseline P1 fixed. |
| `8699aa2` | `20260920Tpa09-evidence-8699aa2` | STOP_SHIP | Feedback idempotency advisory fixed. |
| `e0948bc` | `20260920Tpa09-feedback-e0948bc` | STOP_SHIP | Source-bound deadline recalculation P1 fixed. |
| `289269d` | `20260920Tpa09-deadline-289269d` | STOP_SHIP | No remaining local code P1; runtime/observable-delivery gates remain open. |

The fresh read-only Test Critic was separately requested as
`gpt-5.6-terra`/`high` for `8db7f55`; its STOP_SHIP findings drove the
double-send, final-policy, DST and reconciliation corrections above. Its report
is `docs/verification/PA-09-test-critic-8db7f55.md`.

## Remaining gates and next command

The final slice review remains STOP_SHIP because PA-09 declares runtime
verification required, while this owner-authorized local slice expressly
forbids the required authenticated collection adapter, Telegram transport,
service/timer and real provider exercise. This is not a failed local test and
does not authorize enabling any of them. No human design approval, runtime
acceptance, release or claim that watches arrive reliably is made here.

After separately authorized runtime integration exists, the next command is:

```text
python3 tools/run_codex_role.py run --root . --task PA-09 --feature-id PA \
  --slice-id PA-09 --role slice_review --model gpt-5.6-terra \
  --reasoning-effort high
```
