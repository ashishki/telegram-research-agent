# PA-12 — Academic Inbox contracts (local evidence)

Date: 2026-09-24
Boundary: local, synthetic only. No OAuth, network call, token storage, default
database, scheduler, delivery, live Canvas/mail account or institutional
permission is enabled or assumed.

## Implemented

`src/prm/academic_inbox.py`:

- `CanvasScopeSelection`: explicit Canvas provider + account, bounded course
  list and window, validated local timezone, item cap, and hard refusals for
  `fetch_submissions`, `fetch_grades`, `fetch_attachments`; at least one read
  surface must be selected. `describe_canvas_scope` states that grades,
  submissions, rosters, files and attachments are never read.
- `AcademicCandidate` normalizes Canvas assignments/announcements/calendar,
  mail and UTD public evidence into one bounded, versioned DTO with category
  (`obligation|opportunity|reading|administrative|uncertain`), authority
  (`canvas|official_message|aggregator`), deadlines, eligibility note +
  uncertainty, and completion.
- `categorize` is deterministic and stage-agnostic; `authoritative_deadline`
  ranks canvas over mail over aggregators; `conflicting_deadlines` surfaces
  distinct instants and never merges them.
- `derive_stage` returns `overdue|due_soon|upcoming|completed|unknown`, and
  completion distinguishes `local_done` from `source_completed`.
- `deduplicate_candidates` merges the same item seen through several sources,
  keeping the strongest authority and unioning sources and deadline instants so
  no evidence is silently dropped.
- `build_reminder_preview` / `confirm_reminder`: a reminder binds to the exact
  candidate and `source_version`; a source revision invalidates the old preview.
- `require_academic_read_access`: fail-closed PA-02 reservation check for the
  `academic.read` purpose (registered in `src/prm/capabilities.py`), separate
  from mail and calendar grants.

## Verification

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_academic.py
# 7 passed

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 542 passed
```

The suite is registered in `focused-prm` (and therefore `fast-contract`).

## Remaining gates

Institutional permission and a minimal Canvas read scope must be confirmed with
UTD eLearning/IT before any real Canvas/mail processing; this slice assumes
none. Runtime verification (live read, paging, real conflicting deadlines,
stage/priority on real data, reminder delivery) remains required and is not
claimed here. The public UTD watch consent is not reused as consent for mail or
Canvas.
