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
  regression passes in the dedicated suite. The full focused recheck is running.
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
