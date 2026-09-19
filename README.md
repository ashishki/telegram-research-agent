# Telegram Personal AI Assistant

Private, single-operator assistant. The current implementation is an archive-
centered alpha; the full target is natural Chat, real AI Search, beautiful
weekly/topic Briefs, controlled Watch and confirmed Act in one conversation.
**The PA specification is a target, not a claim these features already work.**

## Start here

- [Full specification in Russian](docs/PERSONAL_ASSISTANT_SPEC.md): all user
  wishes, UX, weekly reports, search, connectors, Academic Inbox, permissions,
  architecture, models, evidence, operations and full completion criteria.
- [Current handoff](docs/CODEX_PROMPT.md) and
  [next-session assignment](docs/prompts/personal_assistant_implementer.md).
- [Compact programme design](docs/design/PA.md),
  [slice registry](docs/design/PA.design.json), [active tasks](docs/tasks.md).
- [Pinned Playbook setup](docs/PLAYBOOK_ADOPTION.md) and
  [review policy](docs/REVIEW_POLICY.md).

## Current implementation versus target

Existing archive search/evidence, confirmed saved actions and bounded public
UTD watch are useful foundations. The inspected active application blocks free
AI chat/synthesis and does not provide working personal mail/Canvas connections.
The new plan develops the whole assistant without restarting old report timers
or claiming a finished product from fixtures. Current deployed state was not
observed. Baseline focused CI has a known UX evaluation failure assigned PA-00.

Original implementation documentation and evidence remain available:
[architecture](docs/ARCHITECTURE.md), [contract](docs/IMPLEMENTATION_CONTRACT.md),
[Academic Inbox handoff](docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md),
[previous README](README.before-pa-20260918.md),
[prior tasks](docs/tasks.before-pa-20260918.md).

## Development setup

```bash
git submodule update --init --checkout -- .playbook/upstream
python -m pip install -r requirements-playbook.txt
python tools/playbook.py --check-pin
python tools/check_personal_assistant_plan.py
```

Application tests additionally need `requirements.txt`. New tooling is pinned
to owner Playbook commit `d570163ab17ec3b4245187c778f1e8d89af9690f`, not latest.
It is development-only, not a runtime dependency. See the adoption guide for
Linux/WSL symlink requirements, focused checks and exact design approval.

No private data or secrets in Git. No account, paid model call, service, timer,
production migration or release is enabled by the planning/tooling update.
