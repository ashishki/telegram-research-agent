# PRM-SN Phase 1 implementation checkpoint — 2026-09-17

Scope: PRM-SN-1A, PRM-SN-1B, PRM-SN-1C. This is implementation and local
fixture evidence only; it is not a phase-review receipt, pilot authorization,
runtime observation, human-label result, or release claim.

## Changes

- Final-answer verification binds a visible citation to the evidence item with
  that exact URL. A missing or wrong URL no longer falls back to lexical source
  matching. It records citation integrity separately from URL formatting.
- Short factual clauses are extracted, verification records a bounded-tail
  condition, and free synthesis is rejected when a factual clause is
  unsupported, citations do not bind, or verification is incomplete.
- Deterministic slot checks reject audited number, negation, and English actor
  mutations without claiming general semantic/NLI coverage. Archive contract
  rendering remains the source-attributed deterministic fallback.
- An archive question that also asks a concrete current fact retains its local
  archive answer, prefixes a precise unverified-current boundary, and does not
  claim the current fact. A lone archive-scoped `сейчас` remains local.

## Local verification

Command (no production DB, provider, Telegram send, migration, timer, or
external request):

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  tests/test_claim_ledger.py tests/test_prm_synthesis.py \
  tests/test_prm_application.py tests/test_prm_bot_dispatch.py \
  tests/test_prm_intent_archive_contract.py -q
git diff --check
```

Latest observed focused result: `45 passed in 3.05s`; whitespace check passed.

## Concrete fixture outputs covered

- Correct archive answer: `В архиве найдено …` with source URLs from the
  selected archive contract.
- Wrong visible citation: `https://example.invalid/wrong` yields an unsupported
  final claim and `citation_integrity=0.0`; no different source is substituted.
- Mixed request: `Что в моём архиве … и какая сейчас текущая цена Nvidia?`
  renders `Текущий внешний факт не подтверждён … ниже — только архивная часть
  вопроса`, followed by archive results; no price is asserted.

## Known limits and rollback

The deterministic critical-slot checks are not a general semantic verifier;
free paraphrases outside their evidence scope retain the safe fallback. Human
labels, live provider behavior, external verification, runtime latency/cost and
operator usefulness remain unmeasured. Rollback retains source-attributed
archive rendering and disables free synthesis rather than restoring a false
verification pass.

## Next gate

PRM-SN-DR-1 passed its final independent read-only engineering closure review.
The sanitised provenance, findings, corrections, final working-diff identity and
residual non-engineering gates are recorded in `PRM_SN_DR1_2026-09-17.md`.
