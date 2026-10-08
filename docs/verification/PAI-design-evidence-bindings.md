# Design review 65 — explicit evidence/authority bindings

## 10. Concrete evidence/authority bindings — 2026-10-08

PAI-00 owns instruction/tooling reconciliation; PAI-01 owns feature-design
publications. B..F own runtime changes/source-review publications. These distinct
file scopes preserve all32 slices and grant no task acceptance.

PAI-00/reconciliation_regression registers these EXISTING tests in BOTH its
verification argv and matrix.slice_bindings.PAI-00.test_files:
tests/test_playbook_bridge.py, tests/test_assistant_conversation.py,
tests/test_prm_product_ux_eval.py, tests/test_pai_plan.py,
tests/test_opencode_role_review.py, tests/test_memory_research.py,
tests/test_pai_acceptance_guard.py. They are not future placeholder tests.
check_pai_plan.py rejects a card test absent from its slice registration; the
separate requirement case names do not replace infrastructure regression tests.

The pre-implementation checker tools/check_pai_plan.py compares FULL raw spec,
Markdown cards, task blocks, registry and matrix. It rejects missing/duplicate69
IDs, stale spec/matrix hashes, dependency/binding/scope drift, unknown verification
IDs, exact SC13.2-01..10 source-text/registered-node/recovery mismatches and case
names aliased to another spec ID. Later run_pai_acceptance.py requires ACTUAL69
binding case names and every scenario/recovery node in observed JUnit, zero
skips/failures/empty runs. Structural planning is not runtime proof. Conditional
PAI-30/31 missing suites remain explicit until a measured trigger.

Baseline: docs/verification/PAI-00-reconciliation.md, source
8faee4232cb30e6b6f39cfbd974c151846f79da6. It records exact clock-fixture
reproductions/root causes/fix decisions/commands and before/after results for
confirmation expiry and recent-posts windows. Historical PA-00 UX was already
repaired, not a new incident. Later failures/snapshots/hashes remain in
PAI-validation-20261008.json; source proof is dated and never projected forward.

PAI-00 manifest: docs/verification/PAI-00-file-manifest.json.
Count 58, limit64; SHA256 a09e5c4f966d8ec4545120854bfa0e316c156bffa8faa1c9493caa8bf13d8748.
Exact named scope paths:
- .playbook/instruction_manifest.json
- .playbook/project_verification.json
- AGENTS.md
- README.md
- docs/ARCHITECTURE.md
- docs/ASSISTANT_BOUNDARIES.md
- docs/CODEX_PROMPT.before-pai-20261006.md
- docs/CODEX_PROMPT.md
- docs/IMPLEMENTATION_CONTRACT.md
- docs/PA_IMPLEMENTATION_TASKS.md
- docs/PA_SCALING_STRATEGY_2026-10-06.md
- docs/PERSONAL_ASSISTANT_BRIEF.md
- docs/PLAYBOOK_ADOPTION.md
- docs/PROJECT_BRIEF.md
- docs/REVIEW_POLICY.md
- docs/adr/ADR-012-pa-assignment-and-instruction-scope.md
- docs/adr/ADR-013-pa-durable-runtime.md
- docs/design/PAI.design.json
- docs/design/PAI.md
- docs/design/PAI.requirements.json
- docs/prompts/ORCHESTRATOR.md
- docs/prompts/pa_sol_implementation.md
- docs/prompts/personal_assistant_implementer.md
- docs/prompts/prm_search_news_implementer.md
- docs/prompts/prm_search_news_reviewer.md
- docs/prompts/workflow_claude_reviewer.md
- docs/prompts/workflow_codex_fixer.md
- docs/prompts/workflow_codex_implementer.md
- docs/prompts/workflow_orchestrator.md
- docs/prompts/workflow_quickref.md
- docs/tasks.md
- docs/verification/PAI-00-file-manifest.json
- docs/verification/PAI-00-reconciliation.md
- docs/verification/PAI-MIMO-CALL-PROTOCOL.md
- docs/verification/PAI-MIMO-SSE-diagnostic.json
- docs/verification/PAI-progress.md
- docs/verification/PAI-review-continuation-41.json
- docs/verification/PAI-review-continuation-43.json
- docs/verification/PAI-review-continuation-44.json
- docs/verification/PAI-review-continuation-66.json
- docs/verification/PAI-review-continuation.json
- docs/verification/PAI-tooling-maintenance-packet.md
- docs/verification/PAI-working-tree-evidence.json
- tests/test_assistant_conversation.py
- tests/test_memory_research.py
- tests/test_opencode_role_review.py
- tests/test_pai_acceptance_guard.py
- tests/test_pai_plan.py
- tests/test_playbook_bridge.py
- tools/check_pai_plan.py
- tools/finalize_opencode_design_reviews.py
- tools/mimo_code_review.py
- tools/opencode_role_review.py
- tools/playbook.py
- tools/run_codex_role.py
- tools/run_pai_acceptance.py
- tools/test_tiers.py
The checker mechanically validates unique path/count/limit/registry budget,
required files and allowed/forbidden scope. New PAI-00 publications must enter the
manifest; PAI-01 design and B..F source receipts belong to their own cards and
cannot be used to silently hide PAI-00 changes. Rollback is a reviewed path-scoped
revert/forward fix of this list, preserving owner/other-card work, history and pin;
rerun pin/planning/regression and fresh tooling review after any gate change.
No rollback was performed or claimed proven by a future plan.

Human gates are FUTURE decisions, never fields to forge now. The owner records
hash-bound feature approval through the real interactive pinned consumer at
.playbook-artifacts/workflows/PAI/approval.json: human:<identity>, actual date,
current Markdown/registry/input hashes, genuine role refs and ADVISORY
acknowledgement. Self-approval, stale hashes and STOP are rejected. One controlled
PAI-29/owner-acceptance.json operator record maps ALL69 IDs/ten scenarios to
explicit candidate SHA/date, owner reference, actual live/visual/usefulness
observations and immutable evidence hashes; public sanitized plan/reference is
PAI-29-pilot-packet.md. No accepted owner record exists yet. Shared human_gate
strings identify the common full-programme owner decision, not unresolved symbols
or past receipts. Actual human SHA/date are captured when the owner acts, never
invented at design time.

External scope is separate: controlled PAI-27/approved-scope.json records exact
owner/source/account/connection fingerprint, read/model-egress/scheduling/delivery/
write/institution scope, provider, bounds, retention and start/expiry. Durable
CapabilityGrant documents enforce owner/resource/operation/data-class/provider/
purpose/revision/expiry before credentials/transport and final effects. Existing
exact valid grants may be reused; a key is not consent. Writes additionally require
owner-bound expiring one-use exact content/recipient/time/version confirmation.
PAI-28/cutover-approval.json separately binds production target/SHA/operator
window/rollback decision; the synthetic-only target guard remains. Missing/expired
scope never becomes live authority; neither artifact has been accepted here.

Evidence schemas/consumers are concrete in REVIEW_POLICY.md and actual tools.
assistant.opencode_review_attempt.v1 means request attempted, not a verdict.
assistant.opencode_design_review.v1 records actual requested/observed model/effort,
read_only, reviewed_head, original/rendered input/doc hashes, report hash, role/
feature/slice/spec scope, imported pinned gate paths/hashes, actual usage and
tooling_audit_ref. Tooling review_scope=tooling cannot be consumed as feature
review. finalize_opencode_design_reviews.py aggregates ALL4 unchanged native
parts into assistant.opencode_complete_review.v1; only the real pinned generic
writer creates role.review.json with opencode_go[_complete] binding. Identity,
hashes, scope, complete roles and consistent verdict are checked; source/HEAD/doc
drift, altered tooling, partial/STOP evidence invalidate consumption. No Codex
role-run events or human fields are manufactured. Bootstrap/advisory source
reports do not substitute. Native tooling #44 was ADVISORY; a checker change
requires NEW genuine audit before design consumption. Unsupported non-Codex
slice/Test Critic/privacy/maintainability acceptance remains pending until genuine
reviewed integration/receipts; no fixture fills that gap.
