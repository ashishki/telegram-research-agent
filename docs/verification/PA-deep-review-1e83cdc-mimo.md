# PA deep review (mimo-2.6-pro) — range `1a1ac5c..1e83cdc`

Independent, read-only review run through the OpenCode Go endpoint
(`tools/mimo_code_review.py`), model `mimo-v2.6-pro`, replacing the Codex
reviewer role for this programme. Reviewed SHA `1e83cdc`, diff SHA-256 and the
raw findings are in `PA-deep-review-1e83cdc-mimo.json`. Verdict:
`FIX_P1_FIRST` (no P0). Fixes below are applied in the follow-up commit.

## P1 — fixed

1. `confirmed_actions.execute_action` lost one-use/idempotency if the executor
   raised, and the store check was a check-then-act. **Fixed:** a pending
   receipt is atomically claimed (lock-guarded `claim`) before the provider call;
   an exception becomes an `unknown` outcome that requires reconciliation; a
   duplicate/concurrent click returns the existing receipt.
2. `editorial_transport` used one `maximum_request_count=1` reservation for a
   multi-attempt retry loop. **Fixed:** the access now carries a re-reservable
   budget; every attempt reserves and consumes a fresh bounded PA-02 decision,
   and the loop stops with `reservation_exhausted` when the budget is gone.
3. `brief_studio` recursively deleted a caller-supplied `--out-dir`. **Fixed:**
   it refuses to write into a non-empty directory it did not create; no delete.
4. `memory_library.confirm_preference` one-use was a non-atomic check-then-act.
   **Fixed:** one `BEGIN IMMEDIATE` transaction with a conditional
   `UPDATE ... WHERE consumed=0` (rowcount gate) plus the revision insert.
5. Academic dedup identity depended on the deadline calendar day (same item
   split across midnight). **Fixed:** identity is `(source_kind, casefolded
   title)`; deadline instants are unioned and surfaced as conflicts.
6. `profile_ranked_brief --send` performed a live Telegram delivery with no
   consent. **Fixed:** `--send` now requires the exact
   `--send-consent send-to-owner-telegram` literal.

## P2 — fixed

7. Provider base URL was not validated before sending the bearer key.
   **Fixed:** `editorial_transport` and `mimo_code_review` require an `https`
   OpenCode host (`opencode.ai`) and fail closed otherwise.
8. Fixed-page renderer could silently clip content via `overflow:hidden`.
   **Fixed:** a more conservative height estimate and an explicit
   `page_overflow` error when a single card cannot fit a page.
9. `MemoryLibraryStore` leaked SQLite connections. **Fixed:** all connections
   use `contextlib.closing`.

## P2 — not a defect

10. `voice.transcription` purpose is already registered
    (`provider_openai`/`media.transcribe`/`model_egress`) in
    `capabilities.py`; the finding was a false positive.

## Not verified (reviewer)

Live wiring of adapters, actual pytest counts, WeasyPrint/Chrome rendering, and
whether a future adapter calls the `require_*_access` guards before `fetch_page`.
These are the open runtime gates, unchanged by this review.
