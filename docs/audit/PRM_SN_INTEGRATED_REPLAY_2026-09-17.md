# PRM-SN integrated local replay — 2026-09-17

Result: local implementation is ready for a **separate human pilot decision**.
This is fixture-only engineering evidence, not pilot evidence or runtime
authorization.

Code identity: base `cee8baae3b8a41f571bd689f2dadf7e6e981863f`; final accumulated
source/test diff `d0fecb9273c769a56c3ff081fe3b410eb7389b3c1f58933c5fde3300d7b0ce52`.
The deterministic scope inventory is
`PRM_SN_DR5_SCOPE_2026-09-17.json`; the final independent PASS is
`PRM_SN_DR5_2026-09-17.md`.

## Replayed local paths

| Path | Fixture evidence | Observed safe outcome |
| --- | --- | --- |
| Archive/current/mixed answer, citations, claim support | `test_prm_application.py`, `test_claim_ledger.py`, `test_primary_source_verification.py` | Useful archive evidence is retained; unsupported current claims are bounded and attributed rather than invented. |
| Follow-up, explicit save/confirmation, refresh visibility | `test_memory_research.py`, `test_prm_post_answer_actions.py`, `test_prm_refresh_receipt.py` | Context is typed/volatile; a specific item is only persisted after exact confirmation. |
| Request plan and controlled verification | `test_prm_request_plan.py`, `test_prm_utd_dispatch.py` | Archive/local path is default-off for outside verification; no fixture invokes a live provider or source fetch. |
| Topic events and on-demand edition | `test_external_watch_shadow.py`, `test_external_watch_selection.py`, `test_prm_application.py` | Reposts/corrections are ranked and rendered with allowed primary links; off-policy URLs are withheld. |
| Profile/lifecycle/schedule/delivery | `test_utd_profile.py`, `test_external_watch_profile.py`, `test_external_watch_subscription.py`, `test_external_watch_delivery.py`, `test_prm_utd_callbacks.py` | Exact profile confirmation, pause/unsubscribe, expiry, quiet hours, DST, cap, revision races, outbox leases, retries and unknown sends fail closed. |
| Telegram callback presentation | `test_callbacks.py` | RU/EN user-visible text, including English feedback toast and acknowledgement, follows the selected language path. |

## Commands and results

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  tests/test_external_watch_shadow.py tests/test_external_watch_delivery.py \
  tests/test_external_watch_profile.py tests/test_external_watch_subscription.py \
  tests/test_utd_profile.py tests/test_prm_utd_callbacks.py \
  tests/test_prm_application.py -q
84 passed in 4.71s

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  tests/test_claim_ledger.py tests/test_memory_research.py \
  tests/test_primary_source_verification.py tests/test_prm_post_answer_actions.py \
  tests/test_prm_refresh_receipt.py tests/test_prm_request_plan.py \
  tests/test_prm_utd_dispatch.py -q
86 passed in 16.80s

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  tests/test_callbacks.py tests/test_external_watch_delivery.py \
  tests/test_utd_profile.py tests/test_prm_utd_callbacks.py -q
72 passed in 20.36s

git diff --check
passed
```

The first and second commands cover distinct test-file sets (170 test outcomes);
the third is an after-fix regression replay for callback/lifecycle behavior.
All use fake transports/providers and disposable SQLite fixtures only.

## Non-authorizing pilot handoff

The reviewable [pilot/rollback packet](../PRM_SEARCH_NEWS_PILOT_PACKET.md)
contains the exact source hash, public allowlisted sources, one owner chat,
14-day duration, a maximum of five candidate units/day, one ordinary digest/day,
no paid-provider budget, required local preflight observations, stop conditions,
and a receipt-preserving rollback procedure. It expressly requires a separate
human decision before any runtime/service/profile/delivery change.

Not observed: human usefulness labels, real service/profile state, real source
coverage, provider cost/latency, Telegram delivery, reconciliation exercise,
pilot observations, release or rollout. Those remain outside this goal and are
not asserted by this replay.
