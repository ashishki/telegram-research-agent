# PRM Eval V2 Quality Pass

Date: 2026-08-15
Status: implementation quality pass complete

## Scope

This pass corrected PRM evaluation methodology and runtime verification
plumbing. It did not add a retrieval backend, start PRM-19 dogfood, claim
release readiness, run live Telegram ingestion, run live web research, or write
production database contents.

## Changes

- Added PRM-QA Eval V2 private dataset generation:
  source-cluster selection, semantic summaries without source names/rare terms,
  leak checks, pooled retrieval candidates, and separate pairwise relevance
  reviewer labels.
- Added PRM-QA Eval V2 runtime evaluator:
  it calls `_route_auto_message`, builds `OperatorContext`, executes retrieval,
  and verifies the actual rendered final answer.
- Added pre-synthesis claim ledger flow:
  evidence -> candidate claims -> approved claim ledger -> synthesis inputs.
- Added rendered-answer verification:
  final answer -> atomic claim extraction -> exact evidence snippets ->
  entailment verdict.
- Updated project-decision synthesis to use approved claims, project goal,
  current blocker, next proof, saved project decisions, one grounded
  recommendation, and one acceptance criterion.
- Integrated primary-source fetch results into the same claim-ledger/support
  comparison path.

## Verification

Focused checks run:

- `python3 -m py_compile src/assistant/claim_ledger.py src/assistant/memory_research.py src/assistant/professional_workflows.py src/assistant/primary_source_verification.py src/bot/handlers.py tools/prm_live_ux_eval.py tools/prm_qa_generate_private_eval_v2.py tools/prm_qa_eval_v2.py`
- `pytest -q tests/test_claim_ledger.py tests/test_primary_source_verification.py tests/test_memory_research.py tests/test_prm_qa_dataset_eval.py tests/test_prm_live_ux_eval.py` -> 47 passed
- `pytest -q tests/test_handlers.py tests/test_operator_context.py tests/test_prm_live_ux_eval.py` -> 93 passed
- `PYTHONPATH=src python3 tools/prm_live_ux_eval.py --cases 3` -> passed 3, failed 0
- `systemctl restart telegram-prm-assistant.service && systemctl is-active telegram-prm-assistant.service && systemctl show telegram-prm-assistant.service --property=ActiveState,SubState,MainPID --no-pager` -> active/running, MainPID=2932075

Full `pytest -q` was started, then stopped after operator instruction not to
run the full suite. It is not used as completion evidence for this pass.
Before interruption it had unrelated failures in project-intelligence tests;
those were not investigated in this scoped pass.

## Remaining Validation

Live runtime usefulness is still unproven. The next allowed validation remains
a controlled 15-20 question manual smoke session with operator labels:
Useful / Partial / Miss.
