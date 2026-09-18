# PRM-SN-2B — exact save/confirmation receipt

Date: 2026-09-17

Scope: exact evidence-item selection and preview, confirmation/cancel/replay
lifecycle, private-chat ownership, and non-subscription wording. No live
Telegram, archive, provider, production database, migration, delivery, or
notification operation was run.

Implementation evidence:

- A multi-item answer requires explicit `n1`…`n5` selection; a one-item answer
  binds `n` to that item’s stored source and snippet.
- Callback actions are stored allowlisted; group registration fails closed and
  private callbacks bind the Telegram actor to the registered private chat.
- Confirmation uses an owner-bound lease and the canonical unique
  `(proposal_id, confirmation_token_hash)` key. `INSERT OR IGNORE` turns a
  stale-lease race into an existing receipt, rather than a duplicate event or
  an error.
- Save/watch and help text explicitly state that saving a topic does not enable
  monitoring, notifications, subscriptions, or delivery.

Focused verification:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  tests/test_prm_post_answer_actions.py tests/test_prm_utd_dispatch.py \
  tests/test_pi_tools.py -q
51 passed in 23.86s
```

`py_compile` for the changed runtime modules and `git diff --check` passed.

Immediate confirmation/persistence review:

- Base SHA: `cee8baae3b8a41f571bd689f2dadf7e6e981863f`
- Final reviewed working-diff hash: `6abe6419095ca5a5b1076447828f251e3866574a5a62c5a07ead1779aaf25f26`
- Requested and observed model/effort: `gpt-5.6-terra` / `high`.
- Runtime evidence: Codex runner banner for session
  `01a0afee-1cef-7363-a8a0-2b7eb9f9fd2b` reported both values; sandbox was
  read-only. The review used a fresh sanitised `/tmp` snapshot with public
  code and synthetic tests only.
- Result: `PACKET_REVIEW_RESULT: PASS`. Earlier P1 findings (single-item
  binding, confirmation ownership/race handling, and notification wording)
  were corrected and re-reviewed.

Remaining boundary: this is only the task-level immediate review. PRM-SN-DR-2
still requires the completed accumulated Phase 2 scope, including 2C. Human
and runtime gates remain pending; this receipt does not authorize a pilot,
production write, egress, subscription, or delivery.
