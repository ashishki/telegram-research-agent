# Response to review #32 candidate — final independent recheck pending

Source: 832f9f3. Requested/observed OpenCode Go / mimo-v2.6-pro, thinking
disabled, strict JSON, 16000 output / 900 s. Complete response in
PAI-review-32-candidate.json; receipt PAI-review-continuation-32.json.
The response has FIX_P1_FIRST and two P0 findings, so it fails the enforced
verdict/severity consistency check. No valid phase verdict or acceptance is
inferred. It consumed call #32. The exact candidate is preserved unedited.

The findings still provided concrete paths worth checking. This response is
implementation/test evidence; independent resolution belongs to call #33.

| Candidate finding | Concrete response |
| --- | --- |
| Undefined `strict`/`ref` in reservation-current check | Removed the copied strict-preparation branch from this boolean check; storage/validation failure returns False. The distinct `_commit_durable_transport(strict=True)` path still raises preparation-unknown and retains its fence. Real synthetic storage-error case verifies a bounded denial without HTTP. |
| Same connection silently gains different OAuth scopes | `begin` now rejects a changed scope set for an existing connection. A new connection and fresh owner-bound handshake are required. Test rejects reuse before HTTP and verifies the new handshake separately. The provider echo remains strictly within the exact requested set. |
| Calendar deletion across a narrowed/partial selection | Selection digest already includes calendar refs and the whole date/filter payload. Added an explicit calendar-ref constraint to completed-snapshot deletion. Test reads two real fake-HTTP calendars, narrows to one, then runs a partial read; the other calendar's rows remain present and undeleted. |
| Obsolete tokens remain after unlink failure; stale/missing token behavior | Retirement refs are committed with account rotation in PostgreSQL's existing versioned store. Bounded `cleanup_retired` retries them after restart, skips every active account token, and marks completed metadata after durable unlink. Missing active credentials produce an explicit interactive-reconnect denial. Vault creation/unlink also fsync the directory. |
| Unknown action receipt permits a resend | Existing durable attempts already return the same unknown receipt before another write. Receipts now additionally expose `retry_allowed=False`; dynamic exception class names were replaced by fixed bounded reason codes. Real Graph fake-HTTP ACK loss followed by a reconstructed runtime verifies one write and the same unknown receipt. |
| Body read occurs before selected-message check; provenance resembles authorization | Body reads now require a message in the owner/connection/selection-bound synchronized metadata snapshot before reserving or issuing HTTP, then use the selected folder endpoint and validate the returned identity/filter again. Provenance remains a plain dictionary. Authorizing that read description without reserving it produces no reservation and fails the actual operation guard. GraphTransport itself now rejects a plain dict or unreserved decision before even looking up/refreshing a credential. |
| Calendar timezone/interval validation missing | Timezones were already checked with ZoneInfo at preview/edit and used by `_calendar_time`. The interval now also uses the existing 370-day calendar-read bound at preview/edit/preflight. Invalid timezone or oversized preview/edit causes no HTTP/write. |
| Late Canvas denial looks like unavailable coverage | CapabilityDenied is now recorded as scope_denied, distinct from transport/storage unavailable; both keep incomplete coverage and never produce checked evidence. |
| Vault directory not fsynced | Directory entries are fsynced after encrypted file creation and unlink. No secrets leave private storage. |

The body-read test also reproduced an independent existing defect:
`MailScopeSelection` has `resource_ref`, not `account_ref`. The old access to
`selection.account_ref` raised AttributeError before this path could work.
The fix uses provider identity plus the current transport and owner/connection/
scope-bound metadata row. The account remains bound by GraphTransport/OAuth.

Token refresh follow-through: before contacting the token endpoint the account
commits `awaiting_refresh` with a new revision. A current row lock rechecks that
revision/credential through the bounded request. ACK loss, provider/storage
indeterminacy or restart cannot automatically reuse the old refresh token;
the caller sees `CredentialRefreshUnknown(retry_allowed=False)` and an owner
handshake is required. A successful refresh installs the new token and keeps
the old-token retirement metadata. An ambiguous DB commit never deletes a new
token on the assumption that the commit rolled back. Tests verify one real
fake-HTTP refresh across ACK loss/reconstruction, committed state before HTTP,
reuse of only the completed new credential, and explicit reconnect recovery.

Provider path confirmation: Microsoft documents
[GET /me/mailFolders/{id}/messages/{id}](https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0).
The folder endpoint is used in addition to local selection checks. Local
folder/domain/date filtering still does not narrow the provider token itself.

## Exact observed checks

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_review_recovery.py tests/test_pai_connections.py tests/test_pai_graph_mail.py tests/test_pai_schedule_runtime.py tests/test_pai_academic_runtime.py tests/test_pai_action_runtime.py
```

Initial: exit 1, 1 failed / 6 passed in 26.14 s. AttributeError at the
nonexistent MailScopeSelection.account_ref was preserved and repaired, without
weakening the test. Corrected run: exit 0, 19 passed in 81.19 s, zero skips.
The two subsequent refresh tests were added after this corrected run.

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_review_recovery.py::test_refresh_ack_loss_keeps_a_durable_fence_across_reconstructed_clients tests/test_pai_review_recovery.py::test_successful_refresh_commits_fence_before_http_and_reuses_only_new_token tests/test_pai_review_recovery.py::test_committed_token_retirement_survives_cleanup_failure_and_restart tests/test_pai_connections.py
```

Exit 0: 5 passed in 24.37 s, zero skips/failures on the refresh follow-through.

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_durable_policy.py tests/test_pai_durable_actions.py tests/test_assistant_actions.py tests/test_pai_end_to_end.py::test_object_followups_confirmation_cancel_restart tests/test_pai_media_runtime.py
```

Exit 0: 38 passed in 66.90 s, zero skips/failures on the final local changes.

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_pai_review_recovery.py::test_body_read_rejects_unselected_ids_before_http_and_provenance_is_not_authority tests/test_pai_graph_mail.py tests/test_pai_schedule_runtime.py tests/test_pai_action_runtime.py
```

Exit 0: 6 passed in 28.22 s, zero skips/failures after the last GraphTransport
reservation guard. Its counterexample sends both an unsealed provenance dict
and an allowed-but-unreserved decision to the transport; neither causes HTTP.
Earlier whole-tier passes remain dated observations at their original SHA.
No real OAuth account, body, Canvas institution, token exchange, action or
product model provider was exercised. Only explicitly authorized independent
review used paid egress, with public code/synthetic packets.

Changed code: `src/prm/storage/policy.py`, `src/prm/storage/actions.py`,
`src/prm/confirmed_actions.py`, `src/prm/runtime/connections.py`, `graph.py`,
`schedule.py`, `academic.py`, and `actions.py`. Tests:
`tests/pai_runtime_fixtures.py`, `tests/test_pai_review_recovery.py`.
Review evidence/handoff/packets are separate documentation changes.
Call #33 is a fresh actual-finding recheck, not a retry of invalid call #32.
Governed role coverage, exact human design approval and PAI-27..29 live/owner
gates remain separate regardless of its verdict.
