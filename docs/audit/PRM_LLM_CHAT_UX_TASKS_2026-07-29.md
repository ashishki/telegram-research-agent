# PRM LLM Chat UX Task Block Receipt - 2026-07-29

Status: implementation block complete; batched deep review recorded before
PRM-19

## Scope

This receipt records the pre-dogfood user-experience block for making the
existing PRM/RAG/LLM harness understandable as a ChatGPT-like operator flow.

New tasks added to `docs/tasks.md`:

- `PRM-18A`: Operator LLM Chat UX Contract;
- `PRM-18B`: LLM-Backed Memory Chat CLI;
- `PRM-18C`: Telegram PRM Assistant UX Parity And Start Runbook.

## Rationale

The repository already has:

- bounded SQLite FTS Telegram archive retrieval;
- PI tool catalog;
- PI chat planning/tool loop;
- grounded answer contract;
- local external-verification requirement path;
- confirmation-gated memory proposals;
- local-only `memory ask`.

The block closed the missing operator-facing LLM chat workflow enough for the
pre-dogfood boundary: privacy, citations, unknowns, cost, and write boundaries
are visible in CLI and Telegram chat output.

## Boundary

The task block does not start dogfood. It does not approve raw/bounded Telegram
snippet provider egress by default. It does not start Telegram services,
external search, Radar, Frontier, report generation, embeddings, migrations, or
production database writes.

PRM-19 remains blocked until the batched PRM-18A..PRM-18C review is accepted by
the human operator, PRM-18 blockers are accepted or cleared, and the human
operator explicitly approves dogfood start.

## Progress Update - 2026-08-03

PRM-18A was implemented as a docs-only UX/privacy/cost contract. It did not
call providers, run external search, start Telegram services, run migrations, or
write production DB state.

PRM-18B and PRM-18C were implemented later on 2026-08-03. The batched deep
review boundary is recorded before PRM-19.

## Implementation Update - 2026-08-03

`PRM-18B` is implemented:

- `memory ask --llm-approved` refuses before PI chat/provider execution unless
  `--allow-provider-egress` is present;
- `memory ask --llm-approved --allow-provider-egress "<question>"` runs the
  existing PI chat path and renders answer, sources, archive support, unknowns,
  external-verification status, write status, and privacy/cost flags;
- `memory chat --allow-provider-egress` runs repeated stdin/stdout turns until
  exit/quit commands, `:q`, or EOF;
- local `memory ask` now prints the same privacy/cost line with
  `mode=local-only`.

`PRM-18C` is implemented:

- Telegram safe-mode start and help state local-only CLI mode,
  approved LLM/provider-egress mode, safe read-only commands, blocked legacy
  generation/write commands, and dogfood-not-started status;
- Telegram chat, Hermes, ask aliases, ordinary text, and voice transcript
  dispatch use the same privacy-safe PRM chat renderer as the CLI;
- the operator runbook documents preflight, install/start/status,
  stop/disable, and rollback-to-disabled commands while preserving the service
  start gate.

No live Telegram ingestion, reaction sync, Radar, Frontier, report generation,
full archive indexing, embeddings, external web research jobs, LLM provider
calls, systemd starts/enables, startup migrations, production database writes,
or compatibility deletes/archives were performed.

## Next Session

Stop before PRM-19. PRM-19 cannot start until explicit human dogfood-start
approval is recorded and PRM-18 blockers are accepted or cleared.

Batched review receipt:

- `docs/audit/PRM_DEEP_REVIEW_PRM18A_18C_2026-08-03.md`

## Evidence

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
docs/prompts/prm_architecture_research_agent.md
created as optional local-research prompt for architecture decision before PRM-18A
```

```text
git diff --check
pass, no output
```

No live Telegram ingestion, reaction sync, Radar, Frontier, report generation,
full archive indexing, embeddings, external web research jobs, live LLM
provider calls, systemd starts/enables, startup migrations, production database
writes, or compatibility deletes/archives were performed.
