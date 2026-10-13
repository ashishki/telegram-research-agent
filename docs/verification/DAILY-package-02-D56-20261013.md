# Daily package 2 — D56 Telegram routing and durable controls

Branch: codex/pa-daily-implementation-20261013. Base:
`988da0e5f907f933168dc655e354ac713a004e64` (local independent narrow closure of
DAILY01-R01/R02/R04). Frozen package review: pending. No paid calls, credentials,
personal accounts, production changes, service/timer activation or external
actions. Tests use isolated synthetic PG and loopback HTTP doubles.

## Result and design

Extended the existing TelegramDestination/MessageBinding/ingress/store, not a
parallel queue. Normalized update v2 preserves owner, exact configured bot/chat/
thread route, reply, UTF-16 quote and declared forward origin. Unknown/hidden
identity remains unknown; forwarded text/transcripts cannot become controls.
Edited owner messages create source revisions and invalidate computation/old
controls/prepared confirmation, without automatically running the edited text.
Business/native Stop are rejected until their separately scoped handlers; topics
get a constant unsupported reply in their exact thread without default history.

Durable inbox decisions and cursor survive restart. Invalid/conflicting updates
are quarantined before polling advances; storage failure leaves the offset.
Natural/callback controls share prior fixed immutable selection. Immediate Watch
controls have a no-repeat fence. Immediate reply attempts are precommitted unknown;
copied ambiguity titles participate in source deletion, and the final send holds
the lineage lock/current-input guard. Callback acknowledgement uses the existing
owner reply authorization. Actual markup reaches the HTTP adapter.

One bounded no-redirect/proxy-free BotAPITransport supports sendMessage,
answerCallbackQuery and getUpdates, with accepted/known_rejected/unknown outcomes,
redacted errors, response caps and typed retry_after; no automatic retry/fallback.
Owner-only sender verifies chat/thread/message identity. Delivery v2 hashes method,
route, result/version and presentation, then binds actual message receipts to the
immutable result. Legacy payloads/checksums are read without rewriting/resending.
No DDL or existing migration checksum changes; new logical records carry v2 tags.

Reply A after B forks bounded immutable A content into a request context, with
source provenance/lineage, without copying confirmation or replacing B's focus.
Fixed shorten/item follow-ups use that context; D04 remains the planner/focus work.
Another bot's delivered preview cannot authorize this bot's plain yes.

API fields were checked read-only against the [official Bot API](https://core.telegram.org/bots/api),
including update shapes, UTF-16 quotes and retry_after. API availability is
separate from observed account/client support. No Mini App.

## Verification ledger

Prefix P: `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q`.
Python 3.10.12. Existing isolated PG fixture; no skips or live acceptance inferred.

- Before new implementation, `P tests/test_daily_telegram_routes.py tests/test_daily_telegram_transport.py`: exit 2, two expected collection errors (missing BotAPITransport).
- `P tests/test_daily_telegram_transport.py`: exit 0, 14 passed /8.37s.
- First `P tests/test_daily_telegram_routes.py`: exit 1, 7 passed /2 failed /69.30s; ack and polling quarantine were not yet wired.
- `P tests/test_daily_telegram_routes.py::test_actual_polling_acknowledges_callback_and_keeps_receipt_binding tests/test_daily_telegram_routes.py::test_polling_quarantines_poison_and_conflict_then_accepts_next`: exit 0, 2 passed /21.56s after wiring.
- `P tests/test_daily_controls.py tests/test_pai_ingress_jobs.py tests/test_daily_telegram_routes.py tests/test_daily_telegram_transport.py tests/test_pai_durable_conversation.py`: exit 1, 55 passed /4 failed /140.34s. Old synthetic callback fixtures mutated the same immutable ID; changed them to new IDs. Rollback count includes inbox/cursor; offset expectation now uses durable cursor (81), and still asserts no advancement on DB failure. No boundary tests weakened.
- `P tests/test_daily_telegram_routes.py::test_reply_worker_uses_a_and_preserves_current_b_focus tests/test_daily_telegram_routes.py::test_manual_quote_wrong_utf16_offset_is_unverified tests/test_daily_telegram_routes.py::test_edited_preview_cannot_be_confirmed_or_reexecuted tests/test_daily_telegram_routes.py::test_legacy_unknown_delivery_read_without_digest_rewrite_or_send tests/test_daily_controls.py::test_opaque_selection_callback_is_owner_route_and_expiry_bound tests/test_pai_ingress_jobs.py::test_enqueue_failure_rolls_back_inbox_and_never_acknowledges tests/test_pai_ingress_jobs.py::test_polling_replays_failed_commit_without_advancing_offset`: exit 0, 7 passed /60.46s.
- `P tests/test_daily_telegram_routes.py::test_polling_worker_final_send_use_real_loopback_transport`: exit 0, 1 passed /10.29s. Actual polling/owner wrapper/worker/delivery HTTP pipeline, three loopback requests; no real bot/model account.
- Broad floor `P tests/test_daily_telegram_routes.py tests/test_daily_telegram_transport.py tests/test_pai_ingress_jobs.py tests/test_pai_delivery.py tests/test_prm_bot_dispatch.py tests/test_pai_durable_conversation.py tests/test_pai_control_polish.py`: exit 1, 100 passed /1 failed /312.95s. Foreign actor with a changed same-ID body was denied by conflict; adjusted foreign handling to uniformly reject/quarantine without exposing owner state, preserving the original immutable identity.
- `P tests/test_daily_telegram_routes.py tests/test_daily_telegram_transport.py tests/test_pai_delivery.py::test_private_delivery_status_and_actual_prm_adapter tests/test_daily_entrypoint.py tests/test_daily_controls.py::test_control_identity_cannot_cross_into_compute_route tests/test_daily_controls.py::test_deletion_removes_control_choices_and_prevents_replay_retarget`: exit 0, 46 passed /121.31s.
- Final dispatch/confirmation guard nodes `P tests/test_daily_telegram_routes.py::test_deletion_blocks_copied_ambiguity_reply_at_final_dispatch tests/test_daily_telegram_routes.py::test_preview_delivered_by_other_bot_does_not_authorize_plain_yes tests/test_daily_telegram_routes.py::test_polling_worker_final_send_use_real_loopback_transport tests/test_pai_control_polish.py::test_delivered_human_preview_confirm_reconcile_repeat_uses_one_write tests/test_pai_control_polish.py::test_button_before_full_delivery_or_for_another_action_cannot_send tests/test_pai_delivery.py::test_private_delivery_status_and_actual_prm_adapter`: exit 0, 6 passed /59.69s.
- Final bot namespace/version nodes `P tests/test_daily_telegram_routes.py::test_bot_namespace_and_result_version_cannot_alias_other_job tests/test_daily_telegram_routes.py::test_exact_result_version_navigation_and_reply_after_other_result tests/test_daily_telegram_routes.py::test_deletion_blocks_copied_ambiguity_reply_at_final_dispatch tests/test_daily_telegram_routes.py::test_preview_delivered_by_other_bot_does_not_authorize_plain_yes`: exit 0, 4 passed /27.86s.
- `git diff --check`: exit 0.
- `PYTHONPATH=src .venv-pai/bin/python -m compileall -q src/prm/runtime src/prm/storage/telegram.py src/prm/telegram_contracts.py src/bot/bot.py src/bot/prm_handlers.py`: exit 0.
- `.venv-pai/bin/python tools/check_personal_assistant_plan.py`: exit 0, 19 slices, review_required unchanged.
- `.venv-pai/bin/python tools/check_pai_plan.py`: exit 0, 32 packets/69 IDs/10 scenarios, draft/2 planned conditional test files absent unchanged.
- `.venv-pai/bin/python tools/playbook.py --check-pin`: exit 0, pin unchanged.
- `.venv-pai/bin/python tools/playbook.py playbook_validate --root . --check references`: exit 0, zero errors/warnings.

These runs overlap; do not sum them into a test count. The broad floor preceded
the final copied-reply/route/namespace guards; exact nodes above verify those.
Project verifier's existing daily runner now includes both new D56 files.

## Review and remaining gates

One independent local read-only package review is pending on the committed diff.
Requested model/effort: active defaults, no override. Observed identity/effort:
unknown. The owner's explicit next-package instruction continues local work;
paid scope/reviewer-route replacement was not inferred. Non-Codex Go/governed
review and human acceptance remain pending, distinct from local engineering.

Retained P2: DAILY01-R03 pure nested Graph/config validation; historical extreme
HTML-depth P2. Pre-identity state/backfill/private cutover remain unverified; local
closure covers newly admitted synthetic state. Actual selected bot identity,
account/client observations and usefulness are D27/D40, not these tests. D57
adds progress/drafts/Stop after D05/D24; D58 adds interactive reports after D19.
Arbitrary reply intent comprehension and document focus belong to D04/D19.

Next dependency-ready block after D56 engineering review/fixes: D05 and D06
(model protocol/capabilities plus frozen evaluation/trace), then the DAG. Formal
PA/PAI approvals remain unchanged. Next safe command: `git show --stat HEAD`.
