# Evidence Index

Status: active
Last updated: 2026-08-11

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
| PRM-18 post-PRM28 release gate receipt | docs/audit/PRM18_RELEASE_GATE_POST_PRM28_2026-08-11.md |
| PRM local UX trial receipt | docs/audit/PRM_LOCAL_UX_TRIAL_2026-08-11.md |
| PRM runtime freeze receipt | docs/audit/PRM_RUNTIME_FREEZE_2026-07-29.md |
| PRM safe assistant runtime receipt | docs/audit/PRM_SAFE_ASSISTANT_RUNTIME_2026-07-29.md |
| PRM local memory ask receipt | docs/audit/PRM_LOCAL_MEMORY_ASK_2026-07-29.md |
| PRM LLM chat UX task block receipt | docs/audit/PRM_LLM_CHAT_UX_TASKS_2026-07-29.md |
| PRM architecture research prompt | docs/prompts/prm_architecture_research_agent.md |
| PRM-18 historical sanitized gate JSON | evals/prm18_release_gate_receipt_2026-07-29.json |
| PRM-18 current post-PRM28 sanitized gate JSON | evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json |

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
| ordinary text in safe mode | dispatches to local-only research command, not legacy message router |
| voice transcript in safe mode | dispatches to local-only research command, not legacy voice router |
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

## LLM Chat CLI Evidence - 2026-08-03

| Check | Result |
| --- | --- |
| completed task | PRM-18B LLM-Backed Memory Chat CLI |
| one-shot approved command | `src/main.py memory ask --llm-approved --allow-provider-egress "<question>"` implemented |
| one-shot missing approval | refuses with exit code `2` before PI chat/provider execution |
| interactive command | `src/main.py memory chat --allow-provider-egress` implemented |
| display contract | `prm_chat_display.v1`, no raw PI tool payload dump |
| local-only privacy line | `memory ask` prints `mode=local-only` privacy/cost line |
| model/provider behavior in tests | fake clients only; no live provider calls |
| writes | no direct chat writes except existing exact-token `confirm_save_proposal` path |

Targeted verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_local_memory_ask.py tests/test_pi_chat.py tests/test_cli.py -q
37 passed, 9 subtests passed in 9.10s
```

PRM tier:

```text
python3 tools/test_tiers.py focused-prm
103 passed, 6 subtests passed in 24.45s
```

Shared contract tier:

```text
python3 tools/test_tiers.py fast-contract
214 passed, 9 subtests passed in 178.11s (0:02:58)
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
full archive indexing, embeddings, external web research jobs, live LLM
provider calls, systemd starts/enables, startup migrations, production database
writes, or compatibility deletes/archives were performed.

## Linked Source Research Layer Evidence - 2026-08-03

| Check | Result |
| --- | --- |
| completed task | PRM-22 Linked Source Research Layer |
| implementation | `src/assistant/linked_sources.py` fixture-first resolver/cache |
| focused tests | `tests/test_linked_sources.py` covers extraction/classification, sanitized cache records, and approval refusal paths |
| test tier | `tools/test_tiers.py focused-prm` includes linked-source coverage |
| dogfood boundary | not PRM-19 evidence; no service start or runtime dogfood |
| live operations | none; no live HTTP fetch, external skill, provider call, embeddings/vector backend, production DB write, migration, or durable production cache write |

Verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_linked_sources.py -q
3 passed in 1.50s
```

```text
python3 tools/test_tiers.py focused-prm
106 passed, 6 subtests passed in 24.43s
```

```text
python3 tools/test_tiers.py ops-date-sensitive
4 passed in 5.05s
```

```text
python3 tools/verify_project.py --root .
PASS: playbook_contract exit=0
PASS: project_tests exit=0
1083 passed, 291 subtests passed in 465.66s (0:07:45)
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
pass, no output
```

## Telegram PRM Assistant UX Evidence - 2026-08-03

| Check | Result |
| --- | --- |
| completed task | PRM-18C Telegram PRM Assistant UX Parity And Start Runbook |
| safe-mode start/help | states local-only CLI mode, approved LLM/provider-egress mode, safe read-only commands, blocked legacy commands, and dogfood-not-started status |
| Telegram chat output | uses shared PRM chat renderer with answer, sources, archive support, unknowns, write status, and privacy/cost line |
| raw tool payload exposure | handler tests assert fake raw tool snippet is not sent |
| runbook | docs/operator_workflow.md and docs/PRODUCT_OPERATING_MODEL.md document preflight, install/start/status, stop/disable, and rollback |
| service activation | not installed, enabled, started, or treated as dogfood |

Targeted verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_handlers.py tests/test_callbacks.py tests/test_cli.py -q
58 passed, 3 subtests passed in 50.50s
```

Unit template verification:

```text
systemd-analyze verify systemd/telegram-prm-assistant.service
exit=0; unrelated host warning: /lib/systemd/system/snapd.service unknown RestartMode key
```

Shared contract tier and pre-push checks:

```text
python3 tools/test_tiers.py fast-contract
214 passed, 9 subtests passed in 178.11s (0:02:58)
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
pass, no output
```

No live Telegram ingestion, reaction sync, Radar, Frontier, report generation,
full archive indexing, embeddings, external web research jobs, live LLM
provider calls, systemd starts/enables, startup migrations, production database
writes, or compatibility deletes/archives were performed.

## Research Session Assistant Contract Evidence - 2026-08-03

| Check | Result |
| --- | --- |
| completed task | PRM-21 Project-Aware Research Session Contract |
| contract | docs/personal_research_memory_product_contract.md |
| task graph | docs/tasks.md |
| implementation boundary | PRM-22 fixture-first linked-source resolver/cache and PRM-23 bounded fixture-first `memory research` planner/CLI are implemented |
| RAG boundary | RAG is necessary but not sufficient; SQLite FTS remains baseline and PRM-8 vector/hybrid adoption remains blocked |
| dogfood boundary | not current PRM-19 evidence; `memory research` is local fixture-first and not dogfood/runtime evidence |
| live operations | none |

Verification:

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
pass, no output
```

No live Telegram ingestion, reaction sync, Radar, Frontier, report generation,
full archive indexing, embeddings, external web research jobs, live LLM
provider calls, systemd starts/enables, startup migrations, production database
writes, or compatibility deletes/archives were performed.

## Bounded Memory Research Planner Evidence - 2026-08-03

| Check | Result |
| --- | --- |
| completed task | PRM-23 Bounded Memory Research Planner |
| implementation | `src/assistant/memory_research.py` deterministic local planner and `src/main.py memory research` CLI |
| focused tests | `tests/test_memory_research.py` covers polished answer shape, budget/open-browsing refusal, all project labels including `ambiguous_project`, and confirmation-gated drafts |
| CLI tests | `tests/test_cli.py` covers parser/handler wiring, no startup migrations, and refusal exit code |
| test tier | `tools/test_tiers.py focused-prm` includes memory-research coverage |
| dogfood boundary | not PRM-19 evidence; no Telegram service start or runtime dogfood |
| live operations | none; no live HTTP fetch, external skill, provider call, embeddings/vector backend, migration, production DB write, durable production cache write, or compatibility archive/delete/move |

Verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_memory_research.py -q
7 passed, 4 subtests passed in 2.91s
```

```text
PYTHONPATH=src python3 -m pytest tests/test_cli.py -q
17 passed, 3 subtests passed in 5.29s
```

```text
python3 tools/test_tiers.py focused-prm
113 passed, 10 subtests passed in 36.62s
```

```text
python3 tools/verify_project.py --root .
PASS: playbook_contract exit=0
PASS: project_tests exit=0
1083 passed, 291 subtests passed in 465.66s (0:07:45)
```

## Deterministic Archive Query Planner Evidence - 2026-08-06

| Check | Result |
| --- | --- |
| implementation | `memory research` archive search now plans up to 4 deterministic short SQLite FTS variants per user question |
| receipt visibility | the archive tool receipt records `query_variants`, attempted queries, raw item counts, and locally accepted item counts |
| project boundary | `--project` is treated as a project-context hint, not a hard archive FTS filter |
| acceptance filter | multi-term variants require local snippet/source confirmation before an item is admitted as archive evidence |
| before eval | 30 imitated natural user questions through the previous full-question archive path produced 0/30 archive-hit questions; 20 manual short rewrites produced 18/20 direct FTS hits |
| after eval | the deterministic planner plus acceptance filter produced accepted archive evidence for 15/30 imitated questions |
| interpretation | SQLite FTS is usable for anchored terms, but natural product questions still miss linked-source, freshness, provider-egress, MVP-radar, and some project-specific requests |
| RAG boundary | this is evidence for a future retrieval layer evaluation; it is not vector/backend adoption approval |
| live operations | none; no live HTTP fetch, external skill, provider call, embeddings/vector backend, migration, production DB write, dogfood start, or compatibility archive/delete/move |

## PRM-24 Prepared Gold-Label Drafts - 2026-08-09

| Check | Result |
| --- | --- |
| draft file | `evals/retrieval/product_rag_gold_label_drafts.jsonl` |
| contents | 7 proposed no-answer/external-verification outcomes for operator review |
| approval state | every draft has `human_approved=false`; no `human_approval_ref` is present |
| gate impact | none; the manifest/scorer reads only `product_rag_gold_labels.jsonl`, which remains empty |
| boundary | no live archive read, external research, provider egress, embeddings, migrations, production writes, service start, or dogfood |

## PRM-24 Non-Gating Draft Simulation - 2026-08-09

| Check | Result |
| --- | --- |
| receipt | `evals/retrieval/product_rag_simulation_manifest.json` |
| scenario coverage | 7 drafts: 6 proposed no-answer outcomes and 1 external-verification-required outcome |
| gold metrics | not scored; `gold_labels.count=0` and `gold_labels.status=not_used_by_simulation` |
| gate | `blocked_non_gating_simulation`; vector backend and embeddings remain false |
| privacy | receipt contains case IDs/counts only; no queries, source URLs, raw Telegram text, or provider payloads |

## PRM-24 Operator-Approved No-Answer Gold Seed - 2026-08-10

| Check | Result |
| --- | --- |
| approval ref | `operator-approval-2026-08-10-generated-drafts-as-gold` |
| source drafts | `evals/retrieval/product_rag_gold_label_drafts.jsonl` |
| gold label file | `evals/retrieval/product_rag_gold_labels.jsonl` |
| approved labels | 7 no-answer labels, including one external-verification-required no-answer case |
| manifest | `evals/retrieval/product_rag_eval_manifest.json` reported `gold_labels.count=7` at that time |
| remaining PRM-24 gap | historical; superseded by the 2026-08-11 50-row generated seed approval below |
| vector boundary | vector backend and embeddings remain false; PRM-26/PRM-27 still require separate backend/privacy/cost approval |
| side effects | no raw Telegram text, source URLs, provider payloads, embeddings, migrations, production writes, service start, dogfood, or compatibility archive/delete/move |

Focused verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_product_rag_eval.py tests/test_archive_retrieval_eval.py tests/test_memory_research.py -q
19 passed in 3.01s
PYTHONPATH=src python3 tools/product_rag_eval_manifest.py --root . --json evals/retrieval/product_rag_eval_manifest.json
product_rag_eval_manifest: cases=50 gold_labels=7 output=evals/retrieval/product_rag_eval_manifest.json
python3 tools/playbook_validate.py --root . --check tasks --check references
playbook_validate: errors=0 warnings=0
git diff --check
ok
```

## PRM-24 Full Generated Seed Gold Set And Baseline - 2026-08-11

| Check | Result |
| --- | --- |
| approval ref | `operator-approval-2026-08-11-all-50-generated-gold` |
| generated label command | `PYTHONPATH=src python3 tools/product_rag_seed_gold_labels.py --root . --db data/agent.db --jsonl evals/retrieval/product_rag_gold_labels.jsonl` |
| gold labels | 50 total: 43 source-labelled rows by stable local archive document/post IDs, 7 explicit no-answer rows |
| gold cases | `evals/retrieval/product_rag_gold_cases.jsonl` derived from candidates plus labels |
| manifest | `evals/retrieval/product_rag_eval_manifest.json` reports `gold_labels.count=50` and `coverage_status=full_coverage` |
| baseline report | `evals/retrieval/product_rag_fts_baseline_report.json` |
| baseline metrics | hit@10=1.0; MRR=1.0; citation_precision=1.0; duplicate_top10_rate=0.004; latency_ms_p95=46.912; reacted_post_searchability=0.967742 |
| known baseline gaps | no_answer_accuracy=0.0 because raw FTS returns related evidence for no-answer/control questions; stale_rejection=null because no stale/forbidden labels were approved |
| label quality | operator-approved generated seed labels, not independent human review |
| privacy | labels contain no raw Telegram text and no source URLs; baseline report contains no queries, snippets, source URLs, raw Telegram text, or provider payloads |
| vector boundary | vector backend and embeddings remain false; PRM-26/PRM-27 still require separate backend/privacy/cost approval |
| side effects | read-only local DB access only; no live Telegram service, live web research, provider egress, embeddings/vector backend, migrations, production writes, dogfood, or compatibility archive/delete/move |

Focused commands:

```text
PYTHONPATH=src python3 tools/product_rag_seed_gold_labels.py --root . --db data/agent.db --jsonl evals/retrieval/product_rag_gold_labels.jsonl
product_rag_seed_gold_labels: rows=50 approval_ref=operator-approval-2026-08-11-all-50-generated-gold output=evals/retrieval/product_rag_gold_labels.jsonl
PYTHONPATH=src python3 tools/product_rag_gold_cases.py --root . --jsonl evals/retrieval/product_rag_gold_cases.jsonl
product_rag_gold_cases: rows=50 output=evals/retrieval/product_rag_gold_cases.jsonl
PYTHONPATH=src python3 tools/product_rag_eval_manifest.py --root . --json evals/retrieval/product_rag_eval_manifest.json
product_rag_eval_manifest: cases=50 gold_labels=50 output=evals/retrieval/product_rag_eval_manifest.json
PYTHONPATH=src python3 tools/archive_retrieval_eval.py --root . --db data/agent.db --cases evals/retrieval/product_rag_gold_cases.jsonl --limit 10 --json evals/retrieval/product_rag_fts_baseline_report.json
archive_retrieval_eval: rows=50 gold=50 candidates=0 output=evals/retrieval/product_rag_fts_baseline_report.json
```

## PRM-26 Hybrid Retrieval ADR/Privacy Budget Acceptance - 2026-08-11

| Check | Result |
| --- | --- |
| ADR | `docs/adr/ADR-003-prm26-hybrid-retrieval-privacy-budget.md` |
| approval ref | `operator-approval-2026-08-11-no-vector-prm28-path` |
| status | `accepted_no_vector_for_now` |
| decision | no vector/backend adoption from current generated seed evidence |
| failure map | source-label hit/citation recovered by SQLite FTS/query planner; no-answer/refusal gap remains; stale/forbidden labels unmeasured |
| privacy/cost budget | 0 embedding rows, 0 tokens/chars, 0 provider calls, 0 vector writes, 0 migrations, $0 provider cost |
| rollback | no vector state exists; future vector state must be derived, versioned, disable-able, and backed up before production writes |
| gate impact | PRM-28 no-vector path is allowed; PRM-27 remains blocked unless a future successor vector ADR is approved |
| side effects | documentation/evidence only; no embeddings, vector backend, provider egress, live research, service start, migrations, production writes, dogfood, or compatibility archive/delete/move |

## PRM-28 No-Vector Answer Gate Acceptance - 2026-08-11

| Check | Result |
| --- | --- |
| implementation | `rag_answer_gate.v1` blocks impossible/current project-state claims and current external-fact questions even when FTS returns related posts |
| local product surface | `memory research` records `answer_gate` in the payload, receipt, and context pack |
| eval report | `evals/retrieval/product_rag_answer_gate_report.json` |
| answer-gate metrics | no_answer_accuracy=1.0; external_verification_boundary_accuracy=1.0; current_claim_rejection=1.0; answerable_source_label_accuracy=1.0 |
| vector metrics | vector_backend_required_rate=0.0; embeddings_run_rate=0.0 |
| privacy | report contains no queries, snippets, source URLs, raw Telegram text, or provider payloads |
| side effects | no provider egress, live research, embeddings/vector backend, service start, migrations, production writes, dogfood, or compatibility archive/delete/move |
| dogfood boundary | PRM-19 remains blocked until explicit dogfood-start approval |

Focused commands:

```text
PYTHONPATH=src python3 -m pytest tests/test_rag_context_pack.py tests/test_memory_research.py tests/test_product_rag_eval.py -q
23 passed in 11.88s
PYTHONPATH=src python3 tools/product_rag_answer_gate_eval.py --root . --cases evals/retrieval/product_rag_gold_cases.jsonl --json evals/retrieval/product_rag_answer_gate_report.json
product_rag_answer_gate_eval: rows=50 no_answer_accuracy=1.0 external_verification_boundary_accuracy=1.0 output=evals/retrieval/product_rag_answer_gate_report.json
```

## PRM-18 Post-PRM28 Release Gate Refresh - 2026-08-11

| Check | Result |
| --- | --- |
| receipt | `evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json` |
| base commit classified | `52abcebae7b5eb10af33780237d90198f24802b4` |
| product RAG evidence | PRM-24 generated seed set, PRM-26 no-vector acceptance, and PRM-28 answer gate |
| dogfood gate | blocked |
| dogfood started | false |
| release claimed | false |
| acceptance scenarios | 11 passed, 0 failed, 0 blocked under deterministic local evidence |
| evaluation areas | all passed under deterministic local evidence |
| active stop-ship blockers | none in the post-PRM28 receipt |
| active dogfood blockers | `review_unresolved:human-dogfood-approval`; `missing_human_dogfood_start_approval` |
| privacy | no raw Telegram text, source URLs, snippets, provider payloads, prompts, completions, generated private reports, production DB mutation, or private report commit |
| side effects | no Telegram service start, live ingestion, reaction sync, live research, provider egress, embeddings/vector backend, migrations, production writes, dogfood, release claim, or compatibility archive/delete/move |

Targeted verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_prm_release_gate.py -q
6 passed in 0.09s
```

```text
PYTHONPATH=src python3 -m pytest tests/test_public_evidence.py -q
6 passed in 0.20s
```

```text
python3 tools/test_tiers.py focused-prm
131 passed in 35.29s
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
<no output>
```

## PRM Local UX Trial - 2026-08-11

| Check | Result |
| --- | --- |
| receipt | `docs/audit/PRM_LOCAL_UX_TRIAL_2026-08-11.md` |
| scope | simulated local CLI use over representative operator questions |
| surfaces | `memory research --limit 4`; `memory ask --limit 4` |
| safety | no provider egress, live web research, Telegram service start, embeddings/vector backend, migrations, production writes, dogfood, or release claim |
| positive finding | no-vector RAG is usable for local archive discovery and `memory ask` handles current-fact refusal clearly |
| UX finding | initial trial found `memory research` audit-friendly but too verbose for daily use |
| implemented polish | compact default view, `--debug` full audit view, localized Russian headings/common next steps, freshness-first current-fact boundary, path redaction for `memory ask`, narrow repo-context cue, and no drafts for current-fact freshness-boundary answers |
| post-polish spot-check | three representative `memory research --limit 4` queries rendered at 1.56k-1.72k chars / 29-30 lines, with debug context pack hidden by default and no drafts in the current-fact case |
| validation | `PYTHONPATH=src python3 -m pytest tests/test_memory_research.py tests/test_local_memory_ask.py tests/test_cli.py -q` -> 35 passed in 4.41s; `python3 tools/test_tiers.py focused-prm` -> 134 passed in 22.88s; `python3 tools/playbook_validate.py --root . --check tasks --check references` -> errors=0 warnings=0; `git diff --check` -> no output |
| remaining gap | deterministic synthesis and curated-memory relevance are still shallow compared with a polished LLM-backed answer; live/current verification remains gated |

This receipt is diagnostic evidence only. It is not PRM-19 dogfood evidence.

## Telegram Local Research Routing - 2026-08-11

| Check | Result |
| --- | --- |
| implementation | `prm-assistant` ordinary text and transcribed voice now route to the Telegram research command, which renders local-only compact `memory research` output |
| explicit command | the Telegram research command with a question is registered and allowed in PRM safe mode |
| provider boundary | the Telegram research command uses `MemoryResearchBudget(max_model_calls=0, allow_provider_egress=false, allow_open_browsing=false)` |
| LLM Telegram gate | Telegram chat, Hermes, and ask commands refuse by default unless `PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1` is set before runtime startup |
| runtime boundary | service was not installed, enabled, started, or treated as dogfood |
| validation | `PYTHONPATH=src python3 -m pytest tests/test_handlers.py tests/test_callbacks.py -q` -> 47 passed in 25.25s; `PYTHONPATH=src python3 -m pytest tests/test_handlers.py tests/test_callbacks.py tests/test_cli.py tests/test_memory_research.py tests/test_local_memory_ask.py -q` -> 82 passed in 32.26s; `python3 tools/test_tiers.py fast-contract` -> 254 passed in 75.89s; `python3 tools/playbook_validate.py --root . --check tasks --check references` -> errors=0 warnings=0; `git diff --check` -> no output |
| operator use | after explicit manual runtime-start approval, send normal text or the Telegram research command with a question; do not use Telegram chat unless provider egress is separately approved |

This is a safe Telegram UX routing change only. It is not PRM-19 dogfood
evidence and does not approve provider egress, live web research, embeddings,
service start, migrations, or production writes.

## Local PRM Status UX - 2026-08-10

| Check | Result |
| --- | --- |
| command | `memory status` and `memory status --json` provide an entrypoint without database operations; normal CLI startup may print configured path/provider metadata |
| available local surfaces | `memory ask`, `memory research`, and evidence inspection |
| visible gates | human gold labels, provider egress, PRM-26 backend ADR, and dogfood approval remain explicit |
| side effects | no DB read/write, migration, service start, provider egress, external research, or embeddings |

Focused verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_memory_research.py -q
7 passed, 4 subtests passed in 2.91s
```

## Private AI Transformation Source Packet UX - 2026-08-10

| Check | Result |
| --- | --- |
| command | `memory ai-transformation-source-packet --allow-live-fetch --days 92` |
| purpose | private Markdown/JSON packet for editor workflows over top liked Telegram channels |
| source selection | read-only `reaction_sync_state` top channels plus read-only local archive rows |
| live source mode | optional explicit public Telegram web-preview fetch; no Telegram session or service start |
| output boundary | generated artifacts are under the ignored private output tree and are not committed |
| PRM boundary | not product RAG gold labels, not dogfood, not PRM-27/vector approval, and not a production ingestion path |
| side effects | no production DB write, migration, Telegram service start, provider egress, embeddings, vector backend, archive/delete/move, or compatibility cleanup |

Focused verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_ai_transformation_source_packet.py tests/test_cli.py -q
```

## Product RAG Eval Scaffold Evidence - 2026-08-08

| Check | Result |
| --- | --- |
| task | PRM-24 Product RAG Gold Eval Set scaffold |
| candidate file | `evals/retrieval/product_rag_candidate.jsonl` |
| candidate rows | 50 |
| category coverage | archive_recall=10, semantic_phrasing=10, project_fit=8, linked_source_freshness=8, no_answer=7, decision_support=7 |
| gold label file | `evals/retrieval/product_rag_gold_labels.jsonl` contains 50 operator-approved generated seed labels |
| gold labels | 50; full PRM-24 coverage is recorded as generated seed evidence |
| thresholds | `evals/retrieval/product_rag_thresholds.json` records proposed recall/citation/no-answer/stale/duplicate/latency thresholds |
| manifest | `evals/retrieval/product_rag_eval_manifest.json` contains counts and gate state, not queries, source URLs, snippets, raw Telegram text, or provider payloads |
| vector boundary | `vector_backend_adopted=false`; `embeddings_run=false` |
| live operations | none; no live HTTP fetch, external skill, provider call, embeddings/vector backend, migration, production DB write, dogfood start, or compatibility archive/delete/move |

Verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_product_rag_eval.py tests/test_archive_retrieval_eval.py tests/test_memory_research.py -q
21 passed in 2.08s
```

```text
PYTHONPATH=src python3 tools/product_rag_eval_manifest.py --root . --json evals/retrieval/product_rag_eval_manifest.json
product_rag_eval_manifest: cases=50 gold_labels=50 output=evals/retrieval/product_rag_eval_manifest.json
```

```text
python3 tools/test_tiers.py focused-prm
117 passed in 35.57s
```

## PRM-25 Citation-Safe Context Pack Evidence - 2026-08-08

| Check | Result |
| --- | --- |
| task | PRM-25 fixture-only context-pack substrate |
| contract | `rag_context_pack.v1` requires stable citations, bounded excerpts, source class, query variant, freshness status, and project label |
| exclusions | uncited, raw-corpus, duplicate, missing-excerpt, invalid, and over-budget candidates are excluded with privacy-safe reasons |
| local rendering | `memory research` renders the pack without a provider call, live fetch, migration, or write |
| semantic boundary | synthetic semantic candidates are fixture inputs only; no embeddings/vector lookup runs |
| PRM-24 gate | full 50-row generated seed coverage recorded; PRM-26 no-vector path accepted and PRM-28 no-vector answer gate implemented; PRM-19 dogfood remains blocked |

## PRM-18A..18C Deep Review Evidence - 2026-08-03

| Check | Result |
| --- | --- |
| review receipt | docs/audit/PRM_DEEP_REVIEW_PRM18A_18C_2026-08-03.md |
| unresolved stop-ship findings | none in PRM-18A..PRM-18C block |
| repaired finding | documentation overclaim about missing-approval refusal boundary was corrected to PI chat/provider execution |
| residual risks | real provider behavior and Telegram runtime activation remain gated; no dogfood or release claim |
| PRM-19 state | blocked until explicit human dogfood-start approval; current post-PRM28 release receipt clears deterministic local stop-ship blockers |

Boundary evidence:

```text
No live Telegram ingestion, reaction sync, Radar, Frontier, report generation,
full archive indexing, embeddings, external web research, external skill
execution, production database migration, dogfood start, release claim, or
compatibility-file archive/delete/move was performed.
```

## LLM Chat UX Task Block Setup Evidence - 2026-07-29

| Check | Result |
| --- | --- |
| setup task | PRM-18A Operator LLM Chat UX Contract |
| setup-time next task | PRM-18B LLM-Backed Memory Chat CLI |
| task block | PRM-18B -> PRM-18C before PRM-19; completed evidence recorded above |
| architecture prompt | docs/prompts/prm_architecture_research_agent.md |
| deep review boundary | batched after PRM-18C and before PRM-19 unless a stop-ship boundary is touched |
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
