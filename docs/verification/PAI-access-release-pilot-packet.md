# PAI-27..29 access, release and pilot preparation

Status: preliminary decision packet; no live/deploy/pilot readiness or approval.
Source baseline: 8faee4232cb30e6b6f39cfbd974c151846f79da6, local PAI phase A diff.

## Source and operation decisions before canary

| Area | Known selection / separate scope still required |
| --- | --- |
| Mail | Historical owner selection is Microsoft 365/Exchange Online; specific account/folder/time/items, delegated scopes, model egress, retention and revoke/delete must be confirmed |
| Calendar/contacts | Account/resource list, read/free-busy/directory scopes and exact recipient ambiguity policy |
| Canvas | Institutional developer/OAuth access; selected assignments/calendar/announcements only; excluded grades/roster/submission bodies |
| Model and reviewers | Provider/model, allowed synthetic/private data classes, maximum calls/tokens/currency/time, requested/observed identity; no key in chat |
| Telegram delivery | Owner tuple/destination, foreground versus background grants, duration/caps/quiet hours and unknown-send reconciliation |
| Memory/media/reader | History/report/upload retention, model/OCR scope, access expiry and deletion/backup exceptions |

Credentials use secure setup outside Git/chat; key availability is not consent.
Failure of a selected required source is an external full-acceptance blocker,
not a reason to claim integration or stop independent authorized local work.

## Release decision package after PAI-26

Must reference exact reviewed candidate SHA and hashes, all acceptance commands
and observed results, wired positive/failure matrix, rendered exports, current
grants/retention, sanitized provider receipts, restore/cutover rehearsal, one
active ingress inventory, unknown-effect drain and operator rollback owner.
Actual canary/migration/rollback CLI commands are not implemented in phase A;
PAI-24..26 must create/test them before this packet can be called executable.
No placeholder command is presented as a working provider/deploy path.

Pre-release source checks available now:
python3 tools/playbook.py --check-pin
python3 tools/check_personal_assistant_plan.py
python3 tools/check_pai_plan.py --require-implemented-tests
The final command currently fails because new acceptance suites do not exist.
Planning checks do not grant provider/deployment authority.

## Owner pilot proposal after approved cutover

Agree the spec's initial 20 tasks and several weeks of actual use before start.
Cover Chat multi-turn/topic reset, archive/web freshness/conflicts, complete
Brief views, Watch pause/quiet/DST, selected account lifecycle, exact Act
edit/confirm/reconcile, inspect/delete memory, voice/PDF, recovery and cost.
Record usefulness/missed obligations/noise, p95 latency and cost per success.
Keep screenshots/private corpus outside Git. Accept the exact final SHA only
with full matrix, independent review and actual owner decision via PA-18.
