# Current assignment — daily assistant strategy and implementation handoff

The 2026-10-11 owner assignment requests independent research, product strategy,
architecture and an executable plan for the next coding agent. This session is
documentation only: no product implementation, personal connections, paid model
inference, external effects, production migrations, services or timers.

Completed research packet: [strategy index](strategy/2026-10-11/README.md).
Read that index, [code audit](strategy/2026-10-11/CODE_AUDIT.md), then only the
assigned cards in [backlog](strategy/2026-10-11/BACKLOG.md). It contains 62 proposed
tasks, mapped to all 69 full-spec IDs; proposed status is not implementation,
design approval or human acceptance. The current owner allows critical redesign
and process simplification as proposals. Existing safety/approval records remain.

The first concrete implementation block for a subsequently assigned coding agent
is **D01 → D02 → D03**: explicit runtime entrypoint/config check, natural job
status/cancel/result, and a shared typed dispatcher over existing capabilities.
Use [IMPLEMENTER_START](strategy/2026-10-11/IMPLEMENTER_START.md) for scope,
interfaces, behavioral cases and exact commands. It can be developed locally on
synthetic fixtures without personal access. Implementation starts only in that
next assigned session; this research session stops after the checked packet.

Owner clarification, 2026-10-11: the next coding agent implements in bounded
packages, with Deep Review BETWEEN packages: implement, scoped checks, one
independent review of the accumulated diff, fix findings, proceed. Recheck P0/P1
fixes independently and narrowly; do not restart whole reviews/test suites for
cosmetics or chase endless review cycles. Carry noncritical remaining findings
explicitly. Sixty-two backlog cards do not imply sixty-two full review cycles.

Source inspected: `23312b8` (master at research start). Current strategy branch:
`codex/pa-daily-strategy-20261011`. Do not edit source on master, reset others'
work or assume the old master-merge assignment authorizes a new deployment.
Previous handoff is preserved in Git at `23312b8:docs/CODEX_PROMPT.md`.

Evidence baseline: runtime/test `0fbcfd1`, dated 398 active PAI checks /69 IDs/
10 scenario groups; actual Go synthetic capture and public GitHub/Python reads;
scoped engineering review117 ADVISORY, extreme HTML-depth P2 remains. CI guard
correction `4c2656c` has separate review118; merge/remote CI receipt is
[PAI-master-integration-20261010](verification/PAI-master-integration-20261010.md).
No current personal/operator acceptance. SyntheticTarget is test-only; private
storage and real startup require implementation and scoped selection.

The strategy identifies additional code-level gaps: optional durable startup,
command/prefix routing, early 48-item Brief truncation, transport API differences,
and incomplete daily personalization wiring. These are static findings, not a
claim that historical passing tests failed. Current public Go documentation
describes coding-agent traffic; runtime suitability, account availability and
privacy must be assessed separately from the public catalog. No new winner over
GPT-4o is claimed; a matched experiment and calibrated judge are specified.

Continue the full Chat/Search/Brief/Watch/confirmed Act programme. Canvas
remains owner-deferred. The owner additionally requested Nebula research/tasks
and will request an API key: read [UTD_NEBULA](strategy/2026-10-11/UTD_NEBULA.md),
D51–D54 plus conditional D55. There is currently no Nebula client in src.
Nebula-only must work without Canvas; api-tools is an upstream ETL CLI, not a
required client dependency. No key/connection/implementation occurred here.
Owner clarification: deliver a fully working daily Nebula integration, not a
minimal adapter or smoke-only MVP. D51–D54 cover useful datasets, durable
sync/recovery, conversation/memory, Brief/Watch and a 14-day real pilot. D55
closes measured gaps with suitable ready-made components; choose reuse by
quality and maintainability, not line-count minimization. D54 completes after
D52/D53/D27; its initial key/canary preparation may happen earlier.
These external gates do not block independent work. Do not rerun completed
historical tasks/reviews, immutable115/116/117 calls or full historical pytest.
Do not forge the 51 missing formal approvals. Use current REVIEW_POLICY and the
pinned tools/playbook.py entrypoint; keep engineering evidence separate from
provider, visual, operator and formal acceptance.

Telegram changes are integrated into this same backlog, not a separate roadmap.
Read [TELEGRAM](strategy/2026-10-11/TELEGRAM.md) only as the design/evidence
reference for assigned cards. After D01–D03, take D56; then dependency-ready
D57/D58 feed the shared D27/D40 pilot. D59 topics are experimental; selected
Secretary D60→D61→D62 separates read, local draft and confirmed send. Mini App is explicitly excluded by the owner; do not implement or reintroduce it
as a conditional task. D25 remains an ordinary private reader. The optional
topics/Secretary branches do not block the core assistant. Official API availability is not observed bot/client support.
The only implementer handoff remains IMPLEMENTER_START; no separate TG phases.

Next safe command:
`PYTHONPATH=src .venv-pai/bin/python -m prm.cli --help`.

Research commands/results, changed files and unresolved gates:
[RESEARCH_RECEIPT](strategy/2026-10-11/RESEARCH_RECEIPT.md).
