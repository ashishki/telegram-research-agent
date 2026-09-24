# PA-11 — calendar and contacts read contracts (local evidence)

Date: 2026-09-24
Boundary: local, synthetic only. No OAuth flow, network call, token storage,
default database, scheduler, delivery or live account is enabled.

## Implemented

`src/prm/schedule_connectors.py`:

- documented provider profiles (Microsoft Graph, Google Workspace) with the
  exact read-only calendar/contacts scopes;
- `CalendarScopeSelection`: explicit provider + account, bounded calendar list,
  bounded window (<= 370 days), validated IANA local timezone, item cap, no
  writes; `describe_calendar_scope` states the read-only boundary honestly;
- owner-bound, expiring consent preview/confirmation with a scope digest;
- `CalendarEvent` with source/local timezone handling (`local_span`), status,
  recurrence id and version identity; `detect_conflicts` returns overlapping
  pairs and excludes cancelled events; `free_busy` derives busy intervals;
- `RecurrenceRule` (daily/weekly/monthly, interval, count or until) with a
  bounded `occurs_on` check — no server-side expansion is assumed;
- `Contact` (validated unique emails) and `resolve_recipient`, which resolves
  only when exactly one contact matches and otherwise returns `ambiguous` or
  `not_found` — a name is never turned into a guessed address;
- `require_calendar_read_access` / `require_contacts_read_access`: fail-closed
  PA-02 reservation checks for the `calendar.read` and `contacts.read` purposes
  (registered in `src/prm/capabilities.py`). A calendar grant never authorizes a
  directory read.

## Verification

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_calendar.py tests/test_assistant_contacts.py
# 9 passed

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 535 passed
```

Both suites are registered in `focused-prm` (and therefore `fast-contract`).

## Remaining gates

Runtime verification is still required by the task: a real read-only calendar
and contacts sync against an authorized account, plus revocation and
multi-account identity in practice. This slice deliberately provides only the
local contract; it is not runtime evidence and makes no acceptance claim.
Recurring-event expansion, timezone DST edge cases against a live provider and
free/busy server queries remain unverified against real data.
