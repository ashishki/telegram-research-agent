# Evidence Index

Status: active
Last updated: 2026-07-29

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
| Product operating model | docs/PRODUCT_OPERATING_MODEL.md |
| PRM deep-review corrective log | docs/audit/PRM_DEEP_REVIEW_CONSOLIDATED_2026-07-27.md |
| PRM-18 release gate receipt | docs/audit/PRM18_RELEASE_GATE_2026-07-29.md |
| PRM runtime freeze receipt | docs/audit/PRM_RUNTIME_FREEZE_2026-07-29.md |
| PRM safe assistant runtime receipt | docs/audit/PRM_SAFE_ASSISTANT_RUNTIME_2026-07-29.md |
| PRM local memory ask receipt | docs/audit/PRM_LOCAL_MEMORY_ASK_2026-07-29.md |
| PRM LLM chat UX task block receipt | docs/audit/PRM_LLM_CHAT_UX_TASKS_2026-07-29.md |
| PRM-18 sanitized gate JSON | evals/prm18_release_gate_receipt_2026-07-29.json |

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
| python3 tools/verify_project.py --root . | fail, required_failures=1; project_tests: 1 failed, 1002 passed, 281 subtests passed in 324.77s; known failure: tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist |
| python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references | playbook_validate: errors=0 warnings=0 |
| git diff --check | pass, no output |

## PRM-18 Release Gate Evidence - 2026-07-29

| Command | Result |
| --- | --- |
| PYTHONPATH=src python3 -m pytest tests/test_prm_release_gate.py -q | 5 passed in 0.08s |
| python3 tools/test_tiers.py focused-prm | 99 passed, 6 subtests passed in 23.17s |
| python3 tools/test_tiers.py fast-contract | 152 passed, 6 subtests passed in 43.24s |
| python3 tools/verify_project.py --root . | fail, required_failures=1; project_tests: 1 failed, 1049 passed, 287 subtests passed in 412.02s (0:06:52); known failure: tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist |

PRM-18 release gate summary:

- receipt schema `prm_release_gate.v1`;
- dogfood gate `blocked`;
- release claimed `false`;
- dogfood started `false`;
- acceptance scenarios: 0 passed, 0 failed, 11 blocked;
- active stop-ship blockers: unsupported claims and retrieval metric failure;
- human dogfood-start approval is missing.

## Runtime Freeze Evidence - 2026-07-29

| Check | Result |
| --- | --- |
| `telegram-ai-split-report.timer` | stopped and disabled |
| `telegram-ai-split-report.service` | inactive after `reset-failed`; unit file remains disabled |
| `telegram-bot.service` | stopped and disabled |
| running Telegram Research Agent services | none found |
| active Telegram Research Agent timers | none found |
| `oc_you` crontab | no crontab |
| system cron project jobs | none found |

Historical W30 generated outputs remain under `data/output/` as private
artifacts. They were not read for content, committed, deleted, moved, archived,
or promoted to PRM dogfood evidence.

## Safe Assistant Runtime Evidence - 2026-07-29

| Check | Result |
| --- | --- |
| CLI entrypoint | `src/main.py prm-assistant` implemented |
| repo unit template | `systemd/telegram-prm-assistant.service` added |
| legacy bot compatibility | `src/main.py bot` still uses legacy runtime mode |
| ordinary text in safe mode | dispatches to chat command, not legacy message router |
| voice transcript in safe mode | dispatches to chat command, not legacy voice router |
| legacy callbacks in safe mode | disabled before DB write helpers run |
| legacy generation/write commands in safe mode | blocked by allowlist |
| safe runtime migrations | no automatic startup migration |
| activation state | not installed, not enabled, not started, not dogfood |

Targeted verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_cli.py tests/test_handlers.py tests/test_callbacks.py -q
52 passed, 3 subtests passed in 18.79s
```

Shared router/privacy tier:

```text
python3 tools/test_tiers.py fast-contract
204 passed, 9 subtests passed in 59.91s
```

Unit template verification:

```text
systemd-analyze verify systemd/telegram-prm-assistant.service
exit=0; unrelated host warning: /lib/systemd/system/snapd.service unknown RestartMode key
```

Pre-push checks:

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
pass, no output
```

No live Telegram ingestion, reaction sync, Radar, Frontier, report generation,
full archive indexing, embeddings, external web research jobs, systemd starts,
or production database writes were performed.

## Local Memory Ask Evidence - 2026-07-29

| Check | Result |
| --- | --- |
| user-facing command | `src/main.py memory ask "<question>"` implemented |
| scope controls | `--project`, `--week`, `--limit`, `--json` |
| default mode | local-only evidence brief |
| model calls | none |
| external search | none |
| startup migrations | none |
| writes | none |
| raw Telegram corpus egress | none |

Targeted verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_local_memory_ask.py tests/test_cli.py -q
13 passed, 3 subtests passed in 4.95s
```

CLI help smoke:

```text
PYTHONPATH=src python3 src/main.py memory ask --help
exit=0; help displayed memory ask options; retrieval was not run
```

PRM and shared contract tiers:

```text
python3 tools/test_tiers.py focused-prm
102 passed, 6 subtests passed in 14.58s
```

```text
python3 tools/test_tiers.py fast-contract
209 passed, 9 subtests passed in 52.30s
```

Pre-push checks:

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
pass, no output
```

No live Telegram ingestion, reaction sync, Radar, Frontier, report generation,
full archive indexing, embeddings, external web research jobs, LLM calls,
systemd starts, startup migrations, or production database writes were
performed.

## LLM Chat UX Task Block Evidence - 2026-07-29

| Check | Result |
| --- | --- |
| next task | PRM-18A Operator LLM Chat UX Contract |
| task block | PRM-18A -> PRM-18B -> PRM-18C before PRM-19 |
| dogfood state | still blocked; not started |
| provider egress | not approved by default |
| implementation boundary | fake LLM clients and fixture DBs until explicit approval |

Validation:

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
pass, no output
```

No live Telegram ingestion, reaction sync, Radar, Frontier, report generation,
full archive indexing, embeddings, external web research jobs, LLM calls,
systemd starts, startup migrations, or production database writes were
performed.
