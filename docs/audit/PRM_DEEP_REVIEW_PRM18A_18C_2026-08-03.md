# PRM-18A Through PRM-18C Deep Review - 2026-08-03

Status: active deep-review evidence
Scope: PRM-18A Operator LLM Chat UX Contract, PRM-18B LLM-Backed Memory Chat
CLI, and PRM-18C Telegram PRM Assistant UX Parity And Start Runbook
Authority: `docs/tasks.md`, `docs/PRIVACY_THREAT_MODEL.md`,
`docs/COST_BUDGET.md`, `docs/PRODUCT_OPERATING_MODEL.md`

## Gate

This is the batched deep-review boundary required after PRM-18C and before
PRM-19. PRM-19 dogfood was not started during this review.

Review was performed locally in the main Codex session. No nested Codex CLI
processes or child agents were spawned.

## Reviewed Material

- PRM task graph and handoff docs:
  - `docs/tasks.md`
  - `docs/operator_workflow.md`
  - `docs/PRODUCT_OPERATING_MODEL.md`
  - `docs/audit/PRM_LLM_CHAT_UX_TASKS_2026-07-29.md`
  - `docs/EVIDENCE_INDEX.md`
- Implementation files:
  - `src/main.py`
  - `src/assistant/local_memory_ask.py`
  - `src/assistant/prm_chat_display.py`
  - `src/bot/handlers.py`
- Tests:
  - `tests/test_cli.py`
  - `tests/test_pi_chat.py`
  - `tests/test_local_memory_ask.py`
  - `tests/test_handlers.py`
  - `tests/test_callbacks.py`
- Runtime template:
  - `systemd/telegram-prm-assistant.service`

## Findings And Disposition

| Area | Finding | Severity | Disposition |
| --- | --- | --- | --- |
| Evidence wording | The initial PRM-18B evidence text said the missing-approval path refused before settings load. The handler does that when called directly, but the top-level CLI loads settings for startup logging before dispatch. The actual safety requirement is refusal before PI chat/provider execution. | Low | Fixed during review: task notes, evidence index, block receipt, and test name now state refusal before PI chat/provider execution. Direct CLI smoke confirmed exit code `2` with no provider call. |
| Runtime boundary | Telegram chat has no per-message command-line egress switch; the explicit approval boundary for Telegram remains the disabled service and future PRM-19 runtime start approval. | Residual | Accepted as matching PRM-18C: the service was not installed, enabled, started, or treated as dogfood. Help copy and runbook state the approval prerequisite. |
| Provider coverage | Approved LLM CLI paths are covered with fake clients and fixture data, not real provider calls with private snippets. | Residual | Accepted by task cost budget. Real provider egress remains a hard gate requiring explicit human approval for that run. |

No unresolved high-severity or stop-ship finding was found in PRM-18A through
PRM-18C.

## Verification

PRM-18B targeted verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_local_memory_ask.py tests/test_pi_chat.py tests/test_cli.py -q
37 passed, 9 subtests passed in 9.10s
```

PRM-18C targeted verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_handlers.py tests/test_callbacks.py tests/test_cli.py -q
58 passed, 3 subtests passed in 50.50s
```

Unit template verification:

```text
systemd-analyze verify systemd/telegram-prm-assistant.service
exit=0; unrelated host warning: /lib/systemd/system/snapd.service unknown RestartMode key
```

Direct missing-approval CLI smoke:

```text
PYTHONPATH=src python3 src/main.py memory ask --llm-approved "test question"
exit=2; printed provider-egress refusal; no provider call was made
```

PRM and shared contract tiers:

```text
python3 tools/test_tiers.py focused-prm
103 passed, 6 subtests passed in 24.45s
```

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

## Residual Risk

- Real provider behavior is not dogfood evidence; implementation/test cost
  remained zero with fake clients.
- Telegram runtime activation remains untested by design because service start
  is a PRM-19 dogfood-start action.
- Full-project pytest was not rerun for this block. The known
  date-sensitive product-ops fixture failure remains documented from PRM-18.
- PRM-8 vector/hybrid retrieval remains blocked.
- PRM-18 release/dogfood gate remains blocked by missing final acceptance
  evidence, gold retrieval labels, and explicit human dogfood-start approval.

## Boundary Evidence

- No live Telegram ingestion, reaction sync, Radar, Frontier, report generation,
  full archive indexing, embeddings, external web research, external skill
  execution, production database migration, dogfood start, release claim, or
  compatibility-file archive/delete/move was performed.
- No `telegram-prm-assistant.service` install, enable, or start was performed.
- No production database contents were modified.
- No live LLM provider call was made; tests used fake LLM clients and fixture
  databases.
- No private Telegram raw text or generated private report was committed.
- PRM-19 remains blocked until the human operator explicitly approves dogfood
  start and PRM-18 blockers are accepted or cleared.
