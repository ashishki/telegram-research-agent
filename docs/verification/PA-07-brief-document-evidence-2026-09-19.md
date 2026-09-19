# PA-07 BriefDocument evidence — 2026-09-19

Status: locally implemented and verified with offline/local-archive fixtures.
This record is not human acceptance, release approval, live Telegram evidence,
or formal approval of the mechanically `review_required` PA design.

Branch: `docs/personal-assistant-blueprint-playbook-20260918`.
Tested implementation SHA: `d2163a13fce5ae16e1f1cb9d09b3131944b58d49`.

## Implemented boundary

- `BriefDocument` is an immutable, versioned selected-local-archive object.
  Its inspection view exposes the exact half-open period and IANA timezone,
  coverage limitations, selection reasons, deduplication decisions, source
  conflicts, importance separately from urgency, content identity, version and
  comparison references.
- Each selected source preserves provenance clocks and state: publication,
  event, first discovery, update, deletion and reissue. A late archive
  discovery is labelled as discovery rather than silently relabelled as a new
  publication. Comparison uses a factual snapshot digest, not only summary
  text, so an unchanged summary with a changed deadline/source version is
  surfaced.
- The active brief ingress parses one `BriefWindow` before local archive
  candidate selection. `BriefWindowResearchFacade` injects its exact UTC
  `[start_at,end_at)` filters and then fail-closes any returned candidate whose
  local temporal provenance is outside that window. The same object reaches
  `BriefBuildRequest`; it is not parsed again after retrieval.
- Telegram initially receives a concise source-backed card and a one-time
  `Показать полный бриф` reply-keyboard control. The button sends normal text,
  creates no callback or durable action, and opens the full view only through
  the current visible `BriefDocument` binding. Explain-item, shorten, topic
  filter, less-technical, cautious apply and week comparison views all render
  the bound report object with `retrieval_performed: false`.
- Report state is intentionally bounded process-local state tied to the
  current visible response. A new topic or process restart makes it
  unavailable. This is the owner-directed PA-07 boundary, not a substitute for
  PA-08 version exports or PA-09 durable work.

No database migration, production database access, live provider/account,
credential, Telegram polling, timer, Redis, worker, schedule, HTML/PDF/export
or live action was introduced. The two pre-existing untracked local files were
not staged or modified.

## Verification

Commands run against `d2163a1`:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_briefs.py \
  tests/test_assistant_report_dialogue.py \
  tests/test_prm_application.py \
  tests/test_assistant_conversation.py
# 55 passed in 4.03s

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 390 passed in 85.77s

python3 tools/playbook.py --check-pin
# Playbook pin verified; no model, hook or application runtime enabled.

python3 tools/check_personal_assistant_plan.py
# PA plan: 19 consistent slices; schemas, references, dependencies and context limits passed.
# Design state: review_required; no product, human-approval or runtime claim.

git diff --check
# passed
```

The direct suites cover timezone/DST half-open selection, exact local-source
provenance, coverage/empty/partial states, deduplication, unresolved conflict,
importance/urgency, content identity, immutable refresh history, current
visible-response expiry, all report follow-ups, window filtering before and
after candidate selection, and the Telegram full-view button payload. They are
fixture/adapter evidence only: they do not prove actual Telegram rendering,
mobile readability, archive recall quality, or operator usefulness.

`focused-prm` remains green but does not currently collect the PA-07 suites.
The owner expressly prohibited an extension to `tools/test_tiers.py` in this
slice, so the direct command above remains the PA-07-specific executable
evidence.

## Independent slice review

Every listed run used the Role Runner in a fresh read-only process with
requested and observed `gpt-5.6-terra` / `high`; no reviewer changed files.
Early P1 findings drove scoped commits for period/history ownership, content
identity, full navigation, comparison identity and temporal source semantics.
The relevant remediation/recheck chain is:

- `20260919T081817Z-slice_review-e40426a3` through
  `20260919T090003Z-slice_review-48531940`: P1 findings were remediated in
  `a1f8001`, `de32184`, `447af21`, `d553f3b`, `44d2195` and `264bc5f`.
- `20260919T091329Z-slice_review-df23e6ee` reviewed `264bc5f` and found P1
  window binding and button navigation. Commit `d2163a1` binds the window
  before candidate selection, rechecks returned rows, and renders the
  stateless one-time reply button.
- Fresh recheck `20260919T092541Z-slice_review-8b606ab1` reviewed
  `d2163a1`, requested and observed `gpt-5.6-terra` / `high`, and returned
  `STOP_SHIP`. It independently executed a non-writing targeted retry with
  `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider` and reported 17 passed;
  its normal writable-temp command was unavailable in the read-only runner.

The final reviewer retained two P1 requests which are not implementable within
the owner-authorized PA-07 boundary:

1. Durable owner-scoped restart history would contradict the explicit
   requirement that report state be ephemeral and unavailable after restart or
   a new topic. Durable retention/export belongs to a separately authorized
   design/slice decision.
2. Registering PA-07 tests in `focused-prm` would edit `tools/test_tiers.py`,
   explicitly forbidden by the owner for this slice.

Actual Telegram/mobile visual and human content review remain separate gates.
Neither the fixture tests nor the read-only review authorizes runtime,
publication, a design-state change, or PA-08/PA-09 work.

Next command after an owner decision on the two scope conflicts:

```text
python3 tools/run_codex_role.py run --root . --task PA-07 --feature-id PA \
  --slice-id PA-07 --role slice_review --model gpt-5.6-terra \
  --reasoning-effort high --timeout-seconds 1800 --no-publish
```
