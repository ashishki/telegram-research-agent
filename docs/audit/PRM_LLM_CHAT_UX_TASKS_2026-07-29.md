# PRM LLM Chat UX Task Block Receipt - 2026-07-29

Status: proposed next implementation block

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

What is missing is a polished operator-facing LLM chat workflow that makes
privacy, citations, unknowns, cost, and write boundaries visible.

## Boundary

The task block does not start dogfood. It does not approve raw/bounded Telegram
snippet provider egress by default. It does not start Telegram services,
external search, Radar, Frontier, report generation, embeddings, migrations, or
production database writes.

PRM-19 remains blocked until PRM-18A through PRM-18C are completed or explicitly
deferred, PRM-18 blockers are accepted or cleared, and the human operator
explicitly approves dogfood start.

## Next Session

Start at `PRM-18A`. Read:

- `AGENTS.md`;
- `docs/CODEX_PROMPT.md`;
- `docs/tasks.md`;
- `docs/operator_workflow.md`;
- `docs/PRODUCT_OPERATING_MODEL.md`;
- `docs/PRIVACY_THREAT_MODEL.md`;
- `docs/COST_BUDGET.md`;
- `src/assistant/pi_chat.py`;
- `src/assistant/pi_tools.py`;
- `src/assistant/local_memory_ask.py`;
- `src/main.py`.

Do not run real provider calls with private Telegram snippets while implementing
the block. Use fake LLM clients and fixture databases for tests.

## Evidence

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
