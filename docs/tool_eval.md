# Tool Evaluation Plan

Status: draft

## Tool Classes

Read-only tools:

- search archive;
- search curated knowledge;
- list reactions;
- get topic/project/saved context;
- get recent changes;
- get Radar status;
- request external verification.

Confirmation-gated proposal tools:

- propose Knowledge Note;
- propose Watch Topic;
- propose project link;
- propose action;
- propose experiment;
- propose feedback.

## Evaluation Checks

- tool schema rejects unexpected fields;
- read-only tools do not mutate SQLite or files;
- proposal tools do not write until confirmation;
- trace records tool name, arguments class, latency, result count, evidence
  status, and termination reason;
- unsafe/mutation tool names remain blocked;
- external verification is labelled separately from Telegram evidence.

## Stop-Ship Cases

- automatic profile/config/project mutation;
- assistant runs code edits or Codex;
- raw corpus text in ordinary logs;
- external skill reads secrets without trust approval;
- no-answer query produces unsupported claim.
