# Assistant judge layer — mechanics and first probes

Date: 2026-09-23
Status: owner-directed evaluation tooling. Advisory only: it never grants
runtime, account, release or design approval, and it is not a substitute for
runtime evidence or owner visual review.

## Provider

All three judges use the operator-owned OpenCode Go endpoint
(`https://opencode.ai/zen/go/v1`, OpenAI-compatible, key = `OPENCODE_API_KEY`,
local file historically named `openrouter_api_key`). They fail closed without
`--allow-provider-egress` and a resolved key, and never fall back to an
`OPENROUTER_*` credential for this endpoint. Keys are never logged or committed.

Models (verified 2026-09-23):
- text judge: `mimo-v2.6-pro` (rejects image content);
- visual judge: `deepseek-v4-flash-vision-exp` (accepts OpenAI-style
  `image_url` data URLs; verified by reading a synthetic 64x64 image).

## Layers

1. Text/product-UX judge — `tools/prm_product_ux_eval.py`
   (`--provider opencode-go`). Sends a redacted case payload per call:
   `judge_role`, `expected_assistant_behavior`, `deterministic_summary`, and
   per-turn `user_message`, `assistant_visible_message`, `expected`, `actual`,
   `deterministic_checks`, `failure_codes`. Scores 10 fields (1..5) plus
   boolean flags; privacy/unsafe findings fail closed.

2. Text answer/brief judge — `tools/assistant_answer_judge.py`.
   Reads JSONL cases (`mode in archive|brief|chat`) with `user_request`,
   `assistant_answer`, `evidence_refs`. Scores groundedness, source fidelity,
   no-fabrication, usefulness, completeness, clarity, priority honesty,
   editorial synthesis, follow-up and safety boundary. Flags
   `unsupported_claim`, `citation_missing`, `negation_flipped`,
   `invented_deadline`, `overclaims_coverage`, `privacy_boundary_violation`.
   Critical flags or privacy findings fail closed.

3. Visual/layout judge — `tools/assistant_visual_judge.py`.
   Accepts `--html` (rendered to PNG with headless Chrome), `--image`
   (existing PNG/JPG), or `--pdf` (inspected and rasterized page-by-page with
   `src/prm/pdf_inspection.py`, `pypdfium2`), then sends each page image plus
   redacted metadata to the vision model. Scores readability, hierarchy,
   scanability, spacing, contrast, mobile fit, source clarity, completeness;
   flags `text_cropped`, `horizontal_overflow`, `overlapping`, `low_contrast`,
   `missing_hierarchy`, `broken_table`, `tiny_text`. Any layout failure fails
   closed. A 0..10 reply is rescaled to 1..5 (documented slippage).

4. Deterministic PDF inspection — `src/prm/pdf_inspection.py` (`pypdf`).
   Runs offline and never uploads the document. Reports page count, text-layer
   presence, replacement-character (tofu) count, https vs non-https links,
   embedded fonts, and case-insensitive `--expect` substring coverage.
   Failures (`empty`, `no_text_layer`, `replacement_chars`,
   `missing_expected:...`, `non_https_links`, `too_many_pages`, `encrypted`)
   force `failed_closed` even when the vision judge passes.

## What is sent (and not)

- Sent: redacted requests/answers, bounded metadata, source URLs reduced to
  hosts, and (visual only) the rendered image bytes in-memory.
- Not sent: the raw private archive/corpus, attachments, account IDs, tokens,
  credentials or raw DB rows.
- Public reports record verdicts, scores, risk tags and image SHA-256 — never
  the image bytes or a private path. Detailed datasets are git-ignored.

## First probes (synthetic only)

- `tools/assistant_visual_judge.py` on a synthetic mobile brief render:
  `warn`, contrast 3/5, tags `low_contrast_caveat`, `tiny_footer_text`; fix
  "сделайте нижнюю сноску контрастнее и крупнее" — the model caught a real
  low-contrast footer.
- `tools/assistant_answer_judge.py` on two synthetic cases: both `fail` with
  `unverifiable_citation`/`invented_deadline` because the synthetic references
  do not support the claims — the expected strict behaviour.
- `tools/assistant_visual_judge.py --pdf` on a synthetic brief PDF rendered by
  weasyprint: page rasterized, text layer present (769 chars), 3 https links,
  0 non-https, DejaVu fonts embedded; vision judge `pass` (all scores 4-5) but
  a missing `--expect` substring forced `failed_closed` — the layered gate
  behaved correctly.

These probes prove the mechanics, not content acceptance. Real archive answers
and the generated weekly brief still need an owner-authorized run with
sanitized/redacted inputs.

5. Telegram dialogue renderer — `tools/assistant_visual_judge.py --dialogue`.
   Converts a dialogue JSON (`{title, turns:[{role,text,buttons,sources}]}`) to
   a Telegram-like private-chat HTML (correct bubble sides, chips, sources),
   screenshots it at `telegram_mobile` and judges it with the same vision
   rubric, now including bubble alignment and button-chip clarity
   (`confusing_controls`).

6. External SotaOCR cross-check — `tools/pdf_ocr_crosscheck.py` (owner-approved
   2026-09-23). Uploads one PDF to `https://sotaocr.com/v1/extract`, polls the
   job and fetches the OCR text (`--format markdown|json|...`), then checks that
   expected substrings survive rendering (case-insensitive). Fail-closed: needs
   `--allow-provider-egress` *and* `--i-understand-third-party-upload` plus a
   key (`--api-key-file`, default `/srv/openclaw-you/secrets/sotaocr_api_key`).
   The OCR text is never written to the report — only length, SHA-256 and the
   missing list. This is the only layer that sends a document to a third party.

## External OCR evidence

`tools/pdf_ocr_crosscheck.py` on the synthetic brief PDF: uploaded, OCR
returned 899 chars, reproduced "Еженедельный бриф" and "Дедлайн", correctly
flagged the injected "ЭТОГО НЕТ" as missing → `failed_closed`.

Telegram dialogue probe: rendered chat judged `pass`, "бабблы на своих
сторонах, источник и кнопки видимы, текст хорошо читается".

## Real-brief experiment (owner-authorized)

A real brief was generated locally from the operator archive (read-only, no
provider, no write): 8 items, 8 evidence, status `partial`; PDF 38 KB, 9 pages,
7161 text chars, 0 replacement chars, 24 https links, embedded DejaVu fonts.
SotaOCR cross-check: 8088 chars, no missing expected text — the text layer is
sound, so the problems are layout, not copyability.

Vision judge on the 9 PDF pages found: tiny body text, no running page
header with period/section, an orphaned section heading at a page bottom, and
a large empty block at the end.

`src/prm/report_exports.py` now adds a running print header/centre
(title + section + period via CSS `string-set`), `break-after: avoid` on
headings and `break-before: avoid` on content after a heading, `orphans/widows`
and a trailing-section border fix, host-label source links in the coverage
table (no mid-word URL breaks), a slightly larger source-card/timeline font,
and a caveat instead of an empty sources grid.

Measured across repeated runs the layout converges (e.g. 6 pass / 2-3 warn,
layout failures 0-1), but **the vision judge is noisy**: identical-PDF runs
gave different verdicts, and one recurring "orphaned "Проверяемые основания"
heading on page 5" was not reproducible in the extracted text (page 6 starts
with the heading immediately followed by a source card). Treat vision output as
hypotheses and confirm each against `pdf_inspection` text before acting; the
deterministic checks are the reliable gate.

Telegram view of the same real brief (353 chars, HTML) judged `pass` with one
real product fix: it is too thin — add inline summary items and at least one
source link in the card instead of hiding everything behind a button.

## Designed analytical format (`render_designed_html` / `render_designed_pdf`)

A second, richer layout was added: cover, KPI blocks (items/sources/conflicts/
coverage), a deterministic inline-SVG bar chart of observations per day, then
the same facts/sources. It uses only inline SVG (no external resources) and
passes the same `validate_report_html` safety contract.

First real run (6 pages) failed on: KPI labels overlapping values (WeasyPrint
grid), an empty "Динамика" section (SVG with no intrinsic size + orphan
heading), and the running header duplicating the cover. Fixes: flex KPIs,
explicit SVG width/height and `h2 + svg { break-before: avoid }`, `@page:first`
suppresses the running header, larger margins, darker/slightly larger running
text, and no mid-word breaks in KPI text. Second run: overlap gone, fails 2 → 0,
all pages pass/warn. Remaining nits: muted header contrast, long identifiers in
the coverage table, and an empty block on the last page — plus the known vision
noise.

## Model editorial pass + brief studio (`tools/brief_studio.py`)

The studio builds a real BriefDocument from the local archive (read-only),
optionally drafts editorial stories with the OpenCode Go model, then writes
standard + designed HTML/PDF/Markdown, Telegram text and a dialogue JSON. The
model draft is validated by `BriefEditorial.from_dict`; invalid tries are
retried with the validation error fed back, and a tolerant parser accepts code
fences and literal newlines inside strings (a common model failure).

Results on the real archive brief: editorial drafted on attempt 2 (5 stories),
no deterministic failures, no tofu; standard PDF 12 pages / 13062 chars,
designed PDF 10 pages / 10339 chars, Telegram text 1220 chars.

Telegram view of the editorial brief: vision `pass`, all scores 5/5 — "пузыри
на своих сторонах, структура с заголовками и источниками, кнопки видимы"
(up from the earlier thin 353-char pass). Fixed a real period bug: the header
showed a duplicated "UTC" (`… UTC — … UTC; UTC`) and now renders in the window
timezone with the zone name once.

Still open: WeasyPrint can still orphan a section heading above a large
`break-inside: avoid` story block; the coverage-table identifiers stay long.

## Content transformation (what the brief actually shows)

Two modes, deliberately distinct:
- **Deterministic** (`render_brief_document` without editorial): item text is a
  bounded `support_span`/`snippet` copied from the selected archive post — an
  excerpt, not a rewrite. The designed export now labels this honestly
  ("Выдержки из источников (без редакторской переработки)").
- **Editorial** (model pass): the model rewrites titles/summaries/explanations,
  but `BriefEditorial.from_dict` enforces exact verbatim quotes from the source,
  no new numeric claims, one anchor binding per story and every source either
  used or omitted. So it is a summary without meaning loss and without invented
  facts. This is the intended default for a real brief.

## Designed layout iteration and the pagination finding

Added a top-sources bar chart, a cover pull-quote (first story summary), an
honest non-editorial label, and meaningful source labels (e.g. `@channel/post`
instead of a bare `t.me`). The cover no longer forces a page break and stories
flow after it, which removed the orphaned "Главное" heading.

Best run: 8 pages, 0 layout failures, `needs_human_review` (3 pass / 5 warn).
Across runs the vision judge swings between 0 and 2 layout failures on the same
document, and the recurring real defects are structural: a nearly-empty page
when a `break-inside: avoid` story block is pushed past a page boundary, and an
empty trailing block on the last page.

Conclusion: WeasyPrint/Chrome **flow pagination is the wrong tool** for a
magazine-grade PDF. Reaching the red_mad_robot reference needs **explicit
fixed-page composition** (place content into A4 page containers in code, so
there are no orphan headings or empty fragments), not more CSS tuning. A Chrome
`--print-to-pdf` path is available in the studio (`--chrome-pdf`) but scored the
same, confirming the issue is composition, not the engine.

## Fixed-page composer (`render_paginated_html` / `render_paginated_pdf`)

Implemented the fixed-page approach: the renderer packs content into explicit
A4 `.page` containers (cover, story pages, coverage page, source pages), each
with its own running head and page number, `break-inside: avoid` and
`height: 297mm`, so the engine never paginates and no heading can be orphaned.
Density is adaptive (one large editorial story per page; three bounded excerpt
cards per page; two sources per page) and validated against real PDFs so pages
do not spill.

Results on the real archive brief: best run 12 pages, **0 layout failures**,
7 pass / 5 warn; non-editorial run 9 pages, 5 pass / 4 warn, layout 1. Mean
scores now all ≥ 4 (contrast 4.9, readability 4.75 on the best run). The cover
carries a table of contents and the observations chart, so it is full; the
source chart is merged onto the coverage page. Remaining warns are minor
(chart has no axis scale, short pages leave whitespace on 2-source pages, a
long table identifier breaks) and the usual vision noise.

## How to run

```bash
KEY=/srv/openclaw-you/workspace/Georgia-Community-Navigator/secrets/openrouter_api_key
PYTHONPATH=src python3 tools/assistant_visual_judge.py --allow-provider-egress \
  --judge-api-key-file "$KEY" --html path/to/brief.html --view telegram_mobile
PYTHONPATH=src python3 tools/assistant_answer_judge.py --allow-provider-egress \
  --judge-api-key-file "$KEY" --cases evals/assistant_judge/answer_cases.v1.jsonl
PYTHONPATH=src python3 tools/prm_product_ux_eval.py --provider opencode-go \
  --allow-provider-egress --judge-api-key-file "$KEY" --max-judge-cases 12
```

## Open items

- Real-output cases (archive answers + generated weekly brief) and an
  owner-rated holdout are not yet built.
- Vision model is `deepseek-v4-flash-vision-exp`; the text model is not
  vision-capable, so the two layers cannot share one model.
- Screenshot sources (Telegram mobile vs HTML mobile/desktop vs PDF) and
  numeric thresholds still need owner calibration.
