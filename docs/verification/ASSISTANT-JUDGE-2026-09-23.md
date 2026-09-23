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
   Renders an HTML view to PNG with headless Chrome (view presets
   `telegram_mobile`, `html_mobile`, `html_desktop`, `pdf_page`) or accepts an
   existing PNG, then sends the image plus redacted metadata to the vision
   model. Scores readability, hierarchy, scanability, spacing, contrast,
   mobile fit, source clarity, completeness; flags `text_cropped`,
   `horizontal_overflow`, `overlapping`, `low_contrast`, `missing_hierarchy`,
   `broken_table`, `tiny_text`. Any layout failure fails closed. A 0..10 reply
   is rescaled to 1..5 (documented slippage).

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

These probes prove the mechanics, not content acceptance. Real archive answers
and the generated weekly brief still need an owner-authorized run with
sanitized/redacted inputs.

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
