# Telegram Research Agent — Development Cycle

**Version:** 1.0.0
**Date:** 2026-03-16
**Status:** Baseline

---

## Overview

This document defines the development process, role responsibilities, iteration protocol, and communication contracts for building the Telegram Research Agent.

All work follows a contract-first, iterative cycle:

```
Strategist → Codex → Review → Fix → Update Docs → next phase
```

---

## Roles

### 1. Strategist (Claude Code — this instance)

**Owns:**
- System architecture
- Data contracts and interface definitions
- Phase sequencing and task graph
- LLM prompt templates (in `docs/prompts/`)
- Review of architectural drift
- Living document updates at major milestones

**Does NOT:**
- Write application code
- Create `src/` files (except config schemas and prompt templates)
- Install system packages

---

### 2. Codex Implementer

**Owns:**
- All `src/` Python code
- `scripts/` shell scripts
- `systemd/` unit files
- `data/` directory initialization
- `.gitignore`, `requirements.txt`

**Operating constraints:**
- Implements tasks from `docs/tasks.md` in phase order
- Does not skip phases
- Does not modify `docs/` without being instructed
- Does not modify `/opt/openclaw/src`
- Does not store secrets in the workspace
- Marks completed tasks `[x]` in `docs/tasks.md`

---

### 3. Claude Reviewer

**Owns:**
- Phase-completion review
- Verification against `docs/spec.md` and `docs/architecture.md`
- Security and isolation review
- Prompt contract verification

**Output:**
- Review report: PASS or list of specific issues
- Issues are concrete (file + line reference if possible)
- Reviewer does NOT fix issues; reports them for Codex Fixer

---

### 4. Codex Fixer

**Owns:**
- Applying reviewer-identified fixes
- Re-running verification steps
- Updating `docs/tasks.md` status after fixes

---

## Phase Iteration Protocol

### Start of Phase

Before Codex begins a phase:

1. Verify all prerequisite phases are `[x]` in `docs/tasks.md`.
2. Re-read `docs/architecture.md` relevant section.
3. Re-read the phase's tasks in `docs/tasks.md`.
4. Note any `[!]` blocked tasks and resolve before starting.

### During Phase

- Implement tasks in the order listed in `docs/tasks.md`.
- Mark each task `[~]` when started, `[x]` when complete.
- Do not mark a task `[x]` until it is tested (at minimum: runs without crashing).

### End of Phase

Codex must:
1. Mark all phase tasks `[x]` in `docs/tasks.md`.
2. Ensure no debugging artifacts, print-dumps, or test files are left in `src/`.
3. Verify `.gitignore` covers all sensitive files.
4. Signal to Reviewer that the phase is complete.

---

## Review Protocol

When a phase is complete, Claude Reviewer:

1. Reads all new/modified files in `src/`, `scripts/`, `systemd/`.
2. Checks against the Phase Review Criteria in `docs/tasks.md`.
3. Checks against the Claude Review Checklist in `docs/spec.md` Section 20.
4. Produces a review result in one of two forms:

**PASS:**
```
Phase N Review: PASS
All criteria met. Proceed to Phase N+1.
```

**ISSUES:**
```
Phase N Review: ISSUES FOUND

Issue 1: [file:line] Description of issue. Expected: X. Actual: Y.
Issue 2: ...

Fix required before Phase N+1 begins.
```

---

## Fix Protocol

When issues are found:

1. Codex Fixer reads the review output.
2. Fixes each issue.
3. Does NOT introduce changes beyond what is needed to fix the stated issues.
4. Marks fixed tasks with `[x]` and appends `(fixed)` to the task description.
5. Signals Reviewer for re-review.

Re-review is a targeted check only of the fixed items, not a full phase re-review.

---

## Living Document Update Rules

| Trigger | Document to update |
|---|---|
| Architecture decision changed | `docs/architecture.md`, `docs/spec.md` |
| New task added mid-phase | `docs/tasks.md` |
| Security requirement changed | `docs/ops-security.md` |
| Phase completed | `docs/tasks.md` (status update) |
| Major milestone (phase group complete) | All 5 docs — version bump, date update |

**Rules:**
- Never create `spec_v2.md`, `architecture_final.md`, etc.
- Always edit the existing file.
- Update the `Version` and `Date` header fields.
- Keep documents compact. Remove superseded content rather than appending both old and new.

---

## Prompt Template Ownership

LLM prompts live in `docs/prompts/`. They are:
- Written by the Strategist (or reviewed by the Strategist if Codex drafts them).
- Loaded from disk by application code (not hardcoded).
- Versioned as part of the document set.

**Format for prompt template files:**

```markdown
# Prompt: [Name]

## Purpose
One sentence.

## Input Variables
- `{variable_name}`: description

## System Prompt
[system prompt text]

## User Prompt Template
[template with {variable} placeholders]

## Expected Output Format
[description or example]
```

---

## Communication Between Agents

Since Codex and Claude operate in separate contexts, the living documents are the primary communication channel.

**State is always encoded in:**
- `docs/tasks.md` — what has been done and what is next
- `docs/spec.md` — what the system should do
- `docs/architecture.md` — how it should be structured

**No state lives in Slack, emails, or informal notes.**

When picking up a task after a context gap, Codex should:
1. Read `docs/tasks.md` to find the last `[x]` task.
2. Read `docs/architecture.md` for the component being implemented.
3. Proceed with the next `[ ]` task.

---

## Definition of Done (MVP)

The MVP is complete when:

- [ ] All Phase 1–8 tasks are `[x]`
- [ ] All Phase 9 hardening tasks are `[x]`
- [ ] At least one full weekly cycle has completed successfully (ingestion → normalization → topics → digest → recommendations)
- [ ] Digest output file exists at `data/output/digests/`
- [ ] Recommendations output file exists at `data/output/recommendations/`
- [ ] Systemd timers are enabled and validated
- [ ] No secrets committed to workspace
- [ ] All living docs reflect current state

---

## Anti-Patterns to Avoid

| Anti-pattern | Why |
|---|---|
| Writing code before reading the architecture doc | Leads to drift and rework |
| Marking tasks `[x]` without testing | Hides real blockers |
| Hardcoding secrets or API credentials | Security violation |
| Creating duplicate documentation files | Breaks the single-source-of-truth principle |
| Skipping phases because they "seem simple" | Phases have explicit review gates |
| Modifying OpenClaw source | Corrupts the verified runtime baseline |
| Storing session files in the workspace | Session leakage risk |
| Calling LLM with raw corpus | Cost explosion; architecture violation |
