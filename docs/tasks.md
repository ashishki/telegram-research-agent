# Active Personal Assistant Task Graph

Status: active PA / PAI programme; historical PA engineering evidence is preserved; exact PA and new PAI design approval remain required.
Updated: 2026-10-06
Feature: PA • Mode: standard • Planning depth: designed_slices

The full target is `docs/PERSONAL_ASSISTANT_SPEC.md`. Exact slice scope, files, interfaces, dependencies, change budgets and rollback are in `docs/design/PA.design.json`. The design is review_required, not self-approved. Follow `docs/CODEX_PROMPT.md` and `docs/PLAYBOOK_ADOPTION.md`.

Historical PRM-SN/RFX/UTD task records are preserved byte-for-byte at `docs/tasks.before-pa-20260918.md`; their statuses and evidence are not rewritten or imported as new PA completion. Read that snapshot only for a relevant maintenance issue. This graph is the new end-to-end goal, not permission to restart completed work or activate accounts/jobs.

## Owner-requested execution breakdown — 2026-10-06

[PA implementation tasks](PA_IMPLEMENTATION_TASKS.md) break the remaining work
into 30 mandatory engineering packets (PAI-00..29) and two conditional scaling
packets (PAI-30..31), with dependencies, acceptance commands and rollback.
Use the [Sol launch prompt](prompts/pa_sol_implementation.md) when the owner
assigns implementation. Start at PAI-00 to reconcile actual evidence, then
PAI-01 to bind scope/design through the pinned workflow. PAI IDs are registered below against the new draft PAI feature; their PA-Refs
map requirement coverage without altering original PA task/approval states.
See docs/design/PAI.md and docs/verification/PAI-progress.md. Draft registration
is not design/live/release approval.

## Verification rule

Commands below are the existing regression floor, not sufficient acceptance evidence for a new feature. Before a code slice starts, add its specific executable acceptance and negative tests, list exact test functions/commands in this block, and record an intended failing case where required. Follow the slice registry and spec scenarios. A passing unrelated tier does not complete a slice. Tests and receipts are synthetic/offline unless an explicit, scoped live pilot is approved. Do not run the full historical pytest suite.

Completed/accepted statuses require concrete code, focused tests, applicable model/data evaluations, independent risk review and required human acceptance. P0/P1 safety findings block dependent work. Missing account/institution permission blocks only that live path; implement and verify independent work without claiming the blocked connector works.

### PA-00: Establish and repair the actual baseline
Owner: codex
Phase: foundation
Type: eval:gate
Status: planned
Depends-On: none
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-00
Objective: Reproduce current focused CI, diagnose the confirmation-context failure and correct its actual cause without weakening acceptance.
Acceptance-Criteria:
  - Current HEAD and active entrypoints are recorded; historical runtime observations are not treated as current.
  - The diagnosis explicitly classifies evaluator behavior, active dispatch behavior, or both; it records the affected entrypoints, changed-file count, exact interpreter/environment, then-current HEAD, active bot runtime mode, evaluator synthetic action context IDs and before/after receipt. The historic `cc105…` CI record remains a reference, not runtime proof.
  - The evaluator splits the historical scenario: free-text save/watch from dialogue state is denied as requiring the current inline control and does not fabricate a preview, callback, retrieval call or `eval-*` context; a separate declared immutable bound-inline fixture verifies source-project provenance. The retained historical regression name covers the denied branch; the bound-inline case is separately declared rather than retaining stale dialogue context merely to pass.
  - The existing durable callback uses additive `prm_post_answer_action_binding.v1`: `context_kind=prm`, required `source_result_id` equal byte-for-byte to the lowercase 10-hex row/callback `context_id`, exact canonical SHA-256 source snapshot, optional `{origin: answer.project_name, value}` provenance, offered action codes, private owner chat/actor hashes and expiry. Every Telegram text/voice, compatibility-dispatch and callback ingress either propagates the authenticated `(chat_id, actor_id, owner_chat_id)` unchanged or renders no controls. The shared canonical ID helper accepts only `[1-9][0-9]{0,18}` at most `9223372036854775807`, and controls require three equal canonical positive IDs; no path synthesizes an actor ID.
  - Exact tuple boundaries are `bot.bot.dispatch_command`, `bot.handlers.dispatch_command`, `bot.prm_handlers.dispatch_prm_command`, `_post_answer_action_bundle`, and `handle_prm_post_answer_callback`, each with explicit nullable `actor_id`/`owner_chat_id` input and no-controls default. `run_bot` is the only source of Telegram sender plus configured owner. This rule covers only `prma`/`prmc`; UTD callback prefixes retain their separate contract.
  - One pure snapshot canonicalizer is used at registration and load with the exact PA design keys/bounds/deduplication/absent-value rules. Non-finite/non-serializable source input renders the answer without controls, context or receipt. `validate_prm_post_answer_callback` returns immutable `ValidatedPrmAction` or unavailable after read-only parse/action, row, tuple, status/expiry, schema, digest and offer checks. `apply_validated_prm_action` never reparses: one transaction consumes the result only if context/status/expiry/summary-json/proposals-json fingerprints still match. Missing/pre-binding/tampered/expired/mismatched rows—including malformed callback or row JSON—fail closed without a write, receipt, expiry cleanup or reroute; stale validation also fails without a write.
  - `test_post_answer_controls_require_private_owner_actor_binding`, `test_post_answer_context_binds_canonical_snapshot_and_project_ref`, and the parameterized `test_prm_entrypoints_propagate_private_owner_identity_or_render_no_controls` matrix prove the bound positive path and text/embedded-transcript/completed-voice/compatibility/callback denials for absent/group/malformed/noncanonical/out-of-range IDs; `test_post_answer_callback_preserves_bound_source_without_reroute`, `test_post_answer_context_rejects_expired_wrong_chat_actor_or_tampered_binding`, `test_invalid_prm_action_context_is_read_only_before_rejection`, `test_plain_language_action_selection_rejects_stale_or_cross_topic_context`, and `test_handle_callback_validates_prm_before_acknowledgement` prove preservation, denial and the named `_handle_callback` ordering boundary. Text-action denial does not read `_PRM_DIALOG_STATE` or turn `last_project_name`, `last_topic` or `last_action_context_id` into a callback.
  - The legacy PRM markup path has no authenticated actor/owner tuple and must render no controls. Dynamic `c`, `n1`–`n5`, feedback-reason and confirmation codes require their exact issued server-side transition after a fully valid initial offered action; forged/stale/cross-transition codes make no write. `test_dynamic_post_answer_codes_require_issued_bound_transition` covers every positive and forged dynamic transition.
  - `tests/test_interaction_ledger.py` uses only the same explicit synthetic private tuple (`chat_id == actor_id == owner_chat_id`) as production controls; there is no backdoor fixture interface that accepts controls with chat ID alone.
  - `read_prm_rollback_drain(db_path, *, owner_chat_id, now=None)` validates the owner, derives both current PRM and current UTD owner hashes through their established helpers, opens the proposal table read-only and returns only status, UTC now, blocker count and count-only binding-v1/legacy-PRM-candidate/UTD-profile/UTD-subscription/unknown classifications. It blocks on every unexpired nonterminal row in either namespace. Bad owner/database/table/JSON/SQL is unavailable and blocks rollback. A genuine current-UTD-path row proves the UTD hash is selected as a blocker and the trace proves no non-`SELECT` statement; the report neither deletes nor updates the shared table.
  - UTD is made clean-schema-compatible without a migration: logical `utd_state` is held in `summary_json`, with `draft -> ready`, `previewed|confirming -> pending`, `confirmed -> confirmed`, and `cancelled|expired -> cancelled`. UTD read/write/claim code updates that pair atomically; missing, malformed or mismatched `utd_state`/table-status pairs (including untagged legacy pending) fail closed without a write. Migration/schema files stay forbidden; mapping/rollback tests cover the genuine UTD path.
  - `encode_utd_proposal_state`/`decode_utd_proposal_state` plus guarded `transition_utd_proposal` are the sole state codec. Onboarding, draft load/save/discard, profile preview/confirm/cancel and subscription start/claim/finish/cancel CAS expected logical state, mapped table status and prior JSON fingerprint in one transaction; a production-schema integration test executes every transition and races confirm/cancel so exactly one wins.
  - PRM transport retains the callback facade's single pure validation result before Telegram acknowledgement. Invalid PRM callbacks receive only the generic acknowledgement `Action unavailable`, no follow-up message and no durable write; valid PRM callbacks acknowledge only after validation. UTD acknowledgements remain under their existing contract.
  - These named tests are introduced test-first within PA-00 after design approval. Complete natural-language `yes` confirmation belongs to PA-03 and provider-write confirmation to PA-13; PA-00 must deny unsafe legacy text action selection with a safe re-run instruction rather than claim either later capability.
  - The direct regression and focused CI are green, or an exact unresolved blocker is reported without weakening the acceptance contract.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_prm_product_ux_eval.py tests/test_prm_post_answer_actions.py tests/test_interaction_ledger.py tests/test_utd_profile.py tests/test_prm_utd_callbacks.py tests/test_prm_utd_dispatch.py tests/test_prm_bot_dispatch.py tests/test_callbacks.py::TestIdeaCallbacks::test_run_bot_prm_safe_routes_only_post_answer_callbacks tests/test_callbacks.py::TestIdeaCallbacks::test_handle_callback_validates_prm_before_acknowledgement tests/test_callbacks.py::TestIdeaCallbacks::test_run_bot_prm_safe_dispatches_transcribed_voice_as_auto tests/test_callbacks.py::TestIdeaCallbacks::test_run_bot_prm_safe_dispatches_completed_voice_with_owner_tuple tests/test_callbacks.py::TestIdeaCallbacks::test_run_bot_prm_safe_dispatches_plain_text_as_auto tests/test_callbacks.py::TestIdeaCallbacks::test_run_bot_prm_safe_drops_owner_callback_in_group
  - PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python tools/test_tiers.py focused-prm
  - The PA-00 CAS extension additionally runs `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_prm_post_answer_actions.py::test_validated_prm_action_cas_rejects_stale_row tests/test_utd_profile.py::test_utd_state_transitions_use_guarded_cas_on_canonical_schema`; together with the preceding direct command this is the registry `confirmation_context` set.
Context-Refs:
  - docs/design/PA.md
  - docs/IMPLEMENTATION_CONTRACT.md
  - docs/verification/PA-00-technical-evidence-2026-09-18.md
Design-Refs:
  - docs/design/PA.design.json

### PA-01: Contracts and acceptance foundation
Owner: codex
Phase: foundation
Type: agent:design eval:gate
Status: planned
Depends-On: PA-00
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-01
Objective: Bind the full product outcome to versioned interfaces, independent design review and representative acceptance cases.
Acceptance-Criteria:
  - Conversation, evidence, grant, report and action contracts are specific and preserve existing source identities.
  - Design approval is exact and human-issued; useful positives, failures and adversarial cases exist before capability implementation.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_assistant_contracts.py
  - python tools/test_tiers.py fast-contract
Context-Refs:
  - docs/design/PA.md
  - docs/PERSONAL_ASSISTANT_SPEC.md
Design-Refs:
  - docs/design/PA.design.json

### PA-02: Permissions and tool boundary
Owner: codex
Phase: foundation
Type: tool:policy agent:control
Status: planned
Depends-On: PA-01
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-02
Objective: Enforce account/resource/operation/data/provider grants before calls and before side effects, consistently across text and voice.
Acceptance-Criteria:
  - Revocation, forbidden fallback, changed grant revision and no-consent cases deny the operation without leaking data.
  - Permission UI explains actual scope; a configured key is never interpreted as universal consent.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_assistant_grant_codec.py tests/test_assistant_permissions.py tests/test_assistant_egress.py tests/test_llm_client.py tests/test_openai_provider.py tests/test_voice_transcription.py tests/test_prm_synthesis.py tests/test_prm_utd_dispatch.py
  - python tools/test_tiers.py fast-contract
Context-Refs:
  - docs/design/PA.md
  - docs/PRIVACY_THREAT_MODEL.md
  - docs/ASSISTANT_BOUNDARIES.md
Design-Refs:
  - docs/design/PA.design.json

### PA-03: Natural conversation
Owner: codex
Phase: chat-search
Type: agent:conversation tool:control
Status: planned
Depends-On: PA-02
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-03
Objective: Provide authorized model-backed dialogue with object-aware followups, topic changes and cancellation.
Acceptance-Criteria:
  - Natural report corrections and follow-ups give substantive explanations over the correct object; command matching alone is not conversational acceptance.
  - Greeting/editing/general conversation does not fall into archive search; mixed requests use appropriate tools.
  - Shorten/new topic/second item/ambiguous yes/restart cases preserve the intended object. A plain `yes` resolves only one current visible confirmation ref; a new topic, cancellation, expiry, actor/chat mismatch or changed proposal never executes a stale proposal.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/ASSISTANT_BOUNDARIES.md
Design-Refs:
  - docs/design/PA.design.json

### PA-04: Useful archive AI search
Owner: codex
Phase: chat-search
Type: rag:retrieval rag:generation
Status: planned
Depends-On: PA-03
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-04
Objective: Connect the working archive retriever and authorized synthesis to the actual user-facing path.
Acceptance-Criteria:
  - Topic and time instructions are separated; relevant omissions and noisy inclusions are measured alongside claim support.
  - Representative Russian/English archive questions produce useful source-backed answers with measured retrieval/generation results.
  - No corpus dumps, invented citations or blanket refusal substituted for useful supported partial results.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/IMPLEMENTATION_CONTRACT.md
Design-Refs:
  - docs/design/PA.design.json

### PA-05: Real controlled web search
Owner: codex
Phase: chat-search
Type: tool:search rag:retrieval
Status: planned
Depends-On: PA-02 PA-04
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-05
Objective: Complete the approved public-search/fetch/evidence/answer path without enlarging the old UTD allowlist.
Acceptance-Criteria:
  - Current claims retain primary-source support and material uncertainty in readable partial answers.
  - Current-fact, primary-source-only, conflicting, stale and partial-source scenarios return truthful evidence and gaps.
  - Private query leakage, SSRF/redirect/DNS tricks and injected source instructions cannot expand rights.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/ASSISTANT_BOUNDARIES.md
Design-Refs:
  - docs/design/PA.design.json

### PA-06: Deep and project-aware research
Owner: codex
Phase: chat-search
Type: agent:planning rag:generation tool:search
Status: planned
Depends-On: PA-05
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-06
Objective: Combine permitted archive, web and current GitHub context in a bounded, resumable investigation.
Acceptance-Criteria:
  - Multi-source synthesis explains differences and conditional applicability to actual project context.
  - The answer distinguishes facts, inference and project recommendations with actual checked repository identity.
  - Tool/time/cost limits, cancellation and provider failures yield useful partial results rather than runaway loops.
Verification:
  - python tools/test_tiers.py focused-prm
Scope-Amendment:
  - 2026-09-19 owner authorization: `tools/test_tiers.py` may be changed only
    to register the dedicated PA-06 holdout suite in `focused-prm`; no runtime,
    job, Redis, database, credential or live-provider scope is added.
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/COST_ARCHITECTURE.md
Design-Refs:
  - docs/design/PA.design.json

### PA-07: Weekly and topical briefing
Owner: codex
Phase: brief-watch
Type: rag:generation agent:briefing
Status: planned
Depends-On: PA-06
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-07
Visual-Contract: required
Objective: Produce a source-backed BriefDocument and a concise conversational Telegram view for any requested period/topic.
Acceptance-Criteria:
  - Event-level editorial stories contain takeaways, explanations, selection rationale, optional next steps and source anchors; unknown priority fields never substitute for editorial work. Short/full/follow-up views use the same stored story identities.
  - Selection, period/timezone, coverage, conflicts, duplicates and version identity are inspectable; no fabricated reading or productivity counts.
  - Explain item two, shorten, filter topics, compare weeks and no-news/partial-week cases work from the actual report object.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_assistant_brief_editorial.py tests/test_prm_synthesis.py
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_assistant_briefs.py tests/test_assistant_report_dialogue.py
  - python tools/test_tiers.py focused-prm
Scope-Amendment:
  - 2026-09-19 subsequent owner direction authorizes local product-quality integration through PA-15 and implementation beginning with PA-07; docs/design/PA-PRODUCT-QUALITY.md defines the expanded local scope and batched review. Runtime consent and formal approval remain separate.
  - 2026-09-19 owner authorization: remediate the independent PA-07 P1s with
    owner-scoped bounded immutable BriefDocument history through the existing
    local SQLite schema path, and register the two dedicated PA-07 suites in
    `focused-prm`. Visible-response dialogue state remains ephemeral; durable
    reads require a canonical authenticated private tuple and exact
    brief/version references, with owner-wide bounded retention. This does not
    authorize a production DB migration/access, job, worker, Redis, schedule,
    export, provider/account/credential action, or PA-08/PA-09 implementation.
    This narrow current-task amendment governs those two paths; the
    machine-readable design registry remains mechanically `review_required`
    and is not hand-edited as an approval record.
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/PERSONAL_ASSISTANT_SPEC.md
Design-Refs:
  - docs/design/PA.design.json

### PA-08: Beautiful private report views and exports
Owner: codex
Phase: brief-watch
Type: ui:reports tool:export
Status: planned
Depends-On: PA-07
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-08
Visual-Contract: required
Objective: Render the same report as accessible private mobile HTML, polished PDF and portable Markdown.
Acceptance-Criteria:
  - Information hierarchy and meaningful tables/timelines/charts preserve the editorial story and its caveats; no new factual generation during export.
  - Facts and citations remain equivalent across formats; long URLs/Cyrillic/dark mode/page breaks do not corrupt the layout.
  - Private views enforce ownership and expiry, sanitize content and do not load tracking resources; sharing has a content/recipient preview.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_assistant_report_exports.py tests/test_assistant_report_access.py
  - python tools/test_tiers.py fast-contract
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/PERSONAL_ASSISTANT_SPEC.md
Design-Refs:
  - docs/design/PA.design.json

### PA-09: Durable watches, jobs and reminders
Owner: codex
Phase: brief-watch
Type: agent:runtime tool:delivery
Status: planned
Depends-On: PA-02 PA-07
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-09
Objective: Turn explicitly confirmed watches/reports/reminders into cancellable durable jobs with honest delivery state.
Acceptance-Criteria:
  - Each notification explains a meaningful change and its relevance; repeated reports of one event do not create noisy new alerts.
  - Pause, unsubscribe, quiet hours, DST, changed deadlines, completion and grant revocation work before collection and final send.
  - Restart/double execution/unknown-send scenarios avoid blind retries, preserve receipts and expose reconciliation needs.
Verification:
  - python tools/test_tiers.py focused-prm
Scope-Amendment:
  - 2026-09-20 owner direction for this dependency-ready local slice authorizes
    the narrowly necessary PA-02 transport-purpose registration in
    `src/prm/capabilities.py` and registration of the two PA-09 synthetic
    holdout suites in `tools/test_tiers.py`'s `focused-prm` floor. This permits
    neither a service/timer nor a provider, Telegram-account, delivery,
    migration, deployment or runtime-acceptance action. The canonical design
    registry remains mechanically `review_required`; this is not a human
    approval or a release decision.
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/ASSISTANT_BOUNDARIES.md
Design-Refs:
  - docs/design/PA.design.json

### PA-10: Selected mail connection
Owner: codex
Phase: personal-sources
Type: tool:connector privacy:egress
Status: planned
Depends-On: PA-02 PA-03
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-10
Objective: Read/search selected mail through a verified provider and minimal explicit OAuth/retention policy.
Acceptance-Criteria:
  - Thread summaries explain requested decisions, supported deadlines and optional opportunities rather than dumping mail excerpts.
  - Provider, actual token scope versus app filter, paging/sync/freshness, minimal fields and revocation/delete are documented and tested.
  - No account is assumed connected; live proof is separated from synthetic adapter tests; attachments/raw histories are not fetched by default.
Verification:
  - python tools/test_tiers.py fast-contract
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md
Design-Refs:
  - docs/design/PA.design.json

### PA-11: Calendar and contacts
Owner: codex
Phase: personal-sources
Type: tool:connector privacy:identity
Status: planned
Depends-On: PA-02 PA-03
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-11
Objective: Read calendars, resolve recipients and check availability without conflating accounts, timezones or event versions.
Acceptance-Criteria:
  - Schedule answers explain conflicts, implications and available options with correct local/source times.
  - Recurrence/DST/multiple-account/ambiguous-contact cases are correct and visible to the operator.
  - Unauthorized calendars/fields stay inaccessible and read capability never grants write permission.
Verification:
  - python tools/test_tiers.py fast-contract
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/ASSISTANT_BOUNDARIES.md
Design-Refs:
  - docs/design/PA.design.json

### PA-12: Academic Inbox integration
Owner: codex
Phase: personal-sources
Type: tool:connector agent:academic
Status: planned
Depends-On: PA-09 PA-10 PA-11
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-12
Objective: Integrate the existing academic handoff as a module of the same assistant, not a new bot or broad crawler.
Acceptance-Criteria:
  - Academic briefs distinguish obligations, opportunities and reading, with explained eligibility uncertainty and conflicting deadlines.
  - Institutional permission, minimal read scopes and separate consent are established before real Canvas/mail processing.
  - Stage, category, priority, uncertain/conflicting dates, eligibility, local done versus source completion and reminder changes preserve evidence.
Verification:
  - python tools/test_tiers.py fast-contract
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md
Design-Refs:
  - docs/design/PA.design.json

### PA-13: Confirmed external actions
Owner: codex
Phase: action-memory
Type: tool:write agent:control
Status: planned
Depends-On: PA-09 PA-10 PA-11
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-13
Objective: Execute exact mail/calendar proposals after one-use version-bound confirmation and return truthful receipts.
Acceptance-Criteria:
  - A finding can become a concrete editable proposal with source rationale, exact confirmation and an honest execution result.
  - Changed text/recipient/time, expired confirmation, another actor, revoked grant and double click cannot reuse old permission.
  - Idempotency and provider-state reconciliation distinguish failed versus unknown outcomes; dangerous out-of-scope actions remain unavailable.
Verification:
  - python tools/test_tiers.py fast-contract
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/ASSISTANT_BOUNDARIES.md
Design-Refs:
  - docs/design/PA.design.json

### PA-14: Inspectable memory and knowledge library
Owner: codex
Phase: action-memory
Type: rag:memory privacy:retention
Status: planned
Depends-On: PA-03 PA-07 PA-10
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-14
Objective: Let the operator inspect/correct/forget/export memory and reuse reports/materials without hidden profile learning.
Acceptance-Criteria:
  - Explicit interests, projects and length/depth preferences improve future selection; feedback and saved preference changes remain inspectable and reversible.
  - Source, confirmation, time and lifecycle are visible; indexed/opened/read/applied are not conflated.
  - Deletion and permission changes propagate to derived indexes/caches/jobs according to an explicit policy while preserving unrelated archive data.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/ASSISTANT_BOUNDARIES.md
Design-Refs:
  - docs/design/PA.design.json

### PA-15: Voice, images and documents
Owner: codex
Phase: action-memory
Type: tool:media privacy:egress
Status: planned
Depends-On: PA-02 PA-03 PA-14
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-15
Objective: Integrate editable transcription, optional spoken response and safe image/PDF/document questions into the same conversation.
Acceptance-Criteria:
  - Voice, image and document follow-ups preserve report identity and readable explanations with source/page references.
  - All media respects the same provider/grant policy and supports source/page references and reliable temporary cleanup.
  - Malicious/oversized/unsupported content never executes; OCR is bounded and used only when text extraction is inadequate.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/ASSISTANT_BOUNDARIES.md
Design-Refs:
  - docs/design/PA.design.json

### PA-16: Measured model and cost architecture
Owner: codex
Phase: reliability-acceptance
Type: agent:routing eval:cost
Status: planned
Depends-On: PA-06 PA-08 PA-13 PA-15
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-16
Objective: Compare quality-first model routes, privacy-compatible fallback and caching on complete successful tasks.
Acceptance-Criteria:
  - Quality comparisons include editorial and multi-turn usefulness before model cost optimization.
  - Requested/observed model, tariff version, token classes, latency, retries and total per-success cost are recorded without private text.
  - Unknown pricing and provider failures do not silently broaden permissions or underestimate spend; savings require matched quality evidence.
Verification:
  - python tools/test_tiers.py fast-contract
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/COST_ARCHITECTURE.md
Design-Refs:
  - docs/design/PA.design.json

### PA-17: Operations, recovery and security
Owner: codex
Phase: reliability-acceptance
Type: agent:runtime privacy:recovery
Status: planned
Depends-On: PA-09 PA-12 PA-13 PA-14 PA-15 PA-16
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-17
Objective: Make jobs, storage and connectors observable and recoverable through tested deployment/backup/rollback procedures.
Acceptance-Criteria:
  - Worker restart, 429/outage, disk failure, revoked token and duplicate execution have tested honest outcomes.
  - Migration/restore rehearsals use copies, secrets remain private and production deployment requires a specific approval.
Verification:
  - python tools/test_tiers.py focused-prm
  - python tools/test_tiers.py retrofit-boundaries
Context-Refs:
  - docs/design/PA.md
  - docs/ASSISTANT_BOUNDARIES.md
Design-Refs:
  - docs/design/PA.design.json

### PA-18: Full product acceptance
Owner: codex
Phase: reliability-acceptance
Type: eval:gate agent:release
Status: planned
Depends-On: PA-08 PA-12 PA-13 PA-14 PA-15 PA-16 PA-17
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PA-18
Visual-Contract: required
Objective: Accept the complete Chat/Search/Brief/Watch/Act product using exact-HEAD checks, visual review and authorized real use.
Acceptance-Criteria:
  - Owner-calibrated held-out content and multi-turn scenarios gate acceptance separately from schema, provider and mobile evidence.
  - Every requirement maps to implemented paths, tests, review and user evidence; synthetic passes are not called live proof.
  - All required views/connectors/actions/recovery paths are accepted or explicit external blockers prevent a full-completion claim.
Verification:
  - python tools/playbook.py verify_project --root .
Context-Refs:
  - docs/design/PA-PRODUCT-QUALITY.md
  - docs/design/PA.md
  - docs/PERSONAL_ASSISTANT_SPEC.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PA.design.json

## PAI execution tasks — draft scope registration 2026-10-06

These formal tasks map the engineering task pack to feature PAI. The original
PA feature and all historic states/receipts above are unchanged. All formal
PAI states remain planned until the workflow records legitimate acceptance.
PAI-30/31 are conditional, never executed without their measured triggers.

### PAI-00: Убрать противоречия из инструкций и зафиксировать старт
Owner: codex
Phase: pai-a
Type: eval:gate
Status: planned
Depends-On: none
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-00
Objective: следующий исполнитель однозначно понимает, что уже написано, что подключено и что ему разрешено.
Acceptance-Criteria:
  - одна текущая задача/граница, нет ложного «PA-00 снова сломан»; формальные approval ошибки объяснены, но не подавлены. Исторические статусы сохранены. Есть соответствие всех PAI-карточек PA-требованиям.
  - Structural preparation is not independent design review or human approval.
Verification:
  - python3 tools/check_pai_plan.py
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_playbook_bridge.py tests/test_assistant_conversation.py tests/test_prm_product_ux_eval.py tests/test_pai_plan.py tests/test_opencode_role_review.py tests/test_memory_research.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-00
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-01: Принять исполнимый дизайн хранения и фоновой работы
Owner: codex
Phase: pai-a
Type: agent:design
Status: planned
Depends-On: PAI-00
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-01
Objective: конкретный согласованный проект, по которому можно писать код.
Acceptance-Criteria:
  - scope и новые acceptance suites оформлены через pinned workflow; обязательный независимый design review выполнен разрешённым способом; нужное hash-bound human approval получено реально. Если approval отсутствует, design пакет завершён, gate отмечен; изменять его вручную нельзя.
  - Structural preparation is not independent design review or human approval.
Verification:
  - python3 tools/check_pai_plan.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-01
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-02: Подготовить PostgreSQL для локальной разработки и тестов
Owner: codex
Phase: pai-b
Type: agent:runtime
Status: planned
Depends-On: PAI-01
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-02
Objective: тестовый runtime с явным выбором backend и воспроизводимой схемой.
Acceptance-Criteria:
  - чистая test DB создаётся и восстанавливается; migration повторяемо отказывает на неправильном target/version; real PostgreSQL tests идут на synthetic data, а не заменены SQLite mocks. Прежний архив читается.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_storage.py tests/test_assistant_contracts.py tests/test_archive_search.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-02
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-03: Сделать разрешения и бюджеты общими для всех процессов
Owner: codex
Phase: pai-b
Type: agent:runtime
Status: planned
Depends-On: PAI-02
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-03
Objective: два workers видят один отзыв разрешения и не тратят один бюджет дважды.
Acceptance-Criteria:
  - multiprocess race допускает ровно доступный лимит; revoke/revision между enqueue и transport запрещает вызов; restart не сбрасывает расход; request/context pair потребляется корректно.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_durable_policy.py tests/test_assistant_permissions.py tests/test_assistant_egress.py tests/test_assistant_grant_codec.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-03
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-04: Сохранять подтверждения, попытки и квитанции действий
Owner: codex
Phase: pai-b
Type: agent:runtime
Status: planned
Depends-On: PAI-03
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-04
Objective: повторное нажатие или рестарт не повторяет внешнее действие.
Acceptance-Criteria:
  - гонка двух процессов, double click, restart после effect до receipt, stale proposal, foreign owner и revoke покрыты; ни один неизвестный исход не становится автоматическим retry.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_durable_actions.py tests/test_assistant_actions.py tests/test_prm_post_answer_actions.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-04
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-05: Сохранять беседу и точные версии результатов
Owner: codex
Phase: pai-b
Type: agent:runtime
Status: planned
Depends-On: PAI-03 PAI-04
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-05
Objective: после перезапуска «объясни второй пункт» относится к правильному отчёту, а «да» — только к одному текущему предложению.
Acceptance-Criteria:
  - restart, новая тема, отмена, старый callback, две pending proposals и expiry дают правильный результат; retained history удаляется по выбранной политике; беседа другого owner недоступна.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_durable_conversation.py tests/test_assistant_conversation.py tests/test_assistant_report_dialogue.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-05
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-06: Реализовать очередь и worker, переживающие падение
Owner: codex
Phase: pai-b
Type: agent:runtime
Status: planned
Depends-On: PAI-03 PAI-04 PAI-05
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-06
Objective: задача выполняется отдельным процессом и возобновляется с безопасного checkpoint.
Acceptance-Criteria:
  - реальные два test processes не берут один claim; старое поколение не записывает результат; killed worker восстанавливает compute, но не пересылает unknown action; limits/backpressure работают.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_workers.py tests/test_assistant_jobs.py tests/test_assistant_research.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-06
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-07: Освободить Telegram polling от долгих задач
Owner: codex
Phase: pai-c
Type: agent:runtime
Status: planned
Depends-On: PAI-05 PAI-06
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-07
Objective: бот принимает новый запрос и отмену, пока готовится предыдущий.
Acceptance-Criteria:
  - через настоящий ingress fake long job не блокирует другой запрос; duplicate update не создаёт вторую job; restart сохраняет status; cancel прекращает будущие steps. Не писать «в фоне», если enqueue не состоялся.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_ingress_jobs.py tests/test_prm_bot_dispatch.py tests/test_callbacks.py tests/test_prm_cli.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-07
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-08: Подключить планировщик и жизненный цикл Watch
Owner: codex
Phase: pai-c
Type: agent:runtime
Status: planned
Depends-On: PAI-06 PAI-07
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-08
Objective: подтверждённая подписка действительно создаёт задания по времени и восстанавливается без лавины старых уведомлений.
Acceptance-Criteria:
  - два scheduler, повтор tick, downtime, DST, изменение срока, revoke и paused scope проходят; UI различает сохранённое намерение и реально работающий scheduler. Никакой systemd timer не включён этим тестом.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_scheduler.py tests/test_assistant_jobs.py tests/test_assistant_subscriptions.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-08
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-09: Сделать общий executor доставки и сверки исходов
Owner: codex
Phase: pai-c
Type: agent:runtime
Status: planned
Depends-On: PAI-04 PAI-07 PAI-08
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-09
Objective: ответ, Watch и действие проходят один контракт последнего разрешения и правдиво показывают исход.
Acceptance-Criteria:
  - fake server принял effect, но ACK потерян — повтор не происходит; pause/revoke race и старый lease не обходят guard; unknown без возможности проверки остаётся unknown. Реальных отправок ещё нет.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_delivery.py tests/test_assistant_jobs.py tests/test_assistant_actions.py tests/test_assistant_egress.py
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_delivery.py::test_postgres_authority_spans_legacy_sqlite_send
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-09
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-10: Подключить нормальный AI Chat к рабочему приложению
Owner: codex
Phase: pai-d
Type: agent:runtime
Status: planned
Depends-On: PAI-03 PAI-05 PAI-07 PAI-09
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-10
Objective: приветствие, объяснение и редактирование текста проходят реальный model route и возвращаются в ту же беседу.
Acceptance-Criteria:
  - 10–20 последовательных ходов, смена темы, «коротко» и неоднозначное «да» ведут себя правильно; отсутствие grants не делает HTTP вызов. Наличие fake client только в unit test недостаточно для wiring.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_chat_runtime.py tests/test_assistant_conversation.py tests/test_prm_application.py tests/test_openai_provider.py tests/test_llm_client.py
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_chat_runtime.py::test_chat_fallback_provider_without_data_class_grant_is_not_called
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-10
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-11: Довести архивный AI Search до полезного ответа
Owner: codex
Phase: pai-d
Type: agent:runtime
Status: planned
Depends-On: PAI-10
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-11
Objective: запрос на русском/английском находит нужные материалы и даёт синтез с проверяемыми основаниями.
Acceptance-Criteria:
  - end-to-end positive/empty/conflict/revoked cases проходят; bounded excerpts действительно совпадают с разрешёнными источниками; улучшения recall не скрывают ухудшение factual support.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_archive_search.py tests/test_archive_search.py tests/test_prm_synthesis.py tests/test_prm_intent_archive_contract.py
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_archive_search.py::test_retrieved_archive_injection_cannot_create_authority_or_effects
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-11
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-12: Подключить внешний поиск и контекст GitHub
Owner: codex
Phase: pai-d
Type: agent:runtime
Status: planned
Depends-On: PAI-10 PAI-11
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-12
Objective: приложение умеет проверить свежий факт и сравнить его с материалами владельца/выбранным ref репозитория.
Acceptance-Criteria:
  - через fake HTTP проверены snippets-vs-read-doc distinction, timestamps, partial/conflicting sources, SSRF, redirect/DNS смена, malicious content; GitHub answer называет действительно прочитанный ref.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_web_github.py tests/test_assistant_web_search.py tests/test_assistant_research.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-12
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-13: Сделать глубокое исследование отменяемой durable задачей
Owner: codex
Phase: pai-d
Type: agent:runtime
Status: planned
Depends-On: PAI-06 PAI-11 PAI-12
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-13
Objective: большой вопрос переживает рестарт, показывает прогресс и заканчивается синтезом, а не списком ссылок.
Acceptance-Criteria:
  - kill/resume в каждом phase, отмена, потеря провайдера, исчерпание steps/time/cost и новый вопрос в той же беседе корректны; выводы о проекте опираются на актуальный ref, а не общий фон модели.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_deep_research.py tests/test_assistant_research.py tests/test_prm_research_planner.py
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/run_pai_acceptance.py -q tests/test_pai_deep_research.py::test_research_tool_result_injection_cannot_create_authority_or_effects
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-13
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-14: Собрать полезный недельный Brief и его продолжения
Owner: codex
Phase: pai-d
Type: agent:runtime
Status: planned
Depends-On: PAI-05 PAI-08 PAI-09 PAI-11 PAI-13
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-14
Objective: «что важного за неделю» даёт редакционный обзор событий, который можно обсудить и обновить.
Acceptance-Criteria:
  - quiet/partial week, дубли, противоречия, delayed source, DST и followups проходят; смена представления не перегенерирует факты. Fixture quality не выдаётся за human/live quality.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_brief_runtime.py tests/test_assistant_briefs.py tests/test_assistant_brief_editorial.py tests/test_assistant_report_dialogue.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-14
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-15: Сделать приватное чтение и качественный экспорт отчётов
Owner: codex
Phase: pai-d
Type: agent:runtime
Status: planned
Depends-On: PAI-07 PAI-14
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-15
Objective: один отчёт читается с телефона в Telegram и приватном reader, экспортируется в HTML/PDF/Markdown с одинаковыми фактами.
Acceptance-Criteria:
  - чужой/отозванный/истёкший доступ не читает artifact; Telegram/HTML/PDF показывают те же story/source IDs, ничего не обрезано. Человеческая визуальная приёмка остаётся в PAI-27/29.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_report_runtime.py tests/test_assistant_report_exports.py tests/test_assistant_report_access.py tests/test_pdf_inspection.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-15
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-16: Сделать безопасный жизненный цикл подключения аккаунта
Owner: codex
Phase: pai-e
Type: agent:runtime
Status: planned
Depends-On: PAI-03 PAI-07
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-16
Objective: пользователь видит scope подключения, может подтвердить его, проверить состояние, отозвать и удалить производные данные.
Acceptance-Criteria:
  - foreign owner/state, redirect substitution, expired refresh, revoke во время job и restart корректны; UI не называет configured account подключённым без успешного handshake. Здесь handshake только synthetic.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_connections.py tests/test_assistant_mail.py tests/test_assistant_calendar.py tests/test_assistant_egress.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-16
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-17: Подключить выбранную почту Microsoft Graph
Owner: codex
Phase: pai-e
Type: agent:runtime
Status: planned
Depends-On: PAI-10 PAI-14 PAI-16
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-17
Objective: «что требует ответа в почте» и раздел Brief используют выбранную почту с понятными ссылками, сроками и ограничениями покрытия.
Acceptance-Criteria:
  - настоящий adapter с fake HTTP проходит multi-page, deadline conflict, missing data и revoke/delete; беседа даёт сводку, а не дамп заголовков и не выдуманные действия. Sync cursor продвигается только после durable обработки страницы.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_graph_mail.py tests/test_assistant_mail.py tests/test_pai_brief_runtime.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-17
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-18: Подключить календарь и контакты
Owner: codex
Phase: pai-e
Type: agent:runtime
Status: planned
Depends-On: PAI-10 PAI-16
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-18
Objective: ассистент показывает конфликты расписания и находит адресата, не путая аккаунты, зоны времени и совпадающие имена.
Acceptance-Criteria:
  - DST, all-day, recurring exception, несколько аккаунтов, неоднозначный recipient и revoked calendar видны пользователю; read grant не выполняет write, email по имени не угадывается.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_schedule_runtime.py tests/test_assistant_calendar.py tests/test_assistant_contacts.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-18
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-19: Объединить Academic Inbox и минимальный Canvas adapter
Owner: codex
Phase: pai-e
Type: agent:runtime
Status: planned
Depends-On: PAI-08 PAI-14 PAI-17 PAI-18
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-19
Objective: академическая сводка различает обязательства, возможности и чтение; напоминания опираются на актуальный подтверждённый срок.
Acceptance-Criteria:
  - письмо и Canvas с разными сроками дают видимый конфликт; изменённый срок пересчитывает jobs; локальное «готово» не становится source submission; повтор кандидата не создаёт второе обязательство.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_academic_runtime.py tests/test_assistant_academic.py tests/test_assistant_subscriptions.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-19
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-20: Довести подтверждённые mail/calendar действия до адаптеров
Owner: codex
Phase: pai-e
Type: agent:runtime
Status: planned
Depends-On: PAI-04 PAI-09 PAI-17 PAI-18
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-20
Objective: находка превращается в редактируемое предложение, точное подтверждение и проверяемую квитанцию выполнения.
Acceptance-Criteria:
  - настоящий путь preview→edit→confirm→fake provider→receipt проходит; content/recipient/time change, two clicks, kill/ACK loss, version conflict и revoke не дают неожиданную запись. Payments/submission/registration остаются вне tools.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_action_runtime.py tests/test_assistant_actions.py tests/test_pai_delivery.py tests/test_prm_post_answer_actions.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-20
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-21: Подключить память, исправление и сквозное удаление
Owner: codex
Phase: pai-f
Type: agent:runtime
Status: planned
Depends-On: PAI-05 PAI-14 PAI-17
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-21
Objective: владелец видит, что сохранено, может исправить/забыть/экспортировать; удалённое не возвращается из кэша или отложенной job.
Acceptance-Criteria:
  - inspect→edit→forget→restart→search и concurrent running job не воскрешают данные; независимый архив не удалён; opened/read/applied не выводятся из факта индексации. Restore/delete ограничения объяснены честно.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_memory_runtime.py tests/test_assistant_memory.py tests/test_assistant_report_dialogue.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-21
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-22: Подключить голос, изображения и документы к той же беседе
Owner: codex
Phase: pai-f
Type: agent:runtime
Status: planned
Depends-On: PAI-10 PAI-15 PAI-21
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-22
Objective: voice/image/PDF input продолжает правильный разговор, показывает редактируемую расшифровку и source/page references.
Acceptance-Criteria:
  - исправленная транскрипция не наследует старую confirmation; page citations сохраняются; malicious/oversized file не исполняется; неразрешённый fallback provider не получает документ.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_media_runtime.py tests/test_assistant_media.py tests/test_voice_transcription.py tests/test_pdf_inspection.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-22
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-23: Измерять качество, стоимость и полезный эффект кэша
Owner: codex
Phase: pai-f
Type: agent:runtime
Status: planned
Depends-On: PAI-03 PAI-13 PAI-15 PAI-20 PAI-22
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-23
Objective: видны стоимость целой задачи, задержка, маршрут модели и ограничения; оптимизация не ухудшает согласованное качество.
Acceptance-Criteria:
  - synthetic usage доказывает отсутствие двойного счёта; unknown price не ноль; limits общие; cache не раскрывает отозванный результат. Экономия не заявляется до сопоставимого quality evidence.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_cost_cache.py tests/test_assistant_cost.py tests/test_pai_durable_policy.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-23
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-24: Сделать наблюдаемость, восстановление и пакет запуска
Owner: codex
Phase: pai-f
Type: agent:runtime
Status: planned
Depends-On: PAI-09 PAI-16 PAI-21 PAI-22 PAI-23
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-24
Objective: оператор понимает состояние системы и может восстановить её по проверенному runbook.
Acceptance-Criteria:
  - реальный synthetic backup восстанавливается, unknown effects не повторяются; DB loss, disk full, 429, revoked token и logs с secret-shaped fixture values проверены; измерены rehearsal RPO/RTO.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_operations_runtime.py tests/test_assistant_ops.py tests/test_delivery_health.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-24
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-25: Прорепетировать перенос состояния и откат без потери квитанций
Owner: codex
Phase: pai-f
Type: agent:runtime
Status: planned
Depends-On: PAI-02 PAI-04 PAI-05 PAI-08 PAI-21 PAI-24
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-25
Objective: готов конкретный cutover plan для выбранных PA-таблиц, который воспроизведён на копиях synthetic data.
Acceptance-Criteria:
  - rehearsal before/after/rollback совпадает по IDs/digests, grants/tombstones/receipts; повреждённая запись блокирует переключение; искусственный crash в каждом шаге не создаёт второго writer или отправки.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_migration.py tests/test_pai_storage.py tests/test_pai_durable_actions.py tests/test_prm_post_answer_actions.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-25
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-26: Проверить полный продукт без живых аккаунтов
Owner: codex
Phase: pai-f
Type: eval:gate
Status: planned
Depends-On: PAI-15 PAI-19 PAI-20 PAI-22 PAI-23 PAI-24 PAI-25
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-26
Objective: один release candidate с полной requirement-to-evidence матрицей и конкретным списком оставшихся live-gates.
Acceptance-Criteria:
  - Every SC13.2-01..10 scenario and all 69 spec IDs in docs/design/PAI.requirements.json have actual wired test/review evidence; absent/planned nodes cannot pass.
  - каждая обязательная PA-возможность имеет wired positive и failure evidence, нет открытых P0/P1; отсутствие provider/human proof указано отдельно. Generic tier и judge не заменяют эту матрицу.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_end_to_end.py tests/test_pai_load_recovery.py
  - python3 tools/test_tiers.py focused-prm
  - python3 tools/test_tiers.py retrofit-boundaries
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-26
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-27: Проверить реальные подключения в ограниченном canary
Owner: codex
Phase: pai-g
Type: eval:gate
Status: planned
Depends-On: PAI-26
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-27
Objective: реальные integrations подтверждены наблюдениями, а не mocks.
Acceptance-Criteria:
  - для каждого выбранного обязательного подключения записаны точные scope/time/version, observed outcome и ограничения; приватные receipts в защищённом хранилище, в Git только sanitized metadata. Отсутствующий Canvas или model grant имеет свой blocker и не тормозит независимые проверки.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - python3 tools/check_pai_plan.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-27
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-28: Выполнить согласованный production cutover и deployment
Owner: codex
Phase: pai-g
Type: eval:gate
Status: planned
Depends-On: PAI-25 PAI-27
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-28
Objective: нужный SHA работает в назначенной среде с проверенной БД, worker, scheduler и управляемыми capabilities.
Acceptance-Criteria:
  - deployment/migration receipts и наблюдаемый SHA совпадают; нет второго polling/executor, выполнены restore/rollback prerequisites; ошибки переключают систему в заранее согласованный безопасный режим.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - python3 tools/check_pai_plan.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-28
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-29: Пройти пользовательский пилот и закрыть полную PA-18 приёмку
Owner: codex
Phase: pai-g
Type: eval:gate
Status: planned
Depends-On: PAI-28
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-29
Objective: владелец принимает полный персональный ассистент по своим задачам, качеству ответов и эксплуатации.
Acceptance-Criteria:
  - финальная requirement matrix полна, exact-HEAD checks и обязательные reviews пройдены, человек явно принял продукт через workflow. Неподключённый обязательный источник/формат/действие оставляет незавершённость; не переименовывать результат в MVP или full done с исключением по умолчанию.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - python3 tools/check_pai_plan.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-29
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-30: Добавить Redis, только если он устраняет измеренный предел
Owner: codex
Phase: pai-conditional
Type: eval:gate
Status: planned
Depends-On: PAI-23 PAI-24 PAI-26
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-30
Objective: Measured conditional outcome: Добавить Redis, только если он устраняет измеренный предел
Acceptance-Criteria:
  - cache/broker outage, redelivery и stale state не обходят policy; paired load доказывает пользу с учётом новой операционной цены. Production включение отдельно разрешается; обновить PAI-26…29 evidence.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_redis.py tests/test_pai_cost_cache.py tests/test_pai_delivery.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-30
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json

### PAI-31: Перенести архив/FTS в PostgreSQL, если SQLite стал ограничением
Owner: codex
Phase: pai-conditional
Type: eval:gate
Status: planned
Depends-On: PAI-11 PAI-25 PAI-26
Risk-Level: high
Critic-Required: required
Runtime-Verification: required
Correction-Budget: 2
Planning-Depth: designed_slices
Slice-ID: PAI-31
Objective: Measured conditional outcome: Перенести архив/FTS в PostgreSQL, если SQLite стал ограничением
Acceptance-Criteria:
  - data parity и agreed retrieval/SLO выполнены; проверены backup/restore/rollback. Реальный перенос только по отдельному migration разрешению с повтором затронутой приёмки PAI-26…29.
  - The exact card scenarios in the Context-Ref must pass; missing tests, skipped PostgreSQL, fixtures or absent live authority never count as full acceptance.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_pai_archive_migration.py tests/test_archive_search.py tests/test_archive_documents.py tests/test_pai_migration.py
Context-Refs:
  - docs/PA_IMPLEMENTATION_TASKS.md#pai-31
  - docs/design/PAI.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PAI.design.json
