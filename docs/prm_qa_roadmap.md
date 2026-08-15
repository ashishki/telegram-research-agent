# PRM-QA Roadmap

Status: active
Date: 2026-08-15

PRM-QA is the active evaluation-led quality queue. It supersedes ad hoc
retrieval and UX polishing for this phase without deleting historical PRM,
PRM-UX, or PRM-MAT evidence.

## Milestones

- Milestone A: private dataset generator, layered eval harness, intent policy.
- Milestone B: retrieval ablation, selected policy ADR, evidence quality, claim
  ledger, grounding checks.
- Milestone C: project-decision clarification/memo, job-specific Telegram
  contracts, usefulness feedback receipts, private traces, primary-source
  verification slice.
- Milestone D: private holdout run, documentation, focused acceptance, commit,
  push, and handoff.

## Current State

Milestones A through D have implementation evidence in this branch, with two
important limitations:

- Dense retrieval was not adopted because no local dense runtime was installed
  and no holdout gain was measured.
- Automated task-success proxy is not a real operator usefulness claim.
