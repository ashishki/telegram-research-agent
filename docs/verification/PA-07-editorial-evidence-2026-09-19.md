# PA-07 editorial correction — implementation evidence

Owner direction: integrate the product/content/conversation recommendations
through active tasks up to PA-15 and begin local implementation, batching
reviews. This is a coherent first implementation of that correction, not a
claim that PA-08..15 or the full programme is implemented/accepted.

Baseline: `1533fe00122efaf0d017e2e5232e242f60b7f354` on
`docs/personal-assistant-blueprint-playbook-20260918`.

## Changed behavior

- The programme contract in `docs/design/PA-PRODUCT-QUALITY.md` is referenced
  by task acceptance and the compact design. The paired machine registry keeps
  every existing slice/dependency and the `review_required` state.
- Ordinary brief retrieval separates topic from period/display instructions,
  permits 32 candidates and 8 selected sources, and shows up to 5 editorial
  stories. This is bounded selection, not full-week recall evidence.
- `brief_editorial.py` constructs event stories with a headline, takeaway,
  explanation, editorial selection rationale, optional conditional next step,
  caveat and exact source quote anchors. Duplicate accounts can support one
  story; omitted source references remain inspectable.
- The active application path invokes this synthesis using the existing typed
  archive grant pair. It reserves an additional operation under those same
  grants for an isolated content review before generation. No grant is created
  or enlarged; insufficient review budget denies generation. Each transport
  rechecks its own one-use pair. No automatic retries or new provider are added.
- Unknown priorities do not block editorial judgment. Schema/reference/quote
  checks reject malformed or unbound output; a separate model request checks
  semantic support and editorial usefulness. Its pass is measured as
  `source_anchored_reviewed` / `model_review_passed`, not deterministic truth or
  human acceptance. A rejected/failed review leaves the original source report.
- Editorial text is included in document identity, version storage and the
  shared optional DTO field. Existing stored documents still decode. Short,
  full, explain, apply and topic views reuse saved stories and source references.
- Fallback expanded views retain the available excerpt (up to 1200 characters)
  and label it as material awaiting editorial synthesis; empty urgency fields
  are hidden. They are not represented as accepted editorial content.
- The advisory user-judge protocol now requires source/generated-transcript
  evidence for content acceptance, substantive follow-ups and a single 0-4
  scale. Earlier presentation-only synthetic passes are not reused.

## Verification ledger

- `python3 tools/playbook.py --check-pin`: PASS.
- `python3 tools/check_personal_assistant_plan.py`: PASS, 19 consistent slices;
  design remains `review_required`.
- `git diff --check`: PASS.
- `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
  tests/test_assistant_brief_editorial.py tests/test_assistant_briefs.py
  tests/test_assistant_report_dialogue.py tests/test_prm_synthesis.py`:
  59 passed in 9.21s, including ordinary-route retrieval, generation, review
  and saved-story discussion.
- Earlier development failures were preserved in the session: initial test
  import path; three assertions for the intentionally replaced empty-priority
  UI; and the test's incorrect registry revocation method name. They were
  corrected without removing ownership, temporal, citation or retention checks.
  The first focused-prm run had 1 failed / 436 passed: the active brief adapter
  discarded a valid source support_span when no display snippet was present.
  The adapter now preserves the exact selected support span; the end-to-end
  regression passes in the dedicated suite. The full focused recheck passed: 437 tests in 120.75s.
- `feature_workflow context` first reported a missing planning decision;
  `feature_workflow plan --task PA-07` produced `needs_input`; context then
  reported that state as blocking workflow draft/start/check. No artifact was
  hand-edited and no formal approval inferred. Local work follows the owner's
  newer explicit scope direction; this mechanical gate remains recorded.

## Evidence limits and remaining work

All source data and model responses in these tests are synthetic; provider
calls are replaced. No private archive, production DB, credential, runtime model,
Telegram service, job or timer was used. No deployment occurred. Human mobile
and content acceptance and actual provider behavior remain unverified.

This patch supplies an editorial pipeline and meaningful stored explanations;
it does not complete arbitrary natural-language conversation, personalized
memory, complete weekly recall, primary-source web enrichment or PA-08..15.
The model content checker needs calibration against owner-rated examples and
a frozen holdout. A model pass can still be wrong. Those requirements remain
in the amended task graph rather than being marked complete.

Independent slice review must record exact reviewed SHA, requested/observed
`gpt-5.6-terra` / `high`, findings and any scoped recheck. It is not a new full
Deep Review. Final implementation and review receipts are appended below.

Next local development scope after this correction: strengthen the held-out
content/conversation scenarios and the relevant PA-03/04/06 integrations,
then continue dependency-ready tasks under the common quality contract.
Reproduce this batch with the dedicated command above or
`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm`.

## Final focused receipt

Implementation commit: `e280723aa4f40de4815e36ab37cf933dc2e5ed85`.

`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm`
completed with exit 0: **437 passed in 120.75s**. The historical full suite was
not run. The log is local at `/tmp/pa-editorial-focused-final-20260919.log`.

`python3 tools/playbook.py playbook_validate --root . --check tasks --check references`
returned 19 `TASK_DESIGN_APPROVAL_REQUIRED` errors, one per PA slice, reflecting
the preserved unapproved design state. The dedicated plan checker passes schema,
reference, dependency and context consistency; formal approval is not forged.

A sanitized, explicitly fictional structure preview is
`docs/verification/PA-07-editorial-example-2026-09-19.md`.

The independent review was launched with:
`python3 tools/run_codex_role.py run --root . --task PA-07 --feature-id PA --slice-id PA-07 --role slice_review --model gpt-5.6-terra --reasoning-effort high --timeout-seconds 480 --no-publish`.
Its run ID is `20260919T155031Z-slice_review-1510807c`; the manifest binds
`e280723aa4f40de4815e36ab37cf933dc2e5ed85`. The reviewer returned one P1: the generator's valid no-news empty-story result
was rejected by the parser. The independent report is useful finding evidence,
but its runner receipt is invalid (`postflight_failed`): the implementer created
the synthetic preview file while the review was running, which the runner
reported as a read-only workspace change. The reviewer itself made no edits.
Do not describe this first receipt as a passed review.

The P1 correction allows zero stories only when every selected source is
accounted for by omissions. Complete coverage renders a checked-scope no-news
statement; partial coverage states that no event was selected from the bounded
selection, never that the entire week was empty. Neither view redisplays noise.
Two end-to-end tests cover both coverage states, schema, persistence and the
full-view follow-up.

After the correction the dedicated command above passed **61 tests in 12.44s**.
A fresh scoped Role Runner recheck will run against the correction commit,
with the repository kept unchanged until its postflight completes. This is the
one required P1 recheck, not a repeated full programme/Deep Review.

## Independent recheck and comparison correction

The fresh runner receipt `20260919T155507Z-slice_review-0dfc89a0` is validated
and its `verify` command succeeded. Requested and recorded model/effort:
`gpt-5.6-terra` / `high`; reviewed SHA:
`f912046ee6d4af6d81b64eab618a1d736bf80481`.
Report SHA-256: `bdeae680c31bf9f53190d9e9623afce0fabf66cf2fbd939ffce6fe586320d3db`.
The workspace remained unchanged throughout this run. Verdict: `STOP_SHIP`.

It identified a second P1 in the neighboring comparison view: raw source
comparison could reintroduce items excluded by the saved editorial selection.
The correction compares only saved editorial stories, retaining their caveats
and source anchors. Matching uses headline and source identities; changed
wording is explicitly a saved-report change, not invented real-world change.
Noise-only comparisons stay empty. If only one report has editorial content,
comparison is unavailable rather than silently falling back to a source feed.
Four new tests cover both empty reports, selected events versus omitted noise,
changed wording, and a mixed editorial/unedited pair.

The focused tier at `f912046` passed **439 tests in 100.78s**. The dedicated
suite after the comparison correction is recorded in the final receipt below.
The remaining independent check is a scoped comparison-P1 recheck, not a new
programme design review or rollout approval. Human/provider/mobile gates are
unchanged and do not require another speculative review loop.

Dedicated editorial/brief/dialogue/synthesis command after the comparison fix:
**65 passed in 40.22s**. `git diff --check` and the PA plan consistency check
also passed. No statuses or approval artifacts were hand-edited.

## Bounded comparison presentation

The comparison recheck `20260919T160142Z-slice_review-e8496f71` reviewed
`b69f8f2794c6fabc20bdc270bbab61f926386c45`, recorded
`gpt-5.6-terra` / `high`, and has a validated, successfully verified runner
receipt. Its P1 was the maximum-size comparison: two changed reports could
produce too many Telegram chunks. At that SHA focused-prm passed **443 tests
in 93.85s**; passing tests did not cover that maximum shape.

The presentation correction appends whole story blocks within a 2400-character
comparison budget, retains caveats and up to two displayed source anchors per
story, and explicitly states how many sources/items are retained in the full
report rather than truncating links or presenting an apparently complete diff.
Expanded editorial views also have a bounded text budget and retain navigation
to unshown story numbers. Long escaped text is wrapped before escaping so
Telegram chunk boundaries do not cut HTML entities.

The new adversarial fixture constructs two five-story reports with eight anchors
per story, long escaped URLs and entity-heavy explanations. It checks that the
comparison remains useful and <=2400 characters; individual Telegram chunks
contain balanced HTML and full/item views fit the reserved send count. The
new fixture passed independently (1 passed in 1.96s); the dedicated four-file
suite passed 66 tests in 11.52s before the final two-link compacting adjustment.
The final focused tier and scoped delivery-bound recheck are recorded below.

## Source links and public comparison API

At `57b7e35592abc34aad31ffa3089251ac0e82d2e5`, focused-prm passed **444 tests
in 107.61s** (`/tmp/pa-editorial-focused-bounded-20260919.log`). The independent
run `20260919T160938Z-slice_review-3d155e8d` has a validated and verified receipt,
requested/recorded `gpt-5.6-terra` / `high`, and report SHA-256
`01b599cd357d5c628d1f3530901ef1a6c5d9bed343025b549a46a953ca83dc5e`.
Its `STOP_SHIP` report identified two remaining P1s: URLs longer than 240
characters were hidden even in full/item views, and the public store renderer
did not resolve a saved comparison companion.

The scoped correction preserves direct links in expanded views while keeping
compact projections bounded. The public API resolves only the saved exact
comparison reference through the same conversation history or authenticated
owner store; a caller-supplied companion cannot override that binding. Tests
exercise URLs of 261 and 500 characters, worst-case escaped links, comparison
before/after a store restart, foreign scopes and an unbound supplied companion.

The first new test run failed 2 cases because the synthetic response reference
did not follow the existing 24-hex contract (68 passed). The fixture was corrected
without changing the contract. The dedicated four-file command then passed
**70 tests in 12.90s**. `git diff --check` and the plan consistency checker passed.
The remaining recheck is scoped to these two P1s and the directly affected
delivery/ownership paths. Formal design, live-provider and human gates remain.

## Final code verification and independent scope receipt

Code SHA: `dbc87126fb88aa21e4af0f9ac643eeb1cea9fbda`.
`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm`
completed at that SHA with exit 0: **448 passed in 107.35s**. This tier includes
all 70 dedicated editorial/brief/dialogue/synthesis cases; no code changed
between their earlier dedicated receipt and the commit. Local log:
`/tmp/pa-editorial-focused-links-20260919.log`. The historical full suite was not run.

Independent run `20260919T162136Z-slice_review-bff8757a` reviewed that exact code
SHA with requested/recorded `gpt-5.6-terra` / `high`. Its runner receipt is
validated; `python3 tools/run_codex_role.py verify --root . --result
.playbook-artifacts/runs/20260919T162136Z-slice_review-bff8757a/result.json`
returned valid. Report SHA-256:
`ee0f0893e7a9d2be4e964653721974d8db5bff11423692386d6f71ce8308cb3d`.
The independent reviewer explicitly found both scoped code fixes sound. Its
overall verdict remains **STOP_SHIP**, with three findings:

- The focused receipt was not yet in the document the reviewer read. The
  concurrent writable-workspace run completed successfully, as recorded above.
  The reviewer's own pytest invocation could not create a temp file under its
  read-only sandbox; that failed invocation is not a passing receipt.
- The machine allowed_files omitted the specification and paired design paths
  changed under the owner's explicit programme integration direction. PA-07 now
  lists those three paths. This corrects the declared local scope; it changes no
  approval, slice status, runtime permission or implementation claim.
- Real private Telegram/mobile inspection is absent. This remains OPEN, along
  with real-provider and owner content acceptance, rather than being papered
  over with synthetic tests. This handoff publishes local implementation, not a
  release or a claim that PA-07/PA-08..15 are accepted.

Only evidence/scope/handoff documentation changed after the reviewed code SHA.
The final documentary recheck is limited to the first two findings; it must
preserve the third as an open acceptance gate.

Changed files relative to `1533fe0`:

- `src/prm/application.py`, `src/prm/archive_synthesis_transport.py`,
  `src/prm/brief_editorial.py`, `src/prm/briefs.py`, `src/prm/routing.py`.
- `schemas/assistant_brief_document.v1.schema.json`, `tools/test_tiers.py`.
- `tests/test_assistant_brief_editorial.py`, `tests/test_assistant_briefs.py`,
  `tests/test_assistant_report_dialogue.py`.
- `docs/CODEX_PROMPT.md`, `docs/PERSONAL_ASSISTANT_SPEC.md`, `docs/tasks.md`,
  `docs/design/PA.md`, `docs/design/PA.design.json`, `docs/design/PA-PRODUCT-QUALITY.md`.
- `docs/verification/PA-07-editorial-evidence-2026-09-19.md`,
  `docs/verification/PA-07-editorial-example-2026-09-19.md`,
  `docs/verification/PA-07-telegram-brief-user-judge-prompt.md`.

Next local verification command: `python3 tools/check_personal_assistant_plan.py`.
Next development work is the already-declared held-out content/conversation
scenarios and dependency-ready slices; no service, timer or live provider starts
as a consequence of this handoff.

## Final documentary recheck

Run `20260919T162628Z-slice_review-fd0cf1c0` reviewed
`744e209c584cdd92880725166538d1ac52a648a9` (documentation-only difference from
the reviewed/tested code checkpoint). Requested/recorded model and effort:
`gpt-5.6-terra` / `high`. The runner receipt is validated and its `verify`
command returned valid. Report SHA-256:
`170fdab94b3a17172cee4b58d35581a121793267a2ca26e0e375a7285cc8c4fb`.

The independent reviewer confirmed the prior documentary P1s resolved and the
plan/pin/diff checks passing. The overall verdict remains **STOP_SHIP**, solely
because actual provider/runtime, private Telegram/mobile and owner content
acceptance evidence is absent. That blocks acceptance/release, not publication
of this owner-authorized local implementation or independent local development.
There is no permission to obtain that evidence by starting live activity here.
Do not repeat an offline review to pretend this real-use gate is closed.

No code changed after `dbc87126fb88aa21e4af0f9ac643eeb1cea9fbda`; the final
handoff commit adds only this receipt and its current-session pointer. The
machine design remains `review_required`; no slice is marked complete.
