# Telegram Research Agent — Orchestrator Prompt

Canonical orchestrator prompt: [workflow_orchestrator.md](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/prompts/workflow_orchestrator.md)

Use that file as the single source of truth.

This alias exists only to prevent drift for older references.

Current workflow contract:

```text
Strategist -> Orchestrator -> Codex -> Review -> Fixes
```

Current roadmap order:
1. Baseline Stabilization
2. Scoring Foundation
3. Model Routing
4. Signal-First Output
5. Project Relevance Upgrade
6. Personalization / Taste Model
7. Learning Layer Refinement
8. Productization / Surface Layer

Hard rules:
- do not skip dependency checks
- do not combine current-phase work with future-phase work
- do not proceed without quality gates
- do not leave `workflow_orchestrator.md` and this file inconsistent
