# Telegram Personal AI Assistant

A personal assistant prototype for source-backed research, briefs, monitoring,
and confirmed actions in one Telegram conversation. It combines **Chat, Search,
Brief, Watch, and Act**, with durable permissions, task state, results, and receipts.

[Русский обзор и план](README_RU.md) ·
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

**Documentation reconciled on 25 October 2026; latest implementation evidence:
14 October.** Eight local packages cover **D01–D21, D56, and D58**: 23 of the
62 backlog cards have local engineering implementation/review evidence. The
remaining 39 include required work and conditional branches; this count is not
a product-completion percentage or human acceptance.

The current source is `b00a5cb`, with package handoff `865a7d8`, on
`codex/pa-daily-implementation-20261013`. The 24 October upstream English/Russian
README refresh is preserved through a normal merge. The daily implementation
is on this working branch; its integration into `master` is a separate step.

**Next package: D22 + D23 + D24 + D57** — private-storage contracts, retention
and restore, one observable runtime profile, and truthful Telegram progress/Stop.
D22 and D57 need bounded slices before implementation. Selected real
connections, sustained daily operation, production cutover, and human acceptance
remain unconfirmed.

The earlier research pipeline is part of the project's history. Its historical
use does not establish operation of the expanded assistant.
[Dated foundation evidence](docs/verification/PAI-master-integration-20261010.md)
and [current package evidence](docs/verification/DAILY-package-08-D19-D20-D21-D58-20261014.md).

## Declared product scope

The full target remains one assistant with five connected capabilities:

| Capability | Intended user outcome |
| --- | --- |
| **Chat** | Explain, rewrite, reason together, and continue the right task or document in an ordinary conversation. |
| **Search** | Research permitted Telegram, web, GitHub, and selected personal sources; cite evidence, dates, contradictions, and coverage gaps. |
| **Brief** | Produce useful weekly/topic/project briefs, discuss individual items, refresh explicit versions, and export matching Telegram/HTML/PDF/Markdown views. |
| **Watch** | Follow confirmed topics and deadlines with schedules, quiet hours, limits, pause, revoke, and delivery receipts. |
| **Act** | Prepare drafts and execute selected mail/calendar actions only after exact, expiring, one-use confirmation. |

The programme also includes controlled memory and project context, documents/
voice/images, selected mail/calendar connections, Academic Inbox and Nebula,
private reading, cost controls, recovery, and actual user evaluation. Canvas is
deferred; Telegram topics and Secretary have separate selection/read/draft/send
gates. **Mini App is excluded.** The target is the full assistant, not an MVP.

## Implemented and still to verify

| Area | Implemented locally | Remaining evidence |
|---|---|---|
| Chat and Search | Native routing/focus, confirmed project context, RU/EN canonical retrieval, selected GitHub contracts, bounded research waves, citation/fact checks and explicit coverage | Representative personal questions, actual archive/discovery/GitHub grants, provider quality and calibrated evaluation |
| Brief | Whole-period inventory, event/project selection, exact item/version follow-ups, refresh/diff, HTML/PDF/Markdown bytes, feedback/rule undo and optional rich Telegram delivery | Useful recurring selection, deployed private reader and real Telegram/client visual acceptance |
| Watch | Preview/confirm, durable schedule, quiet hours, caps, pause/revoke | Sustained operation and real notification noise |
| Act | Exact preview, one-use confirmation, executor, receipts, separate reconciliation | Selected real mail/calendar accounts and observed effects |
| Connections and memory | OAuth/PKCE adapter foundation, grants, relevant confirmed-memory context, explicit save/correct/inspect/export/forget and transitive provenance | Real account scopes, selected retention, integrated media and institutional access; automatic save+undo remains inactive |
| Operations | Durable jobs/leases/checkpoints, Telegram routing/controls, model profiles/budgets and isolated recovery rehearsal | D22/D23/D24/D57, real private target, progress/streaming, production operation and measured task cost/latency |

SQLite remains the canonical Telegram archive. PostgreSQL stores the expanded
assistant's runtime state. An implemented adapter does not mean an account is
connected.

Rich messages default off; nonfull/refresh views preserve their exact compatible
HTML/text. Three action-preview provenance failures reproduced on the package-08
base remain recorded. They are not hidden by the latest package's P1 closure.

## Remaining plan

1. Implement **D22/D23/D24/D57** locally, with bounded storage and progress slices.
2. Prepare private reader/onboarding **D25/D26**, then separately authorized
   source canary **D27**, real-phone acceptance **D40**, and the 14-day/four-brief
   usefulness pilots **D38/D39**, respecting dependencies.
3. Complete calibrated quality/model/cost evaluation **D35–D37** and configuration/
   working-method improvements **D47/D48**; these can advance independently.
4. Continue drafts, selected mail/calendar, Watch, media, deletion and host
   resilience **D28–D34/D42/D43**. Microsoft/Google follow the owner's choice.
5. Deliver Nebula **D51–D54**, conditional gap work **D55**, deferred Canvas
   **D41**, and selected topics/Secretary **D59–D62** through their own gates.
6. Reach full acceptance **D44** after all applicable requirements have evidence;
   architecture/maintenance work **D45–D50** follows its dependencies, with
   learned retrieval and scaling requiring measured justification.

The [single backlog](docs/strategy/2026-10-11/BACKLOG.md) defines exact dependencies;
[handoff](docs/CODEX_PROMPT.md) defines the next local step. Missing account access
does not stop independent synthetic implementation. Real accounts, private/paid
egress, services, migrations, and external effects need their own scoped authority.

## Engineering evidence

The dated [requirement map](docs/verification/PAI-requirement-evidence-20261010.md)
covers 69 requirements and 10 scenarios at the 10 October source `0fbcfd1`. The
[verification report](docs/verification/PAI-go-pilot-20261010.md) records the
active 398-test run, real generation, dialogue checks, visual checks, failures,
and corrections at their exact revisions. Overlapping suites are not additive.

The eight daily packages have separate scoped checks and local read-only review
receipts in the [backlog](docs/strategy/2026-10-11/BACKLOG.md). Package 08 has one
full review and two narrow rechecks; all seven P1 and two P2 findings are closed
locally. Its final 30-case and 6-case runs overlap. No current whole-suite pass,
real-provider quality, or live Telegram appearance is inferred from those runs.

Formal design/role/human gates remain open. The detailed status retains missing
approvals and the outstanding bounded HTML/empty-draft findings. Test fixtures,
provider calls, visual review, and operator usefulness establish different things.
Daily local collaboration reviews do not fill the non-Codex Go/governed gates.

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
