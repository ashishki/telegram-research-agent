# PA-08 private BriefDocument report views — 2026-09-19

Status: local implementation and synthetic/offline verification in progress.
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

## Complete local verification

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py fast-contract`
completed with exit 0: **617 passed in 156.64s**. The historical full suite was
not run. This is the PA-08 regression floor; the new slice tests above are its
specific acceptance evidence.

The exact scoped commit and independent Terra/high review receipt are recorded
below once the current coherent patch is committed. The two pre-existing
untracked local files remain unmodified and unstaged.
