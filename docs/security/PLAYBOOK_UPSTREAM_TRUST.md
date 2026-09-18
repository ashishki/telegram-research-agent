# Trust Record: Owner-maintained Playbook Development Kit

Date: 2026-09-18
Source: https://github.com/ashishki/AI_workflow_playbook
Pin: d570163ab17ec3b4245187c778f1e8d89af9690f
Install scope: repository-local Git submodule `.playbook/upstream`.
Requested authority: owner explicitly requested updating development methodology.

Capabilities: deterministic validation, structured planning, context rendering,
command receipts, and explicitly invoked model review tooling. The Role Runner
can invoke Codex when selected; merely checking out the kit does not invoke it.
No global hooks, skills, runtime agents, account connectors or live jobs enabled.

Reviewed material: pinned README/usage guide, subagent protocol, feature workflow
entrypoint, feature-design library, prompt/context renderers and relevant JSON
schemas. Bridge rejects wrong/dirty/missing pin and non-allowlisted entrypoints.
Full upstream security scan and independent model review were NOT performed;
a clean checkout/hash is integrity evidence, not proof of safety. Read precise
capabilities/commands and budget before invoking any paid/external reviewer.

Do not send private Telegram/mail/Canvas data, secrets or live account details
to reviewers. Synthetic code/test fixtures only unless separate scoped approval.
Follow upstream license notices; no general open-source permission is inferred.

Update procedure: review exact upstream diff, record new pin and limitations,
change lock/gitlink together, rerun local/CI checks. No auto-update to latest.
Rollback: revert gitlink/lock and docs/tooling changes; no runtime data affected.
