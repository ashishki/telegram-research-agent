# Current session handoff — PAI

Updated: 2026-10-06
Branch: docs/personal-assistant-blueprint-playbook-20260918
Source HEAD: 8faee4232cb30e6b6f39cfbd974c151846f79da6
Pin: d570163ab17ec3b4245187c778f1e8d89af9690f

## Current assignment and stop point

The owner assigned the latest Sol task pack end to end and requested a goal.
Safe local PAI-00..26 implementation and synthetic tests are authorized,
including isolated test PostgreSQL within PAI-02. Design approval, paid egress,
live accounts, delivery/services/timers, production migrations/deploy and release
remain distinct gates. Goal remains active; the full programme is not completed.

Current work is PAI-00 baseline/reconciliation and PAI-01 exact draft design.
Use docs/verification/PAI-progress.md and the two receipts for actual results,
next work and limitations. All formal PAI states remain planned; original PA
design remains review_required. Do not restart PA-00..17 based on planned alone.

## Current files and registration

Sol entrypoint: docs/prompts/pa_sol_implementation.md.
Engineering queue: docs/PA_IMPLEMENTATION_TASKS.md.
New formal tasks: PAI-00..31 in docs/tasks.md, feature PAI.
Paired design: docs/design/PAI.md / PAI.design.json; draft, human_required.
Proposed runtime decision: docs/adr/ADR-013-pa-durable-runtime.md.
Original PA tasks/registry are preserved with their historical evidence.

There are two conditional cards, Redis/archive transfer; neither condition is
measured or satisfied here. Do not silently make them release dependencies.
PAI-27..29 need actual access/release/pilot evidence for PA-18 completion.

## Evidence and known gates

See current receipts for targeted tests and focused tier results. The final current-scope focused-prm tier passed 609 tests in 128.75 s.
The historical PA-00 confirmation UX failure passes; a current conversation
fixture mixed fixed September data with wall time. The correction controls
time and tests missing-version denial, expired confirmation and expired state.
This is a test repair, no runtime authorization change.

The owner’s September 23 non-Codex review amendment supersedes older Terra
recipes. docs/REVIEW_POLICY.md records role/runner/receipt compatibility.
The owner reconfirmed Mimo in this session. Native upstream harness is Codex-
only; the local --provider opencode-go backend now prepares product/program
packets and supports genuine generic pinned design records with honest non-Codex
binding. Its separate evidence is not a Codex receipt. Code-range advisory
reports still do not supply design-role records. Synthetic adapter checks pass;
actual independent review awaits brief/planning and explicit call limits. The owner now explicitly authorized the exact brief and two initial bounded
Mimo design-review calls (<=200KB input, <=8000 output tokens, no retries/private
payload); credential access is only for those actual calls.

Pinned planning for PAI-01 now returns ready: the owner approved the exact
project brief; selected depth is the assigned designed_slices, recorded through
interactive select-plan under delegation.
No human selection/approval fields were synthesized. Mandatory independent
product/program reviews and exact hash-bound human design approval are pending
before dependent PAI-02..26 work. Prepare authorized independent work meanwhile.

## Preservation and continuation

At entry, CODEX_PROMPT/tasks were modified and task pack/Sol/strategy/Astra/UTD
documents were untracked. Relevant queue documents were updated in scope;
unrelated Astra/UTD/strategy content is untouched. Original entering handoff is
docs/CODEX_PROMPT.before-pai-20261006.md, retaining amendment provenance.
The older September checkpoints are historical references, not competing tasks.
No private data, production database, service, timer or key was read/changed.

Next command:
python3 tools/playbook.py feature_workflow --root . plan --task PAI-01

The brief/planning decision is recorded; do not rerun it without drift.
Then select-plan/draft/review and exact approve through the pinned workflow;
do not fake interactive answers or import old PA approval. Fix P0/P1 with
independent recheck and continue the first ready card without asking per file.

Safe reviewer packet command, already exercised without API calls:
python3 tools/run_codex_role.py run --provider opencode-go --task PAI-01 --feature-id PAI --role program_design_review --prepare-only
It reports the real planning gate and exact packet hash; never a review verdict.
