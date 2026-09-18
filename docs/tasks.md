# Active Personal Assistant Task Graph

Status: planned programme; no product implementation started by this documentation change.
Updated: 2026-09-18
Feature: PA • Mode: standard • Planning depth: designed_slices

The full target is `docs/PERSONAL_ASSISTANT_SPEC.md`. Exact slice scope, files, interfaces, dependencies, change budgets and rollback are in `docs/design/PA.design.json`. The design is review_required, not self-approved. Follow `docs/CODEX_PROMPT.md` and `docs/PLAYBOOK_ADOPTION.md`.

Historical PRM-SN/RFX/UTD task records are preserved byte-for-byte at `docs/tasks.before-pa-20260918.md`; their statuses and evidence are not rewritten or imported as new PA completion. Read that snapshot only for a relevant maintenance issue. This graph is the new end-to-end goal, not permission to restart completed work or activate accounts/jobs.

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
  - The diagnosis explicitly classifies evaluator behavior, active dispatch behavior, or both; it records the affected entrypoints, changed-file count, exact interpreter/environment and before/after receipt.
  - The existing durable callback uses additive `prm_post_answer_action_binding.v1`: `context_kind=prm`, context ID, exact canonical SHA-256 source snapshot, optional `{origin: answer.project_name, value}` provenance, offered action codes, private owner chat/actor hashes and expiry. Every Telegram text/voice, compatibility-dispatch and callback ingress either propagates the authenticated `(chat_id, actor_id, owner_chat_id)` unchanged or renders no controls. The shared canonical ID helper accepts only `[1-9][0-9]{0,18}` at most `9223372036854775807`, and controls require three equal canonical positive IDs; no path synthesizes an actor ID.
  - Callback validation is read-only until it has checked parse/action, row, tuple, status/expiry, schema, canonical digest and offered action. Missing/pre-binding/tampered/expired/mismatched rows fail closed without a write, receipt, expiry cleanup or reroute; only a fully valid action enters its distinct mutation phase.
  - `test_post_answer_controls_require_private_owner_actor_binding`, `test_post_answer_context_binds_canonical_snapshot_and_project_ref`, and `test_prm_entrypoints_propagate_private_owner_identity_or_render_no_controls` prove the bound positive path and all entrypoint denials; `test_post_answer_callback_preserves_bound_source_without_reroute`, `test_post_answer_context_rejects_expired_wrong_chat_actor_or_tampered_binding`, `test_invalid_prm_action_context_is_read_only_before_rejection`, and `test_plain_language_action_selection_rejects_stale_or_cross_topic_context` prove preservation and denial.
  - `read_prm_rollback_drain(db_path, *, owner_chat_id, now=None)` validates the owner, opens the proposal table read-only and returns only status, UTC now, blocker count and count-only PRM/legacy-or-unknown/UTD-or-unknown classifications. Bad owner/database/table/JSON/SQL is unavailable and blocks rollback. Its unexpired `ready`/`pending` result blocks rollback to an old PRM handler; it neither deletes nor updates the shared table and cannot modify a UTD row.
  - These named tests are introduced test-first within PA-00 after design approval. Complete natural-language `yes` confirmation belongs to PA-03 and provider-write confirmation to PA-13; PA-00 must deny unsafe legacy text action selection rather than claim either later capability.
  - The direct regression and focused CI are green, or an exact unresolved blocker is reported without weakening the acceptance contract.
Verification:
  - PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_prm_post_answer_actions.py::test_post_answer_controls_require_private_owner_actor_binding tests/test_prm_post_answer_actions.py::test_post_answer_context_binds_canonical_snapshot_and_project_ref tests/test_prm_bot_dispatch.py::test_prm_entrypoints_propagate_private_owner_identity_or_render_no_controls tests/test_prm_bot_dispatch.py::test_post_answer_callback_preserves_bound_source_without_reroute tests/test_prm_post_answer_actions.py::test_post_answer_context_rejects_expired_wrong_chat_actor_or_tampered_binding tests/test_prm_post_answer_actions.py::test_invalid_prm_action_context_is_read_only_before_rejection tests/test_prm_post_answer_actions.py::test_prm_rollback_drain_is_owner_restricted_and_never_mutates_utd_rows tests/test_prm_bot_dispatch.py::test_plain_language_action_selection_rejects_stale_or_cross_topic_context
  - python tools/test_tiers.py focused-prm
Context-Refs:
  - docs/design/PA.md
  - docs/IMPLEMENTATION_CONTRACT.md
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
  - Greeting/editing/general conversation does not fall into archive search; mixed requests use appropriate tools.
  - Shorten/new topic/second item/ambiguous yes/restart cases preserve the intended object. A plain `yes` resolves only one current visible confirmation ref; a new topic, cancellation, expiry, actor/chat mismatch or changed proposal never executes a stale proposal.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
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
  - Representative Russian/English archive questions produce useful source-backed answers with measured retrieval/generation results.
  - No corpus dumps, invented citations or blanket refusal substituted for useful supported partial results.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
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
  - Current-fact, primary-source-only, conflicting, stale and partial-source scenarios return truthful evidence and gaps.
  - Private query leakage, SSRF/redirect/DNS tricks and injected source instructions cannot expand rights.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
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
  - The answer distinguishes facts, inference and project recommendations with actual checked repository identity.
  - Tool/time/cost limits, cancellation and provider failures yield useful partial results rather than runaway loops.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
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
  - Selection, period/timezone, coverage, conflicts, duplicates and version identity are inspectable; no fabricated reading or productivity counts.
  - Explain item two, shorten, filter topics, compare weeks and no-news/partial-week cases work from the actual report object.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
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
  - Facts and citations remain equivalent across formats; long URLs/Cyrillic/dark mode/page breaks do not corrupt the layout.
  - Private views enforce ownership and expiry, sanitize content and do not load tracking resources; sharing has a content/recipient preview.
Verification:
  - python tools/test_tiers.py fast-contract
Context-Refs:
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
  - Pause, unsubscribe, quiet hours, DST, changed deadlines, completion and grant revocation work before collection and final send.
  - Restart/double execution/unknown-send scenarios avoid blind retries, preserve receipts and expose reconciliation needs.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
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
  - Provider, actual token scope versus app filter, paging/sync/freshness, minimal fields and revocation/delete are documented and tested.
  - No account is assumed connected; live proof is separated from synthetic adapter tests; attachments/raw histories are not fetched by default.
Verification:
  - python tools/test_tiers.py fast-contract
Context-Refs:
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
  - Recurrence/DST/multiple-account/ambiguous-contact cases are correct and visible to the operator.
  - Unauthorized calendars/fields stay inaccessible and read capability never grants write permission.
Verification:
  - python tools/test_tiers.py fast-contract
Context-Refs:
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
  - Institutional permission, minimal read scopes and separate consent are established before real Canvas/mail processing.
  - Stage, category, priority, uncertain/conflicting dates, eligibility, local done versus source completion and reminder changes preserve evidence.
Verification:
  - python tools/test_tiers.py fast-contract
Context-Refs:
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
  - Changed text/recipient/time, expired confirmation, another actor, revoked grant and double click cannot reuse old permission.
  - Idempotency and provider-state reconciliation distinguish failed versus unknown outcomes; dangerous out-of-scope actions remain unavailable.
Verification:
  - python tools/test_tiers.py fast-contract
Context-Refs:
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
  - Source, confirmation, time and lifecycle are visible; indexed/opened/read/applied are not conflated.
  - Deletion and permission changes propagate to derived indexes/caches/jobs according to an explicit policy while preserving unrelated archive data.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
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
  - All media respects the same provider/grant policy and supports source/page references and reliable temporary cleanup.
  - Malicious/oversized/unsupported content never executes; OCR is bounded and used only when text extraction is inadequate.
Verification:
  - python tools/test_tiers.py focused-prm
Context-Refs:
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
  - Requested/observed model, tariff version, token classes, latency, retries and total per-success cost are recorded without private text.
  - Unknown pricing and provider failures do not silently broaden permissions or underestimate spend; savings require matched quality evidence.
Verification:
  - python tools/test_tiers.py fast-contract
Context-Refs:
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
  - Every requirement maps to implemented paths, tests, review and user evidence; synthetic passes are not called live proof.
  - All required views/connectors/actions/recovery paths are accepted or explicit external blockers prevent a full-completion claim.
Verification:
  - python tools/playbook.py verify_project --root .
Context-Refs:
  - docs/design/PA.md
  - docs/PERSONAL_ASSISTANT_SPEC.md
  - docs/REVIEW_POLICY.md
Design-Refs:
  - docs/design/PA.design.json
