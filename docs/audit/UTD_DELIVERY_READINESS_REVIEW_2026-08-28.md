# UTD delivery readiness review — 2026-08-28

Status: **not approved for live delivery or dogfood**

## Scope and evidence

This read-only review covered the active `origin/master` UTD implementation,
the approved bounded-shadow receipt, delivery/feedback code paths and focused
UTD/PRM tests. No source polling, timer enablement, Telegram send, provider
call, production database access or profile mutation was performed.

The bounded probe evidence remains technical-only: 102 source items, 32
relevant changes, five capped candidates and zero changes on the repeated poll.
It does not supply human usefulness labels, precision/recall, or authorization
to notify.

## Corrected findings

1. **P0 — digest and daily-cap contract was not enforced across runs.**
   Non-urgent candidates were sent as separate messages and the cap applied to
   only one invocation. Delivery now sends one ordinary daily digest, keeps
   source-supported urgent changes separate, and counts delivered candidate
   items in `America/Chicago` across all runs. Every digest component has its
   own receipt so a later digest with a different composition cannot repeat it.
2. **P0 — collection and feedback could use different default sidecars.**
   The shadow CLI, systemd template and Telegram callback now share the
   gitignored `data/utd_shadow.db` default, while an explicit
   `UTD_WATCH_SIDECAR_DB` still overrides it.

## Remaining live gates

- UTD-5 still needs independent human labels and the stated quality thresholds;
  model-authored policy outcomes and the one-shot shadow probe do not qualify.
- UTD-DR-2 and explicit operator delivery approval are required before enabling
  a timer, `UTD_WATCH_DELIVERY_ENABLED`, or `--enable-delivery`.
- UTD-7 needs real controlled-delivery feedback before any relevance-weight
  change is considered. Feedback remains proposal-only and cannot mutate the
  confirmed profile.
- This review is not a PRM-19 dogfood-start approval or a release claim.

## Verification

- `PYTHONPATH=src python3 -m pytest tests/test_external_watch_delivery.py tests/test_prm_utd_callbacks.py tests/test_external_watch_selection.py tests/test_external_watch_shadow.py tests/test_external_watch_relevance.py -q` — 20 passed.
- `python3 tools/test_tiers.py focused-prm` — permitted active-tier check.
- `python3 tools/test_tiers.py retrofit-boundaries` — permitted structural check.
- `python3 tools/playbook_validate.py --root . --check tasks --check references`
  and `git diff --check` — required before commit.
