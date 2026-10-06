# PAI-01 durable design receipt — 2026-10-06

Engineering status: in_progress; reviewable design packet complete, mandatory
actual independent reviews and human approval pending.
Source HEAD: 8faee4232cb30e6b6f39cfbd974c151846f79da6, uncommitted local diff.
Actual reviewed commit/model: none. New PAI code slices are unimplemented.

## Prepared decision

Paired design: docs/design/PAI.md / docs/design/PAI.design.json.
Proposed ADR: docs/adr/ADR-013-pa-durable-runtime.md.
32 formal task scopes in docs/tasks.md; original PA registry remains unchanged.
The full specification was read for design. The draft covers complete product
outcomes, explicit table ownership, small PostgreSQL queue, versioned payloads,
fencing, atomic budgets/confirmations, a precommitted effect attempt with narrow
final locks, conservative unknown reconciliation, retention/deletion/restore,
test DB, load/SLO proposals and single-writer cutover/reverse-delta rollback.
It neither activates PostgreSQL nor claims a worker/integration is implemented.

Queue choice is a bounded own repository, avoiding a second state source.
Library/broker/Redis/archive migration alternatives and reconsideration triggers
are recorded. Test-only lease/concurrency/load parameters are proposals, not
live/financial consent. Every new suite is registered but explicitly absent
until implementation; structure checks do not stand in for vertical behavior.
Live/canary/release/pilot decision packet is PAI-access-release-pilot-packet.md;
actual runtime commands must be created/verified in PAI-24..26.

## Pinned workflow observations

python3 tools/playbook.py create_feature_design --root . --feature-id PAI
--planning-depth designed_slices --owner codex-direct --risk-level high
--brief-ref docs/PERSONAL_ASSISTANT_BRIEF.md
--architecture-ref docs/PA_SCALING_STRATEGY_2026-10-06.md
--architecture-ref docs/PA_IMPLEMENTATION_TASKS.md
was executed as one command: exit 0; real pinned scaffold produced the paired
draft. Existing PA records were not overwritten. The local bridge allowlist
exposes that pinned tool plus validate_feature_design, with forwarding tests.

python3 tools/playbook.py feature_workflow --root . plan --task PAI-01:
exit 1, needs_input, recommendation designed_slices. The actual project-level
PROJECT_BRIEF.md is draft. Decision artifact is
.playbook-artifacts/planning/PAI-01/planning_decision.json; no human fields set.

python3 tools/playbook.py feature_workflow --root . review --task PAI-01
--feature-id PAI --role auto:
exit 1, planning decision needs_input blocks workflow draft/start/check.
It was preparation/preflight only, no independent reviewer launched.

python3 tools/playbook.py validate_feature_design --root .
--design docs/design/PAI.design.json:
exit 0, schema/reference/dependency checks, 0 errors/warnings.
python3 tools/check_personal_assistant_plan.py: exit 0, original review_required.
python3 tools/check_pai_plan.py: exit 0, all 32 cards/PA coverage/dependencies;
28 future test files absent. Strict implemented-tests check exits 1.
Pinned task/reference validator exits 1 with 51 missing-approval errors;
19 are unchanged PA records, 32 are the new draft PAI scopes, no structural errors.

## Mimo review preparation and compatibility

The owner explicitly retained Mimo in the active session. The separate local
OpenCode design backend has synthetic proof of the genuine pinned generic
record writer/parser, honest provider/model telemetry and stale-hash denial.
Reports stay in .playbook-artifacts/opencode-runs/<id>/, not the old default
Codex report projection. That old projection would overwrite provenance with
codex_exec; do not feed these outputs through it. No Codex traces are forged.

Actual reviewer requested: mimo-v2.6-pro; observed: not run. Effort is not
requested for this API, observed effort unknown. No actual PASS/ADVISORY review
is claimed, and the new adapter needs independent review before real use.
Program packet includes full specification, exact paired design, boundaries,
review policy, ADR and the new runner source/changed transport definitions.
Registry whitespace is compacted without dropping a field/requirement.
All original document hashes are retained, including the non-repeated intake
brief. Total input is bounded to 200000 bytes; output request is really 8000
tokens. One provider request per process, no redirects or automatic retries.

Prepared safe command:
python3 tools/run_codex_role.py run --provider opencode-go --task PAI-01
--feature-id PAI --role program_design_review --prepare-only
Exit 0, provider_call false, genuine needs_input gate and exact packet hashes.
This is no reviewer verdict.

## Actual next gates

Owner brief approval question is bound to PROJECT_BRIEF.md SHA-256
7cf9adde93f48f17afef4707e02399c2a180339f4c3acc41e3520309cdfa8458.
Separate question asks two Mimo calls, each <=200 KB input/8000 output tokens,
no automatic retries/private payload. The owner answered “да, всё разрешаю” to both questions. The brief decision is
recorded; two bounded initial reviewer calls are authorized.
This explicit scope decision goes beyond the earlier model selection alone.

After real brief approval, rerun plan and obtain real human select-plan through
the pinned interactive workflow. Do not fake owner identity/TTY answers.
Then draft captures the exact current design-session boundary. Run independent
product/program Mimo reviews via the new backend only with agreed scoped call
limits/credentials for actual execution, never availability scanning. Resolve
P0/P1 and obtain independent recheck with additional scope if needed. The actual
hash-bound feature approval must occur through:
python3 tools/playbook.py feature_workflow --root . approve --feature-id PAI
This is a later human action after required review, not a command run here.

No approval fields, human acceptance or release state were hand-edited.
PAI-02..26 depend on this design gate. Continue the first ready card after it;
do not create a second authorization question for each already-assigned file.

Rollback: withdraw the draft through legitimate workflow/revert owned changes;
preserve prior PA states and other authors' work. No runtime/data changes.

## Authorized workflow continuation

After the owner decision, pinned plan returned ready (exit 0). Interactive
select-plan recorded assigned designed_slices (exit 0), with owner alias
human:owner entered under explicit delegation. Feature draft initially refused
the dirty tree; scoped checkpoint publication/preservation is being prepared.
No interactive feature approval or real independent verdict has occurred yet.

## Actual independent review attempts and bounded failure — 2026-10-06

Checkpoint SHA: 07f2475. The owner approved the exact project brief and two
bounded Mimo calls. Pinned draft succeeded on the clean scoped checkpoint;
design_session and planning selection are real workflow-generated artifacts.

Both independent processes ran the actual approved OpenCode Go request:
python3 tools/run_codex_role.py run --provider opencode-go --task PAI-01
--feature-id PAI --role program_design_review --allow-provider-egress --call-cap 1
--key-file <documented owner OpenCode Go credential file>
The matching product_design_review invocation used the second approved call.
The file was read only for these real authorized requests; its contents were
not printed, stored in reports or committed.

Program invocation exited 2: HTTPError. Product invocation exited 2:
TimeoutError (180 s request timeout). No valid model verdict, report or generic
review approval record was produced. Requested model: mimo-v2.6-pro; observed
model/effort/usage/cost: unknown, not invented. Both attempts count against the
approved cap, including the unknown outcome; there were no automatic retries.
Original runner retained only exception types, so HTTP status/body are unknown.
Post-hoc failure-from-tool-output.json records preserve that limitation in each
.playbook-artifacts/opencode-runs directory beside the exact input manifests.

Failure instrumentation now records prepared attempt, safe HTTP status/type,
request/hash/caps and unknown outcome, without provider body or credentials.
Program source is AST-normalized with exact original-byte hashes; complete
executable semantics/docstrings remain and no requirement field is dropped.
Current full-spec program packet is <200000 bytes; dry-run returns planning_gate
null and provider_call false. The targeted role/legacy-review tests pass:
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
tests/test_opencode_role_review.py tests/test_strategy_reviewer.py
Result: 28 passed in 8.00 s. No product code/provider fallback was changed.

Primary endpoint/model verification: https://opencode.ai/docs/go/ (checked
2026-10-06), matching mimo-v2.6-pro and /zen/go/v1/chat/completions. This public
reference does not prove key health, quota, API success or a reviewer verdict.

The initial two-call cap is exhausted. A concrete follow-up scope question asks
an overall cap of 30 local-program calls, or 8 for phase A only, still <=200KB
input, <=8000 output tokens, <=300 s timeout and no automatic retries/private
payload/model substitution. No answer is inferred from elapsed time.

Next safe preparation command:
python3 tools/run_codex_role.py run --provider opencode-go --task PAI-01
--feature-id PAI --role program_design_review --prepare-only
Actual repeats remain gated on the new explicit cap. Fix/review readiness and
hash-bound feature approval remain separate; none of PAI-02..26 is implemented.

Published continuation checkpoint: 985f8f2ecbbbe0ab28a62e8a4cd09295a0d2266e.
Both scoped commits were pushed to the assigned branch (exit 0). Pinned draft
was rerun on the clean hardening checkpoint. No actual reviewer verdict or
feature acceptance is inferred. The live HTTPError/timeout evidence remains.

## Navigator protocol correction and successful actual smoke

The owner requested inspecting the working Navigator invocation. Source commit
5f26418921246c3e24a967532225dfe3d274b1cb uses system/user, strict json_schema, fresh session UUID and
300 s timeout. Client aligned; 29 targeted tests pass. One tiny synthetic
connectivity probe for that new request succeeded with observed mimo-v2.6-pro
and usage 61+51=112 tokens. It is not a full design verdict or a renewal of the
exhausted two-review-call cap. Full details: PAI-MIMO-CALL-PROTOCOL.md.

## Automatic goal continuation audit — 2026-10-06

Authoritative entry HEAD: 84da33a84e05e76f8451ea4a4aebd8a6d57ab5ec; clean tree.
Previous goal turn classified progress: Navigator protocol fixed/published and
actual bounded synthetic connectivity evidence obtained. No valid full-design
review is proved: both actual design attempts have failure records, no generic
PAI design records exist. The successful connectivity result is schema_ok with
observed mimo-v2.6-pro, usage 61+51=112, valid_verdict=false.

No new call-budget response arrived. The original cap of two design attempts is
exhausted; diagnostic scope was one distinct owner-requested operation, already
performed. New 30/8-call scope and subsequent exact feature approval are still
required. No paid request, credential read or product implementation occurred
during this continuation.

Found stale contradictory current instructions (older checkpoint, no API/brief
decision asserted alongside actual calls/approval). Replaced them with one
current handoff/progress and aligned review policy. Full goal/32-card programme,
formal states, historic failures and pending reviews are preserved.
Changed files: docs/CODEX_PROMPT.md, docs/REVIEW_POLICY.md,
docs/verification/PAI-progress.md plus this receipt and hash manifest.
Next safe command is the actual --prepare-only role command in current handoff.

Audit commands: git status --short / git rev-parse HEAD confirmed the entry
state; safe inspection of the two failure artifacts and one connectivity result
confirmed three attempts and zero PAI design records. All following commands
exited 0: --prepare-only program role (199714-byte packet, planning_gate null,
provider_call false), tools/playbook.py --check-pin,
tools/check_personal_assistant_plan.py, tools/check_pai_plan.py,
tools/playbook.py validate_feature_design --root . --design docs/design/PAI.design.json,
git diff --check. Product tests were not rerun for this documentation-only
correction. Required paid-review scope remains unanswered; no dependent product
task can legally start. Goal is active; this is the second consecutive goal
turn with that remaining cap gate, with concrete reconciliation progress here.

## Owner resume and review funding

Owner message: “разрешаю, продолжи гол”. The recommended total 30-call cap for
the complete assigned local queue is now authorized, including all 3 prior
requests. Per-call bounds and source classes remain unchanged. Continue without
re-asking that scope; no feature/private/live/release approval is invented.

## Actual resumed design review and scoped remediation

Reviewed SHA: 04c4efa17c4fc10ad1db1a7e1acb4c1cbbd32d66.
Actual product reviewer requested/observed mimo-v2.6-pro; verdict STOP_SHIP,
two P1 and three P2. Usage 38730 input / 6304 output tokens. Immutable result:
.playbook-artifacts/opencode-runs/opencode-ccae625bd14a40b88cd808af1c475fc0/result.json.
Public report: PAI-01-product-review-04c4efa.md. Initial program response failed
the complete-response guard; no program verdict/approval is inferred.

Remediated P1: PAI-01 cannot edit src/tests/tools, including its checker; those
belong to independently reviewed code scopes. Added PAI.requirements.json with
all 69 exact spec IDs and all ten verbatim §13.2 scenarios, slice/path/test/review/
human bindings. PAI-26 explicitly enumerates them. Planned tests are obligations,
not passes. Checker additions are PAI-00 tooling and have negative drift tests.

P2 clarifications: permanent unknown spend is conservatively consumed, owner
visible and never refunded/retried silently; new work needs a new funded ID.
PostgreSQL tombstones block serving immediately while idempotent per-store
cleanup/watermarks truthfully remain partial during outage/restore. Scope
overlap checking confirms PAI-24 has no actual allow/deny overlap. Missing
future tests remain pending; missing existing regression files fail checking.

Lossless string/column factoring retains every registry/matrix field and is
roundtrip checked. Full-spec design packets remain below 200000 bytes.
Separate narrow --tooling-review audits the actual checker/transport but cannot
write full-design review evidence. JSON report limits prioritize concise P0/P1;
more independent blockers require STOP_SHIP and explicit remaining coverage,
not a false PASS. Provider thinking defaults/model are unchanged.

Exact targeted command:
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_plan.py tests/test_opencode_role_review.py tests/test_strategy_reviewer.py
Exit 0: 41 passed in 22.52 s. Schema/coverage checker passes: 69 IDs, 10 scenarios,
32 tasks; 28 new future suite files still absent.
Independent recheck of the changed paired design and tooling is next; no human
feature acceptance is claimed. Budget: five calls used before these rechecks.

## Scoped recheck results at bc2fb6a

focused-prm exit 0: 620 passed in 107.22 s.
Product recheck: observed mimo-v2.6-pro, finish_reason=length, 45928 input and
8000 completion tokens; no full verdict. Tooling audit: observed same model,
finish_reason=length, 27676 input and 8000 completion tokens; no full verdict.
Program full-design recheck: TimeoutError; outcome/model/usage unknown.
These are completed attempts, not live processes or acceptance records.
Sanitized failure snapshots are PAI-01-recheck-failure-opencode-*.json.
Eight total calls count against the authorized cap 30. No automatic repeats.

The required schema bounds/parser remain fail-closed; no truncated verdict was
promoted. A concrete question asks whether to increase only design-review output
to 16000 while keeping the same model/thinking mode, input/time/total-call/data
caps, or retain 8000 and explicitly split review scopes. Until that answer,
do not exceed 8000 or infer a successful independent recheck. The full programme
and actual P1 remediation remain intact; exact human design approval is pending.

## Explicit output-ceiling amendment

Owner answered “разрешаю, делай” to the concrete 16000-token design-review/
recheck option. Total call cap 30, input 200KB, selected Mimo/default thinking,
300 s timeout, no automatic retries and public/synthetic-only classes remain.
CLI now requires explicit --output-token-cap 16000; default stays 8000.
A provider/receipt test verifies the actual bound, not an invented measurement.
No private/live/feature approval is inferred from this funding amendment.

## Model latency and complete phase review strategy

All three 16000-token full-packet attempts on 61b3c50 exited TimeoutError at the
bounded 300 s timeout. Unknown outcomes count conservatively: 11 calls consumed
out of 30 before the next explicit attempts. No automatic restart/fallback.

The review scope is now split into foundation (00..06), product (07..15),
sources (16..20) and completeness (21..31), executed sequentially. Each carries
the complete shared architecture/contracts plus exact phase clauses, unchanged
source hashes, relevant requirements/scenarios and declared full-spec section
coverage. Together the phases cover every slice and every spec section 0..15;
this is partitioning work, never dropping a requirement or accepting a subset.
A phase cannot create a complete-design approval record.

The deterministic finalizer requires all four actual independent same-HEAD/
same-design/model/context-hash results, validates their exact slice/section
coverage and report hashes, and preserves the worst verdict. No implementer
review judgment is added. Missing phases, stale HEAD/context, mismatched
model/scope, or STOP_SHIP cannot become a full PASS. The generic pinned consumer
receives only that completed reviewed set. Model/thinking defaults remain the
owner's Mimo choice. No private/live authority or feature approval is invented.

## Actual narrow P1 recheck and remaining complete-design gate

Independent Mimo returned scoped PASS for both original P1 findings at e262f27.
Report: PAI-01-product-P1-recheck.json. Scope is exactly runtime/checker edit
permission and fine-grained requirement/scenario traceability. Its P2 notes that
paths resolve through slice_bindings, and its explicit limitations exclude full
programme/content/runtime/human approval. No complete-design record is minted.

Full and first phase 300 s calls continued to time out. The current remaining
blocker is complete programme review under the response deadline, not those
two P1s. Four-phase aggregation covers all 32 slices/spec sections 0..15 and
denies partial/stale results; targeted tests: 47 passed in 10.20 s. Actual full
records still absent. Failed/unknown attempts all count: 14 calls used of 30.
All model processes observed here are terminal; no live handle is inferred
from old files. Current question proposes only a bounded deadline extension
900 s for design calls, preserving data/model/thinking/input/output/total caps.
Until answered, no request may silently exceed 300 s.

Next safe command:
python3 tools/run_codex_role.py run --provider opencode-go --task PAI-01 --feature-id PAI --role program_design_review --slice-group foundation --prepare-only
After deadline choice: rerun actual phases sequentially, complete both required
roles and tooling audit, resolve/recheck any remaining findings, then seek the
actual hash-bound human feature approval. PAI-02..26 remain unimplemented.
