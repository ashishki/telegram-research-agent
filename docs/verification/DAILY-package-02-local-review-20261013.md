# D56 — independent local package review and fixes

Full reviewer: `/root/daily02_readonly_review`, fresh independent read-only
collaboration process. Requested model/effort: active defaults/no override;
observed identity/effort unknown. No writes/PG/network/provider/credentials.
Local engineering evidence, not non-Codex Go/governed/human acceptance.

Reviewed SHA: `8b56d8e260ea4c9e3b4a3ed03904ff2f67c013c9`.
Range `988da0e..8b56d8e`; binary diff SHA-256:
`c4bc4e3c5c5deaa6a90018fc77796ee0517715bbd9e637d4a2f7e7ccf50775a4`.
One full accumulated review verdict: **STOP**. Frozen findings:

| ID | Severity | Evidence and fix |
| --- | --- | --- |
| DAILY02-R01 | P1 | Source edit after preparation but before transport: original input was checked after sendMessage. Move original compute input/current revision validation before every answer sender call (v2/legacy/multipart), holding lineage through dispatch. |
| DAILY02-R02 | P1 | Source edit between action's consumed precommit and adapter entry cancelled only prepared proposals. Invalidate prepared/consumed proposals under their existing row lock; preserve consumed confirmation and unknown attempt, with no reopen/retry. |
| DAILY02-R03 | P2 | Valid 4,000-emoji forward (16,000 UTF-8 bytes) plus trust prefix hit plain StorageError and stalled the cursor. Keep the raw 16KiB bound, allow at most 200 fixed wrapper bytes and use typed pure validation errors for quarantine. |
| DAILY02-R04 | P2 | Channel forward dropped provider-supplied message_id. Preserve the validated positive message ID alongside declared chat identity/date; hidden identity stays unknown. |

No additional P0/P1 established in immutable replay/quarantine, owner/thread,
opaque expiry, immediate reply deletion fence, unknown/no-repeat transport,
legacy multipart or A-after-B isolation. Recorded fixture tests were inspected,
not rerun. Memory probes ran without writes and excluded subsequent uncommitted
implementer changes. Two setup errors were corrected before the successful R01
probe; no failed probe was counted as verification.

Implementer actual isolated-PG/loopback reproductions before fixes:

- `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_daily_telegram_routes.py::test_source_edit_between_preparation_and_transport_blocks_old_send`: exit 1, 1 failed /7.16s; one stale HTTP send observed.
- Same prefix, `tests/test_daily_telegram_routes.py::test_edit_after_confirmation_precommit_fences_action_and_keeps_unknown_receipt`: exit 1, 1 failed /9.09s; one stale fake Graph write observed.

After fixes, exact command:
`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_daily_telegram_routes.py::test_source_edit_between_preparation_and_transport_blocks_old_send tests/test_daily_telegram_routes.py::test_edit_after_confirmation_precommit_fences_action_and_keeps_unknown_receipt tests/test_daily_telegram_routes.py::test_dispatch_winning_before_edit_preserves_unknown_receipt_and_no_replay tests/test_daily_telegram_routes.py::test_maximum_size_forward_and_next_update_are_admitted tests/test_pai_delivery.py::test_long_mixed_source_answer_records_parts_and_never_resends_unknown tests/test_pai_control_polish.py::test_delivered_human_preview_confirm_reconcile_repeat_uses_one_write`:
**exit 0, 6 passed /38.03s**, zero skips. Both edit-winning cases now have zero
HTTP effects; dispatch-winning retains one unknown receipt and never repeats.
Full forward text and channel message ID are retained; next update is admitted.

Independent narrow R01/R02 closure is pending on the committed fix. Do not run
a second full package review. R03/R04 are addressed by the same scoped fix;
no unrelated full-test reruns or formal acceptance claims.
