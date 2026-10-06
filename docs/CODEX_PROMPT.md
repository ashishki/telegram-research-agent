# Current session handoff — PAI

Updated: 2026-10-06
Branch: docs/personal-assistant-blueprint-playbook-20260918
Latest code/tool checkpoint: 985f8f2ecbbbe0ab28a62e8a4cd09295a0d2266e (published)
Initial source: 8faee4232cb30e6b6f39cfbd974c151846f79da6
Pin: d570163ab17ec3b4245187c778f1e8d89af9690f

## Assignment and current stop point

The owner assigned the latest Sol task pack end to end and requested a goal.
Goal is active, full programme incomplete. Safe local PAI-00..26 implementation,
synthetic tests and isolated test PostgreSQL in PAI-02 are authorized. Exact
feature design, real accounts/private egress, services/timers, production
migrations/deploy and release keep their explicit gates.

PAI-00 is local_verified, with independent phase-A review still pending.
PAI-01 has a concrete draft but is blocked_external on actual reviewer evidence.
Do not implement dependent PAI-02..26 before the required exact design gate.
PAI-27..29 are prepared only as preliminary access/release/pilot decisions;
actual runtime CLI/runbook and real acceptance remain future work. Redis/archive
migration are conditional and neither measured condition is satisfied here.

## Recorded owner decisions — do not re-ask these

The owner explicitly retained OpenCode Go/mimo-v2.6-pro as independent reviewer.
The owner answered “да, всё разрешаю” to the exact project-brief hash and two
bounded initial Mimo design-review calls. PROJECT_BRIEF.md records that real
brief decision; it is not feature approval or account/deployment authority.

Pinned plan PAI-01 returned ready. Pinned interactive select-plan recorded the
assigned designed_slices under explicit delegation, with human:owner as alias.
Pinned draft generated the real design_session on the clean committed tree.
No approval fields were hand-edited and no independent verdict was invented.

Both authorized API attempts were actually made against 07f2475:
program_design_review -> HTTPError; product_design_review -> TimeoutError.
No valid reviewer report/approval record exists. Requested model Mimo; observed
model/effort/usage/cost unknown. Original failure status/body was unavailable.
Exact input manifests and conservative failure-from-tool-output records stay in
.playbook-artifacts/opencode-runs/. No raw error body/credential was logged.

Two design attempts consumed the initial review cap, including failures/unknown outcomes.
The follow-up question offers total 30 bounded calls for local PAI-00..26,
or 8 for phase A, or retaining cap 2. It is still unanswered. Do not infer
consent from elapsed time or the UI default, and do not repeat model calls yet.

## Current design, runner and evidence

Sol entrypoint: docs/prompts/pa_sol_implementation.md.
Engineering queue: docs/PA_IMPLEMENTATION_TASKS.md.
Formal tasks: PAI-00..31 in docs/tasks.md, paired draft feature PAI.
Design: docs/design/PAI.md / PAI.design.json; draft, human_required.
Proposed runtime: docs/adr/ADR-013-pa-durable-runtime.md.
Progress and receipts: docs/verification/PAI-progress.md,
PAI-00-reconciliation.md and PAI-01-durable-design.md.

Original PA registry remains review_required and its 19 formal task states
are preserved. New formal PAI states remain planned; coverage does not create
completion. Task/reference validator has 51 missing-approval errors (19 old +
32 draft PAI), no structural/reference errors. The PAI checker validates all
32 mappings/dependencies; 28 future acceptance test files are absent. Strict
implemented-tests mode exits 1. Do not treat structure as implementation proof.

Local Role Runner --provider opencode-go handles product/program design roles
via the actual pinned generic design-record writer/parser and an honest
opencode_go binding. Separate assistant.opencode_design_review evidence is not
a Codex role-run trace. The native old review projection would rewrite binding
as codex_exec: never copy OpenCode reports into its default Codex report path
or refresh them through that projection. Approve reads the genuine generic
records after actual successful reviews. Other non-Codex role support remains
a future scoped extension. No-provider run fails closed, no Codex fallback.

Latest failure hardening records safe HTTP status/type, attempt/caps and unknown
outcome, without error bodies/secrets. Input <=200000 bytes, actual output cap
8000 tokens, one request per process, no redirects/automatic retries. Full
specification/requirements are preserved; registry whitespace and program-source
AST formatting are normalized with exact original-byte hashes retained.

Focused-prm passed 609 tests in 128.75 s at the first checkpoint. After failure
instrumentation, role/legacy-review targeted tests passed 28 in 8.00 s.
Two fixed baseline tests mixed historical fixture dates with current clocks;
their denial/source assertions remain. Historical PA-00 UX regression passes.
Actual Mimo integration failed; product provider/owner/runtime acceptance is
not established by these synthetic tests.

## Preservation and resume

Two unrelated local documents are unchanged and excluded only via local
Git info/exclude: UTD_intelligence_layer_research_report.md and
docs/prompts/astra6_strategy.md. Owner-provided strategy/queue prerequisites
were included in the scoped checkpoint. No master edit, reset or force push.
The entering historical handoff is CODEX_PROMPT.before-pai-20261006.md.
No production DB/service/timer/account was touched; keys were read only for
the two expressly authorized review requests, never availability scanning.

Safe next command, no API call:
python3 tools/run_codex_role.py run --provider opencode-go --task PAI-01 --feature-id PAI --role program_design_review --prepare-only

After new bounded calls are authorized: run the actual program/product roles
with --allow-provider-egress --call-cap 1 and --timeout-seconds 300 using the
documented key file for execution only. Each attempt counts against the total.
Freeze HEAD/documents during a review, resolve P0/P1 with independent recheck,
then get exact hash-bound feature approval through the pinned workflow. Continue
the first ready assigned card without repeated per-file consent.

## Latest Mimo method correction

Owner requested checking the working Navigator client. Commit 5f26418921246c3e24a967532225dfe3d274b1cb
uses separate system/user messages, strict json_schema, a fresh session UUID
and 300 s judge timeout. Shared client is now aligned; 29 targeted tests pass.
One bounded synthetic diagnostic for that new request succeeded: actual model
mimo-v2.6-pro, strict JSON, 61 input + 51 output tokens. No design verdict is
inferred. Total actual requests are 3; the original 2-review cap is exhausted.
See docs/verification/PAI-MIMO-CALL-PROTOCOL.md. Overall follow-up cap is still
pending; after it is authorized, use the corrected client for full independent
program/product reviews and then the exact design approval gate.
