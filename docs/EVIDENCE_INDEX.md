# Evidence Index

Status: active
Last updated: 2026-07-27

## Repository State

| Evidence | Value |
| --- | --- |
| Target repository commit inspected | ad8689fa25b89f77122c4cec7c7a6b9da3f500cf |
| Target branch before edits | master |
| Target git status before edits | clean |
| Playbook commit used | 5583eca96c4d2d480b5574ed78bea63e0b07ebf0 |
| Playbook branch | master |
| Playbook git status | clean |

## Local Audit Evidence

| Evidence | Location |
| --- | --- |
| Product pivot current-state audit | docs/product_pivot_current_state_audit.md |
| Playbook differential audit | docs/playbook_retrofit_audit.md |
| Product pivot ADR | docs/adr/ADR-001-product-pivot-to-personal-research-memory.md |
| Product contract | docs/personal_research_memory_product_contract.md |
| Architecture | docs/ARCHITECTURE.md |
| RAG data readiness contract | docs/RAG_DATA_READINESS.md |
| Retrieval evaluation contract | docs/retrieval_eval.md |
| Final acceptance plan | docs/final_acceptance_plan.md |
| Privacy threat model | docs/PRIVACY_THREAT_MODEL.md |
| Cost budget | docs/COST_BUDGET.md |
| Rollback and reindex plan | docs/ROLLBACK_AND_REINDEX_PLAN.md |
| Test strategy and tiers | docs/TEST_STRATEGY.md |
| PRM deep-review corrective log | docs/audit/PRM_DEEP_REVIEW_CONSOLIDATED_2026-07-27.md |

## W29 Artifact Evidence

The audited local W29 run is
data/output/weekly_intelligence_runs/tra-weekly-2026-W29-20260720T050229508302Z-978f44004e97/.

Verified facts recorded in docs/product_pivot_current_state_audit.md include:

- manifest schema weekly_run_manifest.v1 with partial run status;
- Brief and Atlas schema split_ai_report.v1;
- contract version tra-intelligence-contract.v1;
- seven personal reaction events and seven resolved posts;
- zero linked atoms, zero linked themes, zero selected item effects;
- Radar stage failure while Brief and Atlas still rendered;
- Project Intelligence produced no concrete project decisions;
- PI assistant retrieval excludes raw Telegram archive search.

## Validation Evidence

| Command | Result | Evidence |
| --- | --- | --- |
| python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references | pass, errors=0 warnings=0 | .playbook-artifacts/project_verification/playbook_contract/stdout.txt |
| python3 tools/verify_project.py --root . | fail, required_failures=1 | .playbook-artifacts/project_verification.json |
| /usr/bin/python3 -m pytest tests/ -q | fail, 963 passed, 1 failed, 281 subtests passed | .playbook-artifacts/project_verification/project_tests/stdout.txt |
| git diff --check | pass, no output | terminal run after final verifier |
| git diff --stat | pass, tracked-file stat showed 9 changed tracked files, 1753 insertions, 4160 deletions; untracked created docs/tools/schemas/evals are listed by git status, not diff stat | terminal run after final verifier |

Remaining test failure:

- tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist expected both ops validation checks to pass, but both returned needs_live_event. The fixture seeds evidence at 2026-07-08T10:00:00Z and calls validate_ops with days=14. On the current date, 2026-07-27, those rows are outside the 14-day validation window. This corrective change set did not alter product ops validation.

## PRM Corrective Review Evidence - 2026-07-27

| Command | Result |
| --- | --- |
| codex -a never -C /tmp/prm-review-repo.7UcDnW exec -s read-only -m gpt-5.5 -c model_reasoning_effort='high' -o /tmp/prm_meta_review.md | PACKET_REVIEW_RESULT: ISSUES_FOUND |
| codex -a never -C /tmp/prm-review-repo.7UcDnW exec -s read-only -m gpt-5.5 -c model_reasoning_effort='high' -o /tmp/prm_arch_review.md | PACKET_REVIEW_RESULT: ISSUES_FOUND |
| codex -a never -C /tmp/prm-review-repo.7UcDnW exec -s read-only -m gpt-5.5 -c model_reasoning_effort='high' -o /tmp/prm_code_review.md | PACKET_REVIEW_RESULT: ISSUES_FOUND |
| PYTHONPATH=src python3 -m pytest tests/test_archive_retrieval_eval.py tests/test_pi_chat.py -q | 16 passed in 1.47s |
| PYTHONPATH=src python3 -m pytest tests/test_test_tiers.py -q | 3 passed in 0.06s |
| python3 tools/test_tiers.py focused-prm | 49 passed in 2.36s |
| python3 tools/test_tiers.py fast-contract | 102 passed in 28.36s |
| python3 tools/test_tiers.py ops-date-sensitive | 1 failed, 3 passed in 3.86s; known failure: tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist |
| python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references | playbook_validate: errors=0 warnings=0 |
| git diff --check | pass, no output |
