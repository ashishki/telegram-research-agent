# PA-07 BriefDocument evidence — 2026-09-19

Status: locally implemented and verified with offline/local-archive fixtures.
This record is not human acceptance, release approval, live Telegram evidence,
or formal approval of the mechanically `review_required` PA design.

Branch: `docs/personal-assistant-blueprint-playbook-20260918`.
Tested implementation SHA: `dfa135ff274855dee05283ff9c62f7a14429d018`.

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
- The owner authorized a narrow 2026-09-19 P1 remediation: immutable selected
  document versions are retained in the existing local SQLite schema only when
  the Telegram ingress carries one canonical private `(chat_id, actor_id,
  owner_chat_id)` tuple. Application code derives an opaque owner scope from
  that tuple and replaces any caller-supplied `BriefBuildRequest.owner_ref`.
  Group, absent, mismatched and CLI tuples retain only ephemeral visible
  state. Durable reads require that authenticated scope plus exact
  `(brief_id, version)`; there is no cross-chat or latest-report lookup.
- Retained history contains bounded excerpts/inspection data rather than the
  archive corpus, checks its stored content identity when loading, is capped at
  64 versions/documents owner-wide, and has owner-scoped deletion. A new topic
  or process restart still removes the visible conversation binding, so normal
  language follow-ups cannot be reconstructed after restart. Exact retained
  reads are a future authorized report-reader seam, not PA-08 export or PA-09
  scheduling.

No production database was accessed or migrated. The additive schema was run
only against temporary test databases. No live provider/account, credential,
Telegram polling, timer, Redis, worker, schedule, HTML/PDF/export or live
action was introduced. The two pre-existing untracked local files were not
staged or modified.

## Verification

Commands run against `dfa135f`:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_briefs.py \
  tests/test_assistant_report_dialogue.py
# 22 passed in 8.08s

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 412 passed in 93.70s
```

The direct suites cover timezone/DST half-open selection, exact local-source
provenance, coverage/empty/partial states, deduplication, unresolved conflict,
importance/urgency, content identity, immutable refresh history, current
visible-response expiry, all report follow-ups, window filtering before and
after candidate selection, and the Telegram full-view button payload. The
durable-history additions cover exact private-scope owner binding,
caller-supplied owner replacement, group/missing/mismatched/CLI rejection,
cross-owner denial, restart-visible-state expiry, tampered JSON fail-closed,
owner deletion and the owner-wide 64-document cap. They are fixture/adapter
evidence only: they do not prove actual Telegram rendering, mobile readability,
archive recall quality, or operator usefulness.

`focused-prm` now includes both PA-07 suites. It is a regression tier, not
human content, visual, live runtime, or release evidence.

## Independent slice review

Every listed review uses the Role Runner in a fresh read-only process with
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
- Pre-amendment recheck `20260919T092541Z-slice_review-8b606ab1` reviewed
  `d2163a1` and returned `STOP_SHIP` for durable restart history and PA-07
  registration in `focused-prm`. The owner then authorized those two bounded
  remediations.
- Fresh review `20260919T102000Z-slice_review-5a7957ec` reviewed `f146925`,
  requested and observed `gpt-5.6-terra` / `high`, and returned `STOP_SHIP`.
  Its P1 findings were authenticated private owner binding, an owner-wide
  retention cap and current evidence. Commit `dfa135f` adds the first two;
  this record replaces the stale evidence and reports the current test runs.

A fresh independent Terra/high recheck of `dfa135f` plus this evidence update
is still required. Actual Telegram/mobile visual and human content review also
remain separate gates. Neither fixture tests nor model review authorizes
runtime, publication, a design-state change, or PA-08/PA-09 work.

Next command:

```text
python3 tools/run_codex_role.py run --root . --task PA-07 --feature-id PA \
  --slice-id PA-07 --role slice_review --model gpt-5.6-terra \
  --reasoning-effort high --timeout-seconds 1800 --no-publish
```
