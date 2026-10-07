# PAI-27 prepared access packet — no live authority granted

Status: draft, pending PAI-26 tests/review and exact owner scope.
Source candidate: the assigned branch; freeze an exact reviewed SHA first.

| Canary | Exact scope to bind before execution | Initial boundary |
|---|---|---|
| Chat/archive/Brief model | provider/model/version, credential connection fingerprint, user text, selected context classes, upper cost and tariff version | One task; separate history/archive/connector grants |
| Public search/GitHub | minimized public query, primary hosts, selected repository/ref/paths, API quote | Bounded read; no private query mirroring |
| Graph OAuth/read | account, connection, selected scopes/folder/calendar, dates, metadata fields, private vault/key locations, retention | Minimal delegated scopes; app filtering is not provider restriction |
| Canvas | institutional approval reference, account/course IDs, assignments/announcements/calendar, dates | No grades/roster/submissions/files |
| Telegram/reader/export | exact private owner tuple/destination, expiry, required origin data classes, approved reader access | Test recipient only; no public sharing |
| Mail/calendar action | exact preview/version/digest/account/recipient/time/ETag, controlled object and current grant | One confirmation/attempt; lost ACK remains unknown |

Scope records must include start/end, maximum calls/upper cost, expected result,
stop command and cleanup decision. No raw token/account/private content in Git.
Use an already valid exact grant if available; no credential availability scans.
Read, model egress, background collection and delivery/write stay separate.

Before canary: finish all synthetic acceptance, focused/retrofit floors,
independent P0/P1 review/rechecks and visual fixtures at the exact SHA. The
prepared runtime CLI requires explicit configuration; it contains no connect-all
or implicit live enablement. Record actual argv/private receipts in controlled
operator storage, then publish only sanitized metadata. No canary was run.

Stop: default-off control epoch/kill-switch and disconnect, followed by scoped
provider cleanup. A prior external effect is not claimed undone by local stop.
