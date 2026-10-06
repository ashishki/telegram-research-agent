# Current session handoff — PAI

Updated: 2026-10-06
Branch: docs/personal-assistant-blueprint-playbook-20260918
Latest implementation/tool checkpoint: 84da33a84e05e76f8451ea4a4aebd8a6d57ab5ec (published)
Initial source: 8faee4232cb30e6b6f39cfbd974c151846f79da6
Pin: d570163ab17ec3b4245187c778f1e8d89af9690f

## Assignment and actual current state

The owner assigned the complete Sol queue and requested a persistent goal.
Goal is active and the full programme is unfinished. Safe local PAI-00..26,
synthetic fixtures and isolated test PostgreSQL in PAI-02 are authorized.
The exact feature design, real accounts/private egress, jobs/services/timers,
production migration/deployment and release retain their separate gates.
PAI-27..29 currently have a preliminary decision packet, not live completion.
Conditional Redis/archive transfer have no measured trigger; do not execute them.

PAI-00 is local_verified; phase-A independent review remains pending.
PAI-01 has a reviewable paired draft and is blocked_external on review budget/
missing actual product/program verdicts. All PAI-02..26 depend on that design
gate. No PAI product implementation or acceptance is claimed by this handoff.

## Existing owner decisions — preserve these

The owner selected OpenCode Go/mimo-v2.6-pro for independent reviews.
The owner approved the exact project-brief hash and two initial bounded Mimo
design-review calls. PROJECT_BRIEF.md records the actual brief decision;
it does not approve the paired feature design or live accounts/deployment.

Pinned PAI-01 plan returned ready. Interactive select-plan recorded the assigned
designed_slices under explicit delegation with human:owner as alias. Pinned draft
created the real design session. No human feature approval fields were set.
Do not re-request these brief/model/planning decisions.

## Model evidence and remaining call scope

Two independent design processes actually attempted the approved requests on
07f2475: program -> HTTPError, product -> TimeoutError. Neither produced a valid
verdict/report/generic approval record. Observed model, usage and cost of those
attempts are unknown. Both attempts consumed the initial two-review-call cap.
Exact input manifests and conservative failure-from-tool-output records remain
in .playbook-artifacts/opencode-runs/. No raw provider body/key was saved.

The owner's subsequent request to find the working Navigator invocation led to
read-only inspection of its fix/dialogue-task-state-20260920 commit
5f26418921246c3e24a967532225dfe3d274b1cb. The client now uses system/user messages,
strict json_schema, fresh session UUID and bounded 300 s judge timeout.
The one tiny synthetic diagnostic for that new request succeeded: actual model
mimo-v2.6-pro, JSON schema valid, 61 input + 51 output = 112 tokens.
This is authenticated connectivity evidence, never a design verdict.

Total actual Mimo requests: 3 (2 failed design attempts + 1 successful diagnostic).
The owner now explicitly answered “разрешаю, продолжи гол” and resumed work.
The recommended total cap is 30 Mimo calls across local PAI-00..26, including
the three previous calls: 27 remain before the next actual attempts.
Each call stays <=200KB project/synthetic input, <=8000 output tokens,
<=300s timeout, without automatic retries/private payload/model substitution.
This expands review funding only; exact design/live/release gates persist.

## Design, verification and runner

Sol assignment: docs/prompts/pa_sol_implementation.md.
Queue/formal tasks: docs/PA_IMPLEMENTATION_TASKS.md and docs/tasks.md.
Paired execution feature: docs/design/PAI.md and PAI.design.json, draft.
Proposed runtime decision: docs/adr/ADR-013-pa-durable-runtime.md.
Evidence: docs/verification/PAI-progress.md, PAI-00-reconciliation.md,
PAI-01-durable-design.md and PAI-MIMO-CALL-PROTOCOL.md.

Original PA feature remains review_required and its formal states are preserved.
New formal PAI states remain planned. The validator has 51 approval errors
(19 original + 32 draft PAI), not structural errors. All 32 mappings/dependencies
pass the PAI checker; 28 future test files are absent, and strict implemented-test
mode exits 1. These are planning checks, never completed product behavior.

focused-prm passed 609 at the earlier checkpoint. Latest relevant transport/
legacy-review tests passed 29 after the Navigator protocol correction.
The two date-dependent fixture regressions are corrected without weaker
assertions. Full historical pytest is prohibited; product runtime/provider/
visual/usefulness acceptance is distinct from all this evidence.

The local --provider opencode-go route supports product/program design via the
actual pinned generic record writer/parser with honest opencode_go binding.
It produces a separate OpenCode evidence schema, never Codex events/receipts.
Native old feature_workflow review would relabel its default reports codex_exec;
do not copy these reports to that path or refresh them through that projection.
Other non-Codex review roles need a scoped extension before being credited.
No-provider run fails closed; implementer model/mode is unchanged.

## Preservation and executable continuation

Work is directly on the assigned branch, never master; no reset or force-push.
Two unrelated files remain untouched in local Git info/exclude:
UTD_intelligence_layer_research_report.md and docs/prompts/astra6_strategy.md.
Historical entering handoff: docs/CODEX_PROMPT.before-pai-20261006.md.
No production DB/service/timer/account was changed. Keys were read only for
the three actual authorized operations, never to check availability.

Safe next command (no key lookup or provider request):
python3 tools/run_codex_role.py run --provider opencode-go --task PAI-01 --feature-id PAI --role program_design_review --prepare-only

After a new explicit call cap: freeze HEAD/documents, run actual program/product
Mimo reviews, fix P0/P1 with independent recheck, then obtain exact hash-bound
feature approval through the pinned workflow. Proceed to the first ready card
without per-file consent. Do not restart completed historical PA slices.

## Latest review checkpoint

Owner funded total 30 Mimo calls and design/recheck output up to 16000. Fourteen
attempts including failures/diagnostic count against it. Original product P1
scope/traceability findings now have actual independent scoped PASS; this does
not approve the whole design. Full and phase requests hit 300 s timeout.
The complete four-phase review/finalizer preserves all 32 slices and spec 0..15
and cannot promote partial evidence. Source and report details:
docs/verification/PAI-01-durable-design.md and PAI-01-product-P1-recheck.json.
Owner deadline-extension question (900 s, other bounds unchanged) is pending;
do not infer consent or spend more calls blindly. Required full programme
reviews/feature approval precede dependent PAI code work.
