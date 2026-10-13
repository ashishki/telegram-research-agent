# Daily package 1 — explicit local entry and job controls

Date: 2026-10-13. Branch: `codex/pa-daily-implementation-20261013`.
Implementation base: `2a1236c` (preserved research packet, original source
`23312b8`). Frozen code commit: `08fb32e1a9c97f8041088e8427f9b9b80059c468`.
Scope: D01–D03. Independent review: **pending**; reviewed SHA:
**none**. No model/provider request was made for this package.

## Implemented result

Explicit durable/compatibility CLI profiles, bounded offline config summary,
shared deterministic RequestIntent adapter, natural status/cancel/result,
reply-to-input and persisted typed message bindings, opaque owner/route/expiry-
bound job choice buttons, actual polling markup propagation, persisted honest
progress and one-job fencing. Other conversation focus and unknown/started
effects are preserved. Missing services produce capability_unavailable rather
than silently routing to a model. No new queue/grant registry/DDL/SQLite store.

New files: runtime/config.py, dispatch.py, job_controls.py;
prm/telegram_contracts.py; storage/telegram.py; three tests/test_daily_* files;
tools/run_daily_acceptance.py; ADR-020 and this receipt. Existing edits:
cli.py, runtime/composition.py, ingress.py, transports.py, storage/jobs.py,
bot/bot.py, inactive service template, test_pai_ingress_jobs.py,
project_verification.json, runbook, tasks/backlog/handoff/status.

The old CLI test was strengthened to require rejection of incomplete durable
configuration. Complete startup is independently exercised using the existing
isolated PG fixture, a complete config and a run_bot spy.

## Exact observed commands

Interpreter: `.venv-pai/bin/python`, **Python 3.10.12**. Prefix `P` below is
`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q`.
All pytest runs use loopback synthetic HTTP/identified isolated test PostgreSQL;
no skips or live/provider/account evidence are inferred.

- Before implementation, `P tests/test_daily_entrypoint.py tests/test_daily_controls.py tests/test_daily_dispatch.py`: exit 2, three expected collection errors for missing new modules.
- First implementation run, same argv: exit 1, 24 passed / 3 failed (test fixture shadowing, non-atomic nested binding transaction, choice order assumption). Corrected transaction binding and fixtures.
- Next same argv: exit 1, 26 passed / 1 failed (repeat-cancel assertion expected Russian text while existing status is cancelled). Corrected the assertion to check terminal state.
- Extended same argv: exit 1, 31 passed / 1 failed (new effect fixture used unsupported kind and omitted effect_key). Kept the queue allowlist intact; corrected the fixture.
- `P tests/test_daily_controls.py::test_started_effect_is_preserved_for_reconciliation tests/test_daily_controls.py::test_deleted_input_cannot_create_or_use_controls`: exit 0, **2 passed / 8.37s**.
- `P tests/test_prm_cli.py tests/test_pai_ingress_jobs.py tests/test_pai_control_polish.py tests/test_pai_operations_runtime.py tests/test_pai_chat_runtime.py tests/test_pai_brief_runtime.py`: exit 0, **52 passed / 179.50s**. This floor preceded the final added control/deletion safeguards; the final command below covers those changes.
- Final `P tests/test_daily_entrypoint.py tests/test_daily_controls.py tests/test_daily_dispatch.py tests/test_pai_durable_actions.py::test_real_application_action_entrypoint_double_click_and_restart tests/test_pai_durable_actions.py::test_wrong_owner_stale_version_revoked_grant_and_cancel_deny tests/test_pai_delivery.py::test_fake_server_accepts_but_ack_is_lost_and_restart_never_resends tests/test_pai_delivery.py::test_cancelled_effect_lease_cannot_send_completed_result tests/test_pai_delivery.py::test_delivery_requires_every_source_class_before_transport tests/test_pai_delivery.py::test_source_revocation_blocks_delivery_of_a_completed_private_copy`: exit 0, **38 passed / 68.47s**, zero skips. Includes all 32 new acceptance cases plus six safety holdouts.
- `.venv-pai/bin/python tools/check_personal_assistant_plan.py`: exit 0, 19 consistent slices; formal design review_required.
- `.venv-pai/bin/python tools/check_pai_plan.py`: exit 0, 32 registered packets/69 IDs/10 scenarios, two planned conditional test files absent; draft states preserved.
- `.venv-pai/bin/python tools/playbook.py --check-pin`: exit 0; pin unchanged.
- `git diff --check`: exit 0.
- `.venv-pai/bin/python tools/playbook.py playbook_validate --root . --check tasks --check references`: first exit 1 with 52 errors (51 preserved missing formal approvals plus one branch name mistaken for a file reference). Removed inline-code formatting from the branch name in tasks.md; the missing formal approvals are not filled or weakened.
- After that fix, `.venv-pai/bin/python tools/playbook.py playbook_validate --root . --check references`: exit 0, zero errors/warnings.
- `PYTHONPATH=src .venv-pai/bin/python -m prm.cli runtime-check --mode compatibility`: exit 0, configured compatibility profile; observed process/schema/grants unknown.
- `.venv-pai/bin/python -m compileall -q src/prm/runtime/config.py src/prm/runtime/dispatch.py src/prm/runtime/job_controls.py src/prm/storage/telegram.py src/prm/telegram_contracts.py`: exit 0.

## Review boundary and remaining evidence

[Actual local synthetic transcript](../evidence/daily-package-01-20261013-transcript.json)
records eight events through `runtime_from_config`, `TelegramJobIngress`, the
real worker and result store. A and B are queued, ambiguity changes neither,
reply cancels A, B completes, return-result retains its delivery scope gate.
Capture argv: `PYTHONPATH=src .venv-pai/bin/python -` with the inline synthetic
PostgresSandbox harness; exit 0. No Telegram/account/provider connection or
screenshot is claimed. No secret/configuration file was read by the harness.

No independent review or human acceptance is claimed. Current REVIEW_POLICY
selects a non-Codex Go reviewer. The fresh assignment restricts paid requests
to separate explicit authorization; the daily reviewer scope/local alternative
must be resolved before claiming this gate. Requested/observed reviewer model
and effort are **not requested / not observed**. No secrets were read or sent.

D56 completes outbound message/result receipts, callback acknowledgements,
update quarantine/revisions and source/thread/quote envelopes. D04 adds a
bounded planner and stable foreground focus; the current fixed phrase adapter
does not establish universal intent understanding or background focus isolation.
Return-result still needs separate delivery authorization. SyntheticTarget is
test-only; personal storage, account/client integration and operator usefulness
remain unobserved. Mini App is excluded. Full-spec formal PA/PAI states stay
draft/planned/review_required; this package is not daily-ready acceptance.

Next block after the independent package gate: **D56**. While a reviewer choice
is pending, independent work may prepare D05/D06/D10; no dependent gate is
marked closed. Next safe command:
`git show --stat HEAD` (inspect the frozen package before the scoped reviewer).
