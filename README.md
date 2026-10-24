# Telegram Personal AI Assistant

A personal assistant prototype for source-backed research, briefs, monitoring,
and confirmed actions in one Telegram conversation. It combines **Chat, Search,
Brief, Watch, and Act**, with durable permissions, task state, results, and receipts.

[Russian technical overview](README_RU.md) ·
[Product status](docs/PRODUCT_STATUS.md) ·
[Synthetic brief and previews](docs/artifacts/pa-20261010/README.md)

## Representative workflow

Ask a research question, inspect the cited sources, and turn the result into a
versioned brief. A recurring watch starts with a preview and confirmation. An
external action has its own exact preview and expiring, one-use confirmation;
an uncertain delivery is reconciled before any retry.

The example describes the implemented workflow. Connected mail, calendar, and
personal-source pilot acceptance remains unconfirmed.

## Current stage

**24 October 2026: implemented local prototype, awaiting selected connections and
an operator pilot.** The documented 10 October verification includes local
synthetic acceptance and real model generation. Daily operation, production
cutover, and human acceptance of the expanded assistant are unconfirmed.

The earlier research pipeline is part of the project's history. Its historical
use does not establish operation of the expanded assistant.
[Current evidence and integration record](docs/verification/PAI-master-integration-20261010.md).

## Implemented and still to verify

| Area | Implemented locally | Remaining evidence |
|---|---|---|
| Chat and Search | Shared conversation path, archive FTS, bounded research, citation/fact checks, explicit fallback | Representative personal questions, live archive scope, selected discovery service |
| Brief | Immutable versions, sources, HTML/PDF/Markdown export, private reader | Recurring personal use and usefulness of the selection |
| Watch | Preview/confirm, durable schedule, quiet hours, caps, pause/revoke | Sustained operation and real notification noise |
| Act | Exact preview, one-use confirmation, executor, receipts, separate reconciliation | Selected real mail/calendar accounts and observed effects |
| Connections and memory | OAuth/PKCE adapters, grants, versioned memory, deletion and lifecycle checks | Real account scopes, private-data settings, institutional access |
| Operations | Leases, recovery, cost accounting, backup/restore, isolated migration rehearsal | Production target, cutover, real task cost and latency |

SQLite remains the canonical Telegram archive. PostgreSQL stores the expanded
assistant's runtime state. An implemented adapter does not mean an account is
connected.

## Engineering evidence

The dated [requirement map](docs/verification/PAI-requirement-evidence-20261010.md)
covers 69 requirements and 10 scenarios. The
[verification report](docs/verification/PAI-go-pilot-20261010.md) records the
active 398-test run, real generation, dialogue checks, visual checks, failures,
and corrections at their exact revisions. Overlapping suites are not additive.

Formal design/role/human gates remain open. The detailed status retains missing
approvals and the outstanding bounded HTML/empty-draft findings. Test fixtures,
provider calls, visual review, and operator usefulness establish different things.

## Development setup

Python 3.10+, Git with submodules/symlinks, and the declared dependencies are
required. PAI integration tests use disposable, isolated PostgreSQL 14 instances.

```bash
git submodule update --init --checkout -- .playbook/upstream
python -m pip install -r requirements.txt -r requirements-playbook.txt
python tools/playbook.py --check-pin
python tools/check_personal_assistant_plan.py
python tools/check_pai_plan.py
PYTHONPATH=src python -m prm.cli --help
```

Choose the smallest relevant test tier using the
[test strategy](docs/TEST_STRATEGY.md); do not run the full historical suite.
The [runtime runbook](docs/runbooks/assistant_runtime.md) describes explicit
targets and configuration. Setup does not activate all accounts or start a
production service.

[Architecture](docs/ARCHITECTURE.md) ·
[Full specification](docs/PERSONAL_ASSISTANT_SPEC.md) ·
[Document index](docs/PA_DOCUMENT_INDEX.md) ·
[Pilot access checklist](docs/verification/PAI-pilot-access-20261010.md)
