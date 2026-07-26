# Agent Harness Design

Status: draft

## Boundary

The assistant is a bounded, local, single-operator tool-use harness. It is not a
self-modifying runtime and not a broad autonomous agent.

## Inputs

- operator question;
- session-local chat context;
- approved tool catalog;
- retrieval and privacy policies;
- cost budget.

## Tools

Read-only by default. Proposal tools return a proposed write object and require
human confirmation before persistence.

No tool may:

- edit code;
- edit profile/config/project files;
- mutate database rows outside confirmed memory writes;
- run Codex;
- install or activate external skills;
- send broad raw corpus text to a provider.

## Trace

Each assistant turn records:

- request ID;
- intent route;
- tool calls and bounded arguments;
- result counts and evidence status;
- retrieval latency;
- generation latency;
- model class;
- cost estimate;
- termination reason;
- insufficient-evidence flag.

Trace records must not include raw post text beyond bounded cited snippets.

## Termination

Allowed terminal states:

- answered_with_evidence;
- insufficient_evidence;
- needs_external_verification;
- needs_confirmation;
- tool_error_degraded;
- invalid_request.

Max correction/retry count defaults to 2 per task unless a task states less.
