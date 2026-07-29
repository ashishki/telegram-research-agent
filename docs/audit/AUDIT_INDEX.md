# Audit Index — telegram-research-agent

**Status:** active index only

---

## Active Rule

`docs/audit/` should contain only the current audit index and any actively referenced current-cycle review material.

Legacy review artifacts and old review prompts have been moved out of the hot path to reduce noise for future agent sessions.

Archive location:

- `docs/archive/legacy_audit/`

---

## Archived Material

Archived files include:

- historical phase reviews
- superseded review reports
- old review-cycle prompt bundles
- roadmap-v2 / roadmap-v3-era audit analysis

These files remain preserved for human reference, but they are no longer part of the active AI-development contract.

## Current-Cycle Reviews

- `PRM_BLOCK_REVIEW_2026-07-26.md` - corrective PRM block review after missed
  PRM-2, PRM-4, PRM-6, and PRM-7/PRM-8 review gates.
- `PRM_DEEP_REVIEW_CONSOLIDATED_2026-07-27.md` - meta/architecture/code
  Codex subagent review consolidation and corrective test-tier evidence.
- `PRM_BLOCK_REVIEW_2026-07-27_PRM9_12.md` - PRM-9 through PRM-12 assistant
  router, grounded answer, external verification, and confirmation-gated write
  block review receipt.
- `PRM_DEEP_REVIEW_PRM9_12_2026-07-27.md` - PRM-9 through PRM-12 corrective
  deep review with meta/process, architecture/privacy, and code/tests reviewer
  findings and repair evidence before PRM-13.
- `PRM13_KNOWLEDGE_LIBRARY_2026-07-27.md` - PRM-13 Knowledge Library
  topic-page implementation receipt, fixture visual/layout evidence, and
  continuation boundary for the PRM-13 through PRM-17 block.
- `PRM14_PROJECT_CONTEXT_2026-07-28.md` - PRM-14 project context and
  decision-support implementation receipt, deterministic relevance evidence,
  and continuation boundary for the PRM-13 through PRM-17 block.
- `PRM15_LEARNING_STATE_2026-07-29.md` - PRM-15 learning-state correction and
  fixture-only migration evidence, explicit receipt requirements, and
  continuation boundary for the PRM-13 through PRM-17 block.
- `PRM16_WEEKLY_BRIEF_V3_2026-07-29.md` - PRM-16 Weekly Brief V3 deterministic
  projection, generic fallback guard, Radar-failure localization, static visual
  receipt, and continuation boundary for the PRM-13 through PRM-17 block.
- `PRM17_RUNTIME_WORKFLOWS_2026-07-29.md` - PRM-17 autonomous workflow
  contract, privacy-safe aggregate telemetry, cost/rollback evidence, and stop
  boundary for the PRM-13 through PRM-17 deep-review gate before PRM-18.
- `PRM_DEEP_REVIEW_PRM13_17_2026-07-29.md` - PRM-13 through PRM-17 batched
  deep review, telemetry budget-validation repair, verifier receipt, and
  release boundary before PRM-18.
- `PRM18_RELEASE_GATE_2026-07-29.md` - PRM-18 deterministic release/dogfood
  gate receipt, stop-ship blockers, privacy boundary, verifier evidence, and
  PRM-19/PRM-20 continuation blockers.
- `PRM_RUNTIME_FREEZE_2026-07-29.md` - runtime freeze receipt after PRM-18:
  old Report V2 timer and live bot stopped/disabled, post-freeze systemd/cron
  checks, and historical W30 artifact boundary.
- `PRM_SAFE_ASSISTANT_RUNTIME_2026-07-29.md` - safe `prm-assistant` runtime
  receipt: CLI entrypoint and repo unit template implemented, legacy generation
  and direct-write bot surfaces blocked, callbacks disabled, and activation
  still gated by explicit PRM-19 dogfood-start approval.
