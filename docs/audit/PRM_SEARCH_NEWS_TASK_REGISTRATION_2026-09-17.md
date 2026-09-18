# PRM Search And News Task Registration

Date: 2026-09-17
Scope: owner-requested documentation/task registration and implementer launch prompt.
Status: documentation prepared and locally validated; implementation/reviews not started.
Code baseline remains `cee8baae3b8a41f571bd689f2dadf7e6e981863f`.

## Registered

- Twelve PRM-SN implementation cards in docs/tasks.md, each with scope,
  dependencies, acceptance, verification and context links.
- Five engineering phase gates and one post-pilot gate. Implementation tasks
  and engineering reviews are planned; the post-pilot gate awaits approved
  real evidence. No gate is marked passed.
- ADR-009, detailed plan/evaluation, independent Terra/high review protocol,
  reviewer template and an end-to-end local implementation goal assignment.
- Current AGENTS/CODEX_PROMPT/README/navigation/policy pointers aligned with the
  new queue. The historical RFX-only instruction no longer redirects an assigned
  PRM-SN task. Existing RFX/UTD task records remain byte-for-byte unchanged.
- Prior synthetic audit receipt retained as historical evidence; no private
  archive, credentials or new provider/runtime measurement added.

## Verification

The deterministic Playbook validator ran its tasks and references checks through
an external Python I/O guard with an empty environment. Network, subprocess,
SQLite access, private data reads and repository writes were blocked for the
check. Result: **0 errors, 0 warnings**; guard blocked-event list empty.

The first attempt used the existing project venv, which lacked jsonschema.
Validation then passed with the already-installed system Python/jsonschema;
no package was installed and no environment or service configuration changed.

Additional checks: new Markdown links/anchors resolve, original RFX/UTD task
blocks compare equal to HEAD, task dependency graph validates, and git diff
whitespace check passes. Product code, tests, tools, systemd and Playbook runtime
configuration have no diff. Existing unrelated untracked files were not changed.

The audit's prior 91 product-test passes are not new tests of this documentation
change. No Codex reviewer/provider invocation, bot test against real Telegram,
production DB access, timer, migration, commit, push or release occurred.

## Launch and remaining boundaries

The owner clarified that the prompt must pursue the goal from start to finish.
Use docs/prompts/prm_search_news_implementer.md to assign all twelve local tasks,
DR-1 through DR-5, corrections, integrated checks and the concrete pilot packet.
Required independent Codex exec Terra/high reviews are included in that scope;
phase continuation does not require a new request per card. Registration and
prompt editing do not execute the goal. Task critics still do not close whole
phase gates. Human labels, runtime, pilot execution and rollout remain separate.
