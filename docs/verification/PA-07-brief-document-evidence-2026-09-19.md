# PA-07 BriefDocument evidence — 2026-09-19

Status: locally implemented and verified with offline/local-archive fixtures.
One bounded owner-authorized private Telegram runtime attempt is recorded below,
but it did not receive a test brief or human review. This record is not human
acceptance, release approval, rendered-live-brief evidence, or formal approval
of the mechanically `review_required` PA design.

On the same private owner conversation, a subsequently received expanded-brief
render was reported unreadable and dominated by audit language. Treat that
feedback as a P1 usability finding, not as approval or a release result. The
private rendered text, source URLs, source excerpts and account information are
intentionally not copied into this repository or this evidence record.

Branch: `docs/personal-assistant-blueprint-playbook-20260918`.
Tested implementation SHA: `c1cd081`.

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
- The Telegram dispatcher retains a bounded, process-local `BriefDocumentStore`
  keyed by local database path, so an immediate second command can navigate the
  visible report. It evicts the oldest of at most four stores and naturally
  loses that visible projection on process restart; no job, timer or shared
  runtime state is involved. A narrow settings-only compatibility path remains
  for pre-existing injected test facades that cannot accept the PA-07 store
  seam.
- The owner authorized a narrow 2026-09-19 P1 remediation: immutable selected
  document versions are retained in the existing local SQLite schema only when
  the Telegram ingress carries one canonical private `(chat_id, actor_id,
  owner_chat_id)` tuple. Application code derives its opaque owner reference
  from that tuple and replaces any caller-supplied `BriefBuildRequest.owner_ref`.
  Group, absent, mismatched and CLI tuples retain only ephemeral visible
  state. Durable reads, listing, writes and deletion each consume that tuple
  plus exact
  `(brief_id, version)`; there is no cross-chat or latest-report lookup.
- Retained history contains bounded excerpts/inspection data rather than the
  archive corpus, checks its stored content identity when loading, is capped at
  64 versions/documents owner-wide, and has owner-scoped deletion. A new topic
  or process restart still removes the visible conversation binding, so normal
  language follow-ups cannot be reconstructed after restart. Exact retained
  reads are a future authorized report-reader seam, not PA-08 export or PA-09
  scheduling.

No production database was migrated. The additive schema was run only against
temporary test databases. On 2026-09-19 the owner separately authorized one
time-bounded manual PA-safe Telegram polling attempt with the existing
documented secret path; it ran with automatic migrations skipped, was stopped
cleanly by SIGINT, and the pre-existing `telegram-prm-assistant.service` was
restored active. It received no confirmed test brief or human review before
shutdown; one generic `getUpdates` failure was handled without exposing
credentials or private content. No raw message, account ID, secret, report or
provider/model egress was retained here. No timer, Redis, worker, schedule,
HTML/PDF/export or live action was introduced. The two pre-existing untracked
local files were not staged or modified.

## Verification

Commands run against `c1cd081`:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_briefs.py \
  tests/test_assistant_report_dialogue.py
# 24 passed in 8.78s

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 414 passed in 93.19s
```

The direct suites cover timezone/DST half-open selection, exact local-source
provenance, coverage/empty/partial states, deduplication, unresolved conflict,
importance/urgency, content identity, immutable refresh history, current
visible-response expiry, all report follow-ups, window filtering before and
after candidate selection, and the Telegram full-view button payload. The
durable-history additions cover private-tuple owner binding,
caller-supplied owner replacement, group/missing/mismatched/CLI rejection,
forged-tuple read/list/write/delete denial, cross-owner denial,
restart-visible-state expiry, tampered JSON fail-closed, owner deletion and the
owner-wide 64-document cap. They are fixture/adapter evidence only: they do
not prove actual Telegram rendering, mobile readability, archive recall
quality, or operator usefulness.

The final direct dialogue case dispatches a brief and then `объясни пункт 2`
through separate Telegram command calls, confirms that the shared bounded
store renders the retained visible item, then clears that process-local
registry to model a restart and confirms the old item is not reconstructed.

`focused-prm` now includes both PA-07 suites. It is a regression tier, not
human content, visual, live runtime, or release evidence.

Current writable-workspace rerun at reviewed `ba84cd3` (the code is unchanged
from `c1cd081`; that commit adds the preceding evidence record) completed:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_briefs.py \
  tests/test_assistant_report_dialogue.py
# 24 passed in 8.07s

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 414 passed in 82.29s

python3 tools/playbook.py --check-pin
# Playbook pin verified; no model, hook or application runtime enabled.

python3 tools/check_personal_assistant_plan.py
# PA plan: 19 consistent slices; schemas, references, dependencies and context limits passed.
# Design state: review_required; no product, human-approval or runtime claim.
```

`git diff --check` also passed. This is writable local-fixture evidence only;
it does not change the external gates below.

## Telegram-card P1 remediation

Commits `d6188c3` through `023688c` replace the Telegram human surface with a
short, escaped native-Telegram HTML card and a conversational expanded view.
The compact card reserves its two mobile slots for an assessed priority or a
source-bound project reference. When the local archive contains only unranked
material it says so rather than promoting arbitrary rows as the week's most
important news. The expanded view uses a title, a bounded summary, a
source-bound `Зачем вам` line only where the selected document supplies a
project/relevance reference, human labels for importance and urgency, and a
named source link. It hides document IDs, snapshot hashes, source-state dumps
and version/history mechanics from the Telegram conversation; those remain
available at the inspectable `BriefDocument` boundary. Coverage stays visible
in ordinary language so partial local selection is not presented as a complete
week.

At `023688c`, writable-workspace checks completed:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_briefs.py \
  tests/test_assistant_report_dialogue.py
# 27 passed in 12.65s

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# PASS (the focused tier completed; its progress/count output was intentionally
# suppressed in the final capture to preserve an unambiguous exit result)

python3 tools/playbook.py --check-pin
# Playbook pin verified; no model, hook or application runtime enabled.

python3 tools/check_personal_assistant_plan.py
# PA plan: 19 consistent slices; schemas, references, dependencies and context limits passed.
# Design state: review_required; no product, human-approval or runtime claim.
```

`docs/verification/PA-07-telegram-brief-user-judge-prompt.md` is an advisory
privacy-safe rubric, not a product prompt. A fresh read-only `gpt-5.6-terra`
with `high` reasoning received only a synthetic/redacted two-item rendering;
it returned `pass`, scores 5/5 for scanability, priority honesty and source
clarity, 4/5 for usefulness, and no P1. It received no live archive content,
user message, account data, credential or runtime authority. This supports the
offline wording decision only; a person still needs to inspect the current
Telegram rendering after an explicitly bounded service refresh.

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
  retention cap and current evidence. Commit `dfa135f` added the first two;
  this record replaced the stale evidence and reported the corresponding tests.
- Fresh review `20260919T103250Z-slice_review-a7231974` reviewed `bce76c5`,
  requested and observed `gpt-5.6-terra` / `high`, and returned `STOP_SHIP`.
  It found that the intermediate `BriefOwnerScope` was forgeable. Commit
  `ff6329e` removes that object-capability interface: durable store methods
  now consume the canonical private tuple themselves; the owner-authorized
  schema/test-tier amendment is recorded in `docs/tasks.md`.
- Fresh review `20260919T104122Z-slice_review-b4f139ef` reviewed `89cc3b4`,
  requested and observed `gpt-5.6-terra` / `high`, and returned `STOP_SHIP`.
  It found that non-string values such as integer `42` were incorrectly
  coerced into a private owner ID. Commit `fa1cc10` now calls the established
  strict `canonical_private_owner_id` helper and adds integer rejection for
  persistence, lookup, listing and deletion.
- Fresh review `20260919T104658Z-slice_review-6fbe8421` reviewed `6f36224`,
  requested and observed `gpt-5.6-terra` / `high`, and returned `STOP_SHIP`.
  It found that the earlier content digest excluded history/comparison refs and
  document-level selection reasons. Commit `9603c28` adds those fields to the
  canonical digest, makes semantic JSON tampering fail closed, and returns the
  machine registry to its unchanged `review_required` state; the precise owner
  amendment remains in this task record.

- Fresh review `20260919T105529Z-slice_review-ecf52f50` reviewed `fde4313`,
  requested and observed `gpt-5.6-terra` / `high`, and returned `STOP_SHIP`.
  It found that the Telegram dispatcher constructed a new visible store for
  each command, preventing a real second-turn report follow-up. Commit
  `d9a684f` retains the bounded process-local store and adds the dispatcher
  restart-denial test. Commit `c1cd081` preserves the settings-only constructor
  expected by narrow legacy injected test facades; the real assistant continues
  to receive the shared store.

Fresh recheck `20260919T110742Z-slice_review-d305cf5c` reviewed `ba84cd3` in a
fresh read-only Role Runner process, requested and observed
`gpt-5.6-terra` / `high`, and returned `STOP_SHIP`. It found no new code defect:
static diff/AST checks passed and it confirmed the authorized durable-history,
ownership, window and visible-object boundaries. Its required test commands
could not create a temporary directory in that read-only sandbox; the
writable-workspace receipts above supply the executable result for the same
code. The remaining P1 acceptance gates are actual private Telegram/mobile
rendering inspection and human content review. A separately owner-authorized,
time-bounded manual polling attempt was made after this review, but no test
brief or human result arrived before shutdown, so neither gate is satisfied.

Neither fixture tests, the model review, nor this evidence authorizes runtime,
publication, a design-state change, or PA-08/PA-09 work. The PA design remains
mechanically `review_required`.

Next required activity: conduct a time-bounded private Telegram/mobile
inspection of the current `023688c` card and record only the human verdict
(never the private report contents). A fresh independent slice review is also
required for this P1 remediation. No additional local command can substitute
for the human gate.
