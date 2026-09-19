# PA-08 private BriefDocument report views — 2026-09-19

Status: local implementation and synthetic/offline verification recorded;
external acceptance gates remain open.
This record does not claim human visual acceptance, private Telegram/mobile
inspection, a live provider result, service activation, export delivery or
release approval. The PA design remains mechanically `review_required`.

## Implemented boundary

- `src/prm/report_exports.py` renders only an already constructed immutable
  `BriefDocument`. Every HTML, Markdown or PDF artifact carries the same exact
  brief ID, version, content digest and ordered source URL list. Rendering has
  no retrieval, model call, filesystem output, public URL, job or delivery
  adapter.
- HTML is static and sanitizes every document-derived text/attribute value.
  Its CSP denies scripts, connections, media, frames, forms, objects, images
  and external fonts. The validator rejects active tags, event handlers,
  untrusted links, inline style attributes and CSS resource imports/URLs.
  Long links use wrapping rules; responsive, dark and print/page-break rules
  are structural checks, not a claim of owner visual acceptance.
- Markdown contains escaped source text rather than raw HTML. It retains the
  same editorial event/takeaway/explanation/rationale/conditional next
  step/caveat, timeline, coverage and selected source content. There is no
  decorative chart because no measurement exists for one.
- PDF first uses the declared local WeasyPrint backend and forbids every
  resource fetch. In this environment WeasyPrint 62.3 imports but its installed
  pydyf 0.12.1 fails internally (`Stream.transform`), before producing a PDF.
  The narrow fallback embeds a local Unicode DejaVu Sans font and lays out the
  same saved document text in memory; it never fetches a resource or writes an
  artifact. This is local dependency-failure resilience, not a new provider or
  production runtime.
- `PrivateBriefReportReader` opens only a persisted exact PA-07 private owner
  tuple plus `(brief_id, version)`, issues an opaque process-local 20-minute
  handle, and rechecks owner, expiry and content digest before each render.
  Wrong/missing/mismatched owner tuples, forged versions, expired handles,
  restarts and unavailable retained history return no artifact. `preview_share`
  creates a content/recipient-label preview marked `preview_only_no_delivery`;
  it has no send path.

## Initial verification

- `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
  tests/test_assistant_report_exports.py tests/test_assistant_report_access.py
  tests/test_assistant_briefs.py tests/test_assistant_report_dialogue.py`:
  **32 passed**. The new tests use invented Cyrillic content, a 457-character
  HTTPS URL and temporary SQLite databases only. They check cross-format
  immutable identity/source preservation, static HTML/XSS/tracking rejection,
  exact owner/version/digest binding, expiry, restart denial and share preview
  non-delivery.
- `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
  tests/test_assistant_contracts.py`: **5 passed**.
- `python3 tools/check_personal_assistant_plan.py`: PASS; 19 consistent slices
  and unchanged `review_required` state.
- `python3 tools/playbook.py --check-pin`: PASS.
- `git diff --check`: PASS.

## Bound local verification

The code and test scope below is committed at
`4d574901986c1b44a0df1b38892bd9f533ac3bb3`; its implementation diff is
`31a9a92..4d57490`. Commands were run from the repository root on 2026-09-19,
with exit code 0:

- `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
  tests/test_assistant_report_exports.py tests/test_assistant_report_access.py`:
  **6 passed in 7.16s**. This is the task's direct command. It covers immutable
  cross-format identity/citations, Cyrillic and long URLs, sanitization,
  source-link annotations, forced fallback PDF, multiple fallback pages and
  exact owner/version/digest/expiry/restart denial.
- `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
  tests/test_assistant_report_exports.py tests/test_assistant_report_access.py
  tests/test_assistant_briefs.py tests/test_assistant_report_dialogue.py`:
  **34 passed in 12.92s**. This additionally checks the PA-07 document and
  report-dialogue dependencies.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py fast-contract`:
  **617 passed in 131.05s**. The historical full suite was not run.
- `python3 tools/playbook.py --check-pin`: PASS; no model, hook or application
  runtime enabled. `python3 tools/check_personal_assistant_plan.py`: PASS,
  19 consistent slices and unchanged `review_required` design state.
- `git diff --check`: PASS. The two pre-existing untracked local files remain
  unmodified and unstaged: `UTD_intelligence_layer_research_report.md` and
  `data/agent.db.pre-feedback-migration-20260821T122749.bak`.

The earlier initial runs remain useful diagnostics only: the initial direct
slice run had 32 passed and its earlier fast-contract run had 617 passed in
156.64s. The bound receipts above supersede them for the committed scope.

## Independent review trace

All slice reviews used the pinned Playbook Role Runner in fresh read-only
processes, requested as `gpt-5.6-terra` with `high` reasoning. The runner
observed that same model and effort, returned exit code 0, validated its trace
and confirmed an unchanged workspace.

- `20260919T182659Z-slice_review-6c3b8ca6` reviewed `85ffabf` against
  `31a9a92`, returned `STOP_SHIP` with P1 fallback-PDF link/footer and Markdown
  link defects. They were fixed in `06b5c2f`; report SHA-256:
  `09df29fcdec9b9956e21cbe87cf447b7c19c73daa1c5276d52478af5eb5f1745`;
  runner-result SHA-256:
  `5f3782aff2a84ccaa489b474760e26e002c0d4b6fb04ad1db85ac6918122f373`.
- `20260919T183307Z-slice_review-f31eb15d` reviewed `06b5c2f`, returned
  `STOP_SHIP` with a P1 Unicode-PDF URI defect. It was fixed in `0fffff8`;
  report SHA-256:
  `6a95d7a423bdd46daeac580d71034427fcca40dfa811a88cf54786c2558d9fbe`;
  runner-result SHA-256:
  `4747e47ac15a774c01eb265ba7b2a1fc8669ef35859cd8296c4b81e0bab4f9b2`.
- `20260919T183731Z-slice_review-651dd59b` independently rechecked
  `0fffff821e4fe71e23f18fa2d436ddb869b01d0f` against `31a9a92` and returned
  `ADVISORY`, with no P0/P1. It identified missing exact-SHA receipts and
  Test-Critic evidence, plus the still-open visual/runtime gate; those evidence
  gaps are addressed in this record and the runtime gate remains below. Report
  SHA-256: `0361875d4e05e63e2aefbaf237e5d3f189b74ae339163f91c2b093e4799c0918`;
  runner-result SHA-256:
  `269ed680aa021b76e1167433a28ff75d1db42db9ff3dcc7ba16432b050a5d4b6`.

A separate fresh read-only Test Critic process was requested as
`gpt-5.6-terra` / `high` for `31a9a92..0fffff8`. Its final report did not emit
independent model telemetry, so the observed identity is recorded as
unavailable rather than inferred. The report SHA-256 is
`15648e6731a99c57da052206a412bce8d1302efc0c70a710edd76cec2b69881d`.
It reported two evidence blockers and two test-oracle concerns: the first
evidence blocker is resolved by the bound receipts above; the digest-rebinding
and multipage-footer concerns are covered by the two added tests in `4d57490`.
Its remaining blocker is the external visual/runtime gate stated below. A
fresh Test Critic recheck is required after this evidence record is committed.

## Remaining external acceptance gate

PA-08 is not formally accepted or released. The required authorised private
HTML/PDF/mobile visual inspection, including real layout/overflow/page-break,
keyboard and owner-usefulness observations, has not occurred. It needs a
separate owner-authorised runtime session; this local task did not start a
service, use a Telegram account, call a provider, create an export delivery,
enable a timer, migrate a production database or deploy anything. The broken
local WeasyPrint/pydyf pairing makes that visual inspection especially material.
The design remains mechanically `review_required`.
