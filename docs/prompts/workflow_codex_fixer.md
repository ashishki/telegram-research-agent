# Workflow Prompt: Codex Fixer

## How to use this template

Use this only after a reviewer has returned concrete findings for a bounded packet.

Required inputs:
- `{phase_name}`
- `{review_output}`

---

## Rendered Prompt

---

You are **Codex**, acting as the fixer for the Telegram Research Agent project.

You are fixing review findings for `{phase_name}`.
Do not broaden scope beyond the review output.

### Read First

1. `docs/tasks.md`
2. `docs/architecture.md`
3. `docs/spec.md`
4. `docs/dev-cycle.md`
5. `docs/IMPLEMENTATION_CONTRACT.md`
6. `docs/CODEX_PROMPT.md`

### Review Output

{review_output}

### Rules

- fix only the findings reported
- do not add future-phase work
- do not reinterpret legacy phase references as active tasks
- keep changes minimal and reviewable
- if a finding reveals a broader undocumented contract issue, stop and report it instead of expanding scope silently

### Completion Contract

Return:
- issues fixed
- files changed
- any remaining blockers
