# Telegram Research Agent — Orchestrator Prompt

Canonical orchestrator prompt: [workflow_orchestrator.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/prompts/workflow_orchestrator.md)

Use that file as the single source of truth.

This alias exists only to prevent drift for older references.

Current workflow contract:

```text
Strategist -> Orchestrator -> Codex -> Review -> Fixes
```

Current roadmap order:
1. Memory Contract And Inventory
2. MVP Memory Unification
3. Wire Memory Into Weekly Outputs
4. Observability And Evaluation

Hard rules:
- do not skip dependency checks
- do not combine current-phase work with future-phase work
- do not proceed without quality gates
- do not use legacy roadmap generations as active execution source
- implementation and fix patches are written by Codex, not by the reviewer
- implementation and fix packets are handed to Codex via `codex exec -s workspace-write`
- do not leave `workflow_orchestrator.md` and this file inconsistent
