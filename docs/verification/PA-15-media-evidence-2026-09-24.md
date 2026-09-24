# PA-15 — voice, images and documents (local evidence)

Date: 2026-09-24
Boundary: local, synthetic only. No OAuth, network call, token storage, default
database, provider, scheduler or delivery is enabled. No real media is
processed.

## Implemented

`src/prm/media_connectors.py`:

- `MediaAsset` with an explicit allowlist per kind (voice/image/document) and a
  defence-in-depth blocked-mime list (executables, archives, scripts); size
  (<=20 MB), page count, sha256 and expiry are bounded. Malicious, oversized or
  unsupported content is rejected before any adapter runs.
- `Transcription` is editable: `revise_transcription` produces a new version and
  the original is retained; provider ref and language stay visible.
- `ExtractedText` + `needs_ocr`: OCR is used only when a document's text layer is
  missing or below a threshold; images always need OCR. No unbounded OCR.
- `MediaQuestion` / `MediaAnswer` carry page and source references so an answer
  points back to the exact page/source.
- `plan_cleanup` returns an explicit temporary-cleanup plan (temp file, derived
  text, thumbnail, transcript) and `is_expired` enforces asset expiry.
- `require_media_egress_access`: one fail-closed PA-02 egress check shared by
  voice transcription, vision, document and speech. Each is a separate purpose
  (registered in `src/prm/capabilities.py`), so a grant for one cannot authorize
  another.

## Verification

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_media.py
# 6 passed

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 561 passed
```

The suite is registered in `focused-prm` (and therefore `fast-contract`).

## Remaining gates

Runtime verification remains: real transcription/vision/document/speech calls
against an authorized provider, real OCR quality, reliable temporary cleanup on
disk, and adversarial media (polyglot PDFs, oversized images, malformed audio)
against a live adapter. This slice is the local safety contract only.
