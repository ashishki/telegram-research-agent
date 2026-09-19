# Next-session Assignment — Complete Personal Assistant

You are implementing the owner's complete PA programme in this repository.
Do not reduce it to an MVP, rebuild completed old work, or implement everything
in one uncontrolled commit. Deliver successive user-visible vertical slices.

## Start

Read AGENTS.md and docs/CODEX_PROMPT.md. Establish actual branch/HEAD/status;
preserve unrelated work. Stay on the published PA branch or a child feature
branch, never modify master directly. Initialize the exact pinned development
submodule as documented, verify its identity, and run the planning checks.
Read the complete docs/PERSONAL_ASSISTANT_SPEC.md once for design/review,
then docs/design/PA.md and the PA.design.json registry.

This is a high-risk designed_slices programme. Use the pinned Feature Workflow
and required product/program design reviews. Do not set approval fields yourself.
Record the owner's exact interactive design approval before capability work.
Old PROJECT_BRIEF/PRM-SN completion is not approval of this new feature; the new
brief is docs/PERSONAL_ASSISTANT_BRIEF.md. When the upstream workflow requires
a project-level brief approval, present the new brief to the owner and update
the project intake reference/provenance explicitly rather than borrowing an old
approval marker or bypassing the check.

## Execute the complete programme

Select the first dependency-ready unfinished PA slice; PA-00 diagnoses the
current CI regression before expansion. Use tools/feature_workflow.py to plan,
start, render bounded context, check and record acceptance. A task-specific
request remains scoped; a full-programme assignment means continue to the next
ready step after its required gates, not stop after a framework skeleton.

For each code slice: inspect active call paths/I/O; add precise positive,
negative and failure-recovery acceptance tests; demonstrate the intended red
case when test-first is required; implement the smallest complete user journey;
run new tests plus the existing regression floor; wire new tests into project
verification. Current registry commands alone do not prove new features.

Use direct implementation in the current session's default Codex
model/reasoning mode, independent read-only risk reviews and scoped
corrections. The implementer never self-reviews. Each independent reviewer is
a fresh separate process requested as `gpt-5.6-terra` with `high` reasoning.
Use `tools/run_codex_role.py run` for any review role supported by the pinned
Role Runner; use fresh read-only `codex exec` for all other prescribed review
roles. Reviewers do not commit, push or fix their own findings. The implementer
or a separate scoped fix agent fixes P0/P1; a fresh independent reviewer then
rechecks the changed scope before a dependent slice proceeds. Deep Review runs
at the declared phase boundaries, not after every small patch, except for an
immediate safety trigger. Record requested and observed model/effort. Limit
correction loops as declared; unresolved real blockers remain explicit.

Commit/push only scoped, verified changes with honest evidence and the
applicable human authority. High-risk acceptance and live gates remain human.
Do not forge success to satisfy an end-to-end goal. Leave resumable checkpoint
artifacts whenever stopping; a later session resumes the first unfinished slice.

## Product non-negotiables

Natural dialogue and object-aware continuation; actual archive/web AI search;
beautiful weekly/topic Telegram/HTML/PDF/Markdown reports from one versioned
evidence object; quiet useful subscriptions; selected mail/calendar and
permitted Academic Inbox; confirmed writes with receipts/reconciliation;
inspectable memory; voice/document parity; quality-first measured model routing;
real recovery/privacy/security; actual owner usefulness and visual acceptance.

## Access and deployment

The owner is willing to provide access/models. Request only genuinely needed
account/provider permissions through secure setup, never tokens in chat/Git.
Plan implementation with synthetic fixtures until the relevant grant is present.
No service/timer, production DB, paid provider call or real send without a
specific approved scope and budget. Independent account/institution blockers
must not stop unrelated safe work, but an unconnected provider is not completed.
Keep all private evidence outside the public repository.

## Token discipline and final evidence

Read the current task, compact approved design, relevant spec sections and
bounded context, not the entire historical archive every turn. Reuse actual
receipts; do not repeat already-green unrelated evaluations or all reviewers
for small copy edits. Never remove risk gates for lower token use. Compare
cost per accepted task, not tokens alone.

Final acceptance is PA-18: requirement-to-implementation/test/review/live-evidence
matrix, real rendered visual review, current exact-HEAD project checks, permitted
provider pilot, and human acceptance. No fixture-only production/release claim.
