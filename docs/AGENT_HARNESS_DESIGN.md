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

## PRM-9 Implemented Tool Boundary

`assistant.pi_tools.build_pi_tool_catalog` exposes one bounded catalog for the
assistant entrypoint.

Minimum read-only tools:

- `get_current_week_label`;
- `get_weekly_summary`;
- `get_artifact_status`;
- `search_intelligence_items`;
- `search_telegram_archive`;
- `search_idea_threads`;
- `get_idea_thread`;
- `get_project_actions`;
- `get_mvp_radar_status`;
- `get_feedback_summary`;
- `list_marked_posts`;
- `get_strategy_reviewer_notes`;
- `request_external_verification`.

Additional local read-only helpers:

- `get_workbook_sections`;
- `get_action_statuses`.

Confirmation-gated proposal tools:

- `propose_knowledge_note`;
- `propose_watch_topic`;
- `propose_project_link`;
- `propose_decision`;
- `propose_action`;
- `propose_experiment`;
- `propose_feedback`.

Proposal tools return `needs_confirmation`, `persisted=false`, and a proposed
object only. They do not write to SQLite, files, profile, config, projects, or
feedback tables.

Confirmed write tool:

- `confirm_save_proposal`.

`confirm_save_proposal` is the only writable PI tool. It requires an explicit
facade, the exact proposal object, and the matching confirmation token. It
requires the canonical `personal_memory_events` schema to already exist through
normal migrations; the tool handler does not create tables lazily. Replaying the
same proposal/token returns the existing event and does not append a duplicate.
Edit, delete, and rollback confirmations validate that their target memory or
event exists before writing.

The catalog is an explicit allowlist. Known external-skill tool names remain
unapproved unless a trust record is approved, and unknown tool names are rejected
before handler execution.

Deterministic intent routes cover exact archive search, concept search, case
search, comparison, freshness/news, project application, reaction recall,
no-answer probes, artifact status, Radar status, strategy notes, and external
verification requests.

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

PRM-9 trace schema: `pi_assistant_trace.v1`.

Each tool trace records:

- selected tool name;
- bounded arguments;
- result count;
- tool status;
- evidence status;
- privacy boundary.

Turn-level trace records planner type, deterministic intent, termination
reason, insufficient-evidence flag, and privacy boundary
(`raw_telegram_text_egress` for bounded snippet provider context,
`raw_telegram_corpus_egress=false`, `external_skill_used=false`,
`write_performed=false` unless a confirmed write succeeds). PI chat suppresses
content-free `llm_usage` database writes during read-only planning/generation;
cost remains in response telemetry.

Tool trace privacy labels:

- `bounded_read_only_no_raw_corpus`;
- `proposal_only_no_write`;
- `confirmation_gated_write_no_write`;
- `confirmation_gated_write`.

## Termination

Allowed terminal states:

- answered_with_evidence;
- insufficient_evidence;
- needs_external_verification;
- needs_confirmation;
- confirmed_write;
- tool_error_degraded;
- invalid_request.

Max correction/retry count defaults to 2 per task unless a task states less.
