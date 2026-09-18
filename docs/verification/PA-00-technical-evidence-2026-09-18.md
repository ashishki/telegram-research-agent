# PA-00 technical evidence — 2026-09-18

Status: local technical verification complete; not a human high-risk slice
acceptance, runtime permission, release, or live-action claim.

## Authority and baseline

The operator gave exact design/start approval in this conversation after the
design candidate and the one requested independent Astra/xhigh review. The
Playbook approval recorder was also attempted, but correctly refused to write
an approval while the preserved design-review artifact remained STOP_SHIP. No
approval artifact or Playbook state was edited by hand. The operator's direct
instruction authorized PA-00 implementation; a separate human high-risk slice
acceptance is still required before PA-01.

The historical GitHub run `35328205490` (302 passed / 1 failed) remains
reference-only. The focused baseline at `fb5d5717e82e36d8d5ac0085746e5fa864fcc70a`
is recorded in [PA-00-baseline-2026-09-18.md](PA-00-baseline-2026-09-18.md):
the historical evaluator test passed locally, while static diagnosis found two
real safety defects—synthetic `eval-*` callback state in the evaluator and a
live free-text handler that synthesized an actor ID. The retained historical
test now exercises the safe denied-free-text branch; the separate declared
bound-inline evaluator fixture proves source-project provenance.

## Implemented scope

The implementation commits through code HEAD
`4b7fa59269c93701a00e92cddd8b3f9c0016ef0f` are:

- immutable `prm_post_answer_action_binding.v1` snapshot and exact private
  owner tuple;
- pure read-only PRM validation followed by fingerprinted CAS application,
  including issued dynamic controls and outer callback acknowledgement order;
- evaluator/live denial of legacy free-text actions without synthetic context;
- clean-schema UTD JSON state codec and guarded state transitions without a
  migration; and
- owner-restricted, `SELECT`-only PRM/UTD rollback drain.

No production database, Telegram ingestion, external provider, service, timer,
account, archive content, or `.env` was touched. The two pre-existing untracked
local files were preserved.

## Commands and results

Environment: Python `3.10.12`; `PYTHONPATH=src` and
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.

```text
python tools/check_personal_assistant_plan.py
# PA plan: 19 consistent slices; schemas, references, dependencies and context limits passed.

python -m pytest -q tests/test_playbook_bridge.py
# 12 passed in 1.50s

python -m pytest -q \
  tests/test_prm_product_ux_eval.py \
  tests/test_prm_post_answer_actions.py \
  tests/test_interaction_ledger.py \
  tests/test_utd_profile.py \
  tests/test_prm_utd_callbacks.py \
  tests/test_prm_utd_dispatch.py \
  tests/test_prm_bot_dispatch.py \
  tests/test_callbacks.py::TestIdeaCallbacks::test_run_bot_prm_safe_routes_only_post_answer_callbacks \
  tests/test_callbacks.py::TestIdeaCallbacks::test_handle_callback_validates_prm_before_acknowledgement \
  tests/test_callbacks.py::TestIdeaCallbacks::test_run_bot_prm_safe_dispatches_transcribed_voice_as_auto \
  tests/test_callbacks.py::TestIdeaCallbacks::test_run_bot_prm_safe_dispatches_completed_voice_with_owner_tuple \
  tests/test_callbacks.py::TestIdeaCallbacks::test_run_bot_prm_safe_dispatches_plain_text_as_auto \
  tests/test_callbacks.py::TestIdeaCallbacks::test_run_bot_prm_safe_drops_owner_callback_in_group
# 83 passed in 51.98s

python tools/test_tiers.py focused-prm
# 317 passed in 93.29s
```

The broad historical full-pytest suite was not run. The next independent Deep
Review remains batched at the declared foundation boundary (PA-00..PA-02), in
line with the operator's one-review instruction and the review policy.

## Remaining gate

PA-00 is technically ready for the required human high-risk slice acceptance.
Do not start PA-01 until that acceptance is explicit and can be recorded
without overwriting the preserved review history.
