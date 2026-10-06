# PAI-00 reconciliation receipt — 2026-10-06

Engineering status: local_verified; independent phase-A review pending.
Source/verified HEAD: 8faee4232cb30e6b6f39cfbd974c151846f79da6.
Branch: docs/personal-assistant-blueprint-playbook-20260918.
Work is a local uncommitted diff. No independently reviewed commit exists.
Current final file hashes/diff manifest: PAI-working-tree-evidence.json.

## Entry state and preservation

Entry changes were docs/CODEX_PROMPT.md and docs/tasks.md; untracked files were
UTD_intelligence_layer_research_report.md, docs/PA_IMPLEMENTATION_TASKS.md,
docs/PA_SCALING_STRATEGY_2026-10-06.md, docs/prompts/astra6_strategy.md and
docs/prompts/pa_sol_implementation.md. Relevant queue/prompt docs were edited
within assignment; unrelated UTD/Astra and strategy contents are untouched.
No reset, master edit, force push, credential read or production/runtime change.
The entering handoff is preserved in CODEX_PROMPT.before-pai-20261006.md.
Original PA.design.json and original PA task acceptance/dependencies remain
unchanged. The added PAI feature is draft; all formal PAI states stay planned.

## Observed behavior and changes

One current handoff/progress replaces competing PA-09/PA-10/PA-17 instructions.
The September 23 non-Codex amendment governs reviewer choice; the owner retained
Mimo again in the active session. Contract applicability records local scope
separately from exact human/live authority. Skill instructions may be read in
scope; unreviewed executables/private/runtime access gain no authority.

README/architecture distinguish application injection seams, standalone local
contracts and absent current live evidence. Archive and FTS remain canonical;
new PostgreSQL authority/queue is proposed, not implemented. Historical UX
failure is dated evidence rather than a new PA-00 assignment. Old maintenance
prompts remain explicit-use references; orchestrator alias is relative.

32 PAI task blocks and a separate draft registry map every original PA
requirement, preserve engineering dependencies and register exact planned
acceptance tests. The offline checker rejects drift/missing tasks/wrong design
binding and explicitly reports 28 absent future test files. Strict file mode
fails rather than calling those suites implemented. Two pinned draft/validation
tools were exposed through the existing verified bridge; unknown tool/path and
dirty-pin guards are preserved. Verification configuration adds the PAI
structural check; focused-prm now contains conversation and new governance tests.

The Mimo design backend runs via tools/run_codex_role.py run --provider
opencode-go. It prepares bounded packets without keys/API calls, and actual
execution requires the genuine planning binding, explicit egress and one
budgeted call. It checks complete output/observed model, P0/P1 verdicts,
manifest/HEAD drift, and uses real generic pinned design-record writer/parser
with opencode_go binding. It never emits a Codex role-run schema/events or human
approval. Shared transport rejects redirects and oversized responses; output is
actually bounded to 8000 tokens for this route. Unknown cost/effort is explicit.
This code still needs actual independent review before external use; fake
consumer compatibility is not a real Mimo verdict. No-provider run fails closed.
The old workflow review projection would label a default report codex_exec;
the new route therefore retains separate report paths and generic records.

## Current failures and correction

Initial targeted baseline: 1 failed, 50 passed in 7.53 s.
The historical product UX confirmation test passed. The failure was
test_application_plain_yes_does_not_reroute_or_execute_without_pa13_version_loader:
fixed September 19 state expired against the current clock, returning unavailable
instead of the intended missing-version stale_or_unavailable. Control the store
clock in the fixture and add current-preview, expired-confirmation and
expired-conversation cases. Keep the no-search/no-execution denial assertions.

First focused floor: 1 failed, 593 passed in 167.53 s.
test_memory_research_archive_scoped_recent_posts_are_not_current_fact_refusal
used a July fixture and current October relative time; insufficient_evidence was
correct for that time. Reproduced individually: 1 failed in 1.85 s. Supply the
scenario's explicit August 11 clock; retain status/source/refusal assertions.
Existing recent/stale/strict-window tests remain. No production code was changed
to make either fixture pass.

## Exact commands and observed results

| Command | Result |
| --- | --- |
| git status --short; git branch --show-current; git rev-parse HEAD (individually) | Source state above; original files preserved |
| python3 tools/playbook.py --check-pin | Exit 0, immutable pin confirmed |
| python3 tools/check_personal_assistant_plan.py | Exit 0, 19 consistent original PA slices, review_required |
| python3 tools/playbook.py playbook_validate --root . --check tasks --check references (entry) | Exit 1, 19 TASK_DESIGN_APPROVAL_REQUIRED, no structural errors |
| PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_prm_product_ux_eval.py::test_product_ux_keeps_project_context_for_confirmation_followups tests/test_assistant_conversation.py tests/test_assistant_jobs.py tests/test_assistant_actions.py tests/test_assistant_mail.py tests/test_assistant_ops.py | Exit 1, 1 failed/50 passed; diagnosis above |
| PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_playbook_bridge.py tests/test_assistant_conversation.py tests/test_prm_product_ux_eval.py | Exit 0, 39 passed in 20.87 s |
| PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_memory_research.py::TestMemoryResearch::test_memory_research_archive_scoped_recent_posts_are_not_current_fact_refusal | Before second correction: exit 1, 1 failed in 1.85 s |
| PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_memory_research.py tests/test_pai_plan.py tests/test_playbook_bridge.py tests/test_assistant_conversation.py | Exit 0, 62 passed in 5.72 s |
| PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm (baseline recheck) | Exit 0, 594 passed in 157.30 s |
| PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_opencode_role_review.py tests/test_strategy_reviewer.py | Initial adapter: exit 0, 23 passed; later run 23 passed in 15.17 s |
| PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm (adapter registration) | Exit 0, 606 passed in 138.77 s, before final adapter hardening/test additions |
| PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_opencode_role_review.py tests/test_strategy_reviewer.py tests/test_pai_plan.py tests/test_playbook_bridge.py tests/test_assistant_conversation.py tests/test_memory_research.py | Intermediate test import collision: 1 failed/87 passed; explicit local entrypoint import correction: 88 passed in 14.81 s |
| python3 tools/check_pai_plan.py | Exit 0, 32 consistent packets; 28 absent planned test files, no product claim |
| python3 tools/check_pai_plan.py --require-implemented-tests | Exit 1, 28 planned suites absent |
| python3 tools/playbook.py validate_feature_design --root . --design docs/design/PAI.design.json | Exit 0, 0 errors/warnings |
| python3 tools/playbook.py playbook_validate --root . --check tasks --check references (registered) | Exit 1, 51 TASK_DESIGN_APPROVAL_REQUIRED = original 19 + draft PAI 32; no structural/reference errors |
| python3 tools/run_codex_role.py run --provider opencode-go --task PAI-01 --feature-id PAI --role program_design_review --prepare-only | Exit 0, bounded packet/hashes, provider_call false, real needs_input planning gate |
| python3 tools/run_codex_role.py run --task PAI-01 --feature-id PAI --role program_design_review | Exit 2, current policy denies silent Codex fallback |
| git diff --check | Exit 0 |

Final current-scope focused tier: exit 0, 609 passed in 128.75 s. Runtime: Python 3.10.12.
All new acceptance guards are included. Full historical
pytest, paid provider calls and actual integrations were not run. Exact commands
above are separate executions, not authorization to rerun unrelated history.

## Gates, review and next command

Requested reviewer: independent OpenCode Go/mimo-v2.6-pro, owner-reconfirmed.
Observed actual reviewer/model/effort: none; only fake transport telemetry tests.
No independent acceptance or reviewed SHA, no human completion, no live evidence.
Current blocker is PAI-01 genuine project brief/planning decision, bounded review
scope and independent product/program verdicts, then hash-bound design approval.
The owner answered “да, всё разрешаю” to the exact brief SHA and two bounded
Mimo calls. The approved brief decision is recorded in PROJECT_BRIEF.md.
Pinned plan now returns ready; interactive select-plan recorded the assigned
designed_slices with human:owner as the owner alias, entered by the implementer
under that explicit delegation. No unseen feature approval is inferred.

Next safe command:
python3 tools/run_codex_role.py run --provider opencode-go --task PAI-01 --feature-id PAI --role program_design_review --prepare-only

Next workflow command:
python3 tools/playbook.py feature_workflow --root . plan --task PAI-01

Rollback: revert only newly owned instruction/tool/test changes and draft
registration, preserving other authors' documents and all historical receipts.
No data or production migration needs rollback. Commit/push is pending applicable
publication authority/review; nothing unrelated has been staged.

Scoped checkpoint contains 45 changed/new paths, including the owner-provided strategy prerequisite.
Two unrelated untracked documents stay byte-untouched in place and are listed
only in local Git info/exclude (UTD_intelligence_layer_research_report.md and
docs/prompts/astra6_strategy.md), so they are neither committed nor treated as
application/design drift. No tracked modifications are hidden by this exclusion.

Phase-A checkpoint spans instruction reconciliation, baseline fixtures, scoped
runner code/tests and paired design across 46 files (including the hash manifest).
Draft PAI-00 file budget is 48; code-card budgets remain 24. This is a proposed
scope recorded before review/approval, not a retroactive accepted budget.

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
git push origin HEAD exited 0 and updated the assigned branch. Existing user
local documents remain preserved; no production/release action was performed.

## Navigator protocol correction and successful actual smoke

The owner requested inspecting the working Navigator invocation. Source commit
5f26418921246c3e24a967532225dfe3d274b1cb uses system/user, strict json_schema, fresh session UUID and
300 s timeout. Client aligned; 29 targeted tests pass. One tiny synthetic
connectivity probe for that new request succeeded with observed mimo-v2.6-pro
and usage 61+51=112 tokens. It is not a full design verdict or a renewal of the
exhausted two-review-call cap. Full details: PAI-MIMO-CALL-PROTOCOL.md.
