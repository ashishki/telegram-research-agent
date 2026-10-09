# Feature Design — PAI durable Personal Assistant

## Metadata

Feature-ID: PAI
Status: draft
Planning-Depth: designed_slices
Owner: active Codex Direct session
Risk-Level: high
Related-Tasks: PAI-00..31; original requirements PA-00..18
Brief-Ref: docs/PERSONAL_ASSISTANT_BRIEF.md
Architecture-Refs: docs/adr/ADR-013-pa-durable-runtime.md
Created-At: 2026-10-06

## 1. Product Outcome

The remaining queue connects the existing contracts into one durable
Chat/Search/Brief/Watch/Act application, including selected mail/calendar/
academic sources, memory/media, private reading and measured operations.
Local fixtures, provider integration and owner acceptance remain distinct.
No MVP reduction or restarted timers; engineering progress preserves historical
PA registry/approvals.

## 2. Existing System Context

Source baseline 8faee4232cb30e6b6f39cfbd974c151846f79da6. Reuse application,
conversation, capabilities, synthesis, public_web, deep_research, briefs,
watch_jobs, confirmed_actions, mail/schedule/media connectors, memory_library,
model_cost and operations. Existing policy/action receipts are partly in memory;
the watch store has explicit-path SQLite and a tested locked-send contract.
The application has injection seams but does not wire all these contracts into
the default ingress. Deployed state remains unverified.
Design reviewers read full PERSONAL_ASSISTANT_SPEC.md.
The companion registry binds each PAI packet to an executable formal task;
PA-Refs preserve stage coverage; PAI.requirements.json maps all 69 binding spec
IDs and ten verbatim §13.2 scenarios to slices, expected paths, acceptance
commands/test nodes, independent roles and actual human evidence gates.

### Review-tooling maintenance boundary

PAI-00's owner-authorized local maintenance scope is separate from PAI-01
feature authorship: runner/transport/checker/finalizer/strict-acceptance changes
are reviewed in a distinct read-only tooling packet. They cannot validate
themselves. Before any new design request or generic design record is trusted,
require_tooling_audit checks an actual independent PASS/ADVISORY from the current
owner-selected reviewer recorded in REVIEW_POLICY (currently GLM-5.3), complete
critical-source manifest, immutable result/report hashes and unchanged current
code/tests/REVIEW_POLICY. Any such change invalidates that gate; re-audit before
consuming design receipts. Bootstrap diagnostics/historical provisional reports
remain evidence only. No tooling reviewer grants human feature completion.

Current native93: ADVISORY at9098d0c, observed glm-5.3, no P0/P1.
Actual require_tooling_audit checks current critical hashes; exact evidence:
PAI-review-continuation-93.json. Native79 retains historical sources. Requested
max/unknown observed effort and fixtures do not grant human design approval.

## 3. System Impact

Proposed topology: ingress/application -> PostgreSQL inbox/state/jobs ->
scheduler/read-research workers/render process -> effect executor -> receipts.
Private report artifacts reside in explicit private storage, with owner,
object/version/hash and access expiry in PostgreSQL. Retain the SQLite archive;
workers never alter its IDs or mix mailbox data into it. The render process has
no arbitrary network or provider secrets. All interfaces call shared use cases.

### Table ownership and constraints

| Namespace / tables | Authoritative component | Core constraints |
| --- | --- | --- |
| pa_policy grants, revisions, revocations | Policy repository | owner/scope/provider/purpose; monotone revision; UTC validity |
| pa_policy reservations, budget_windows, usage_settlements | Budget repository | unique operation/group; atomic reserve/settle; unknown spend retained |
| pa_conversation inbox, conversations, messages, object_refs | Conversation/intake repository | unique bot/owner/update key; CAS state version; bounded context |
| pa_results results, result_versions, report_artifacts | Result repository | unique object/version; immutable digest; owner and source access |
| pa_actions proposals, confirmations, attempts, receipts | Action/effect repository | exact content/version; one-use confirmation; unique effect key |
| pa_jobs jobs, checkpoints, schedules, occurrences | Job/scheduler repository | fenced writes; unique occurrence; consent revision; explicit cancel |
| pa_connections connections, cursors, source_records | Connector repository | account/provider IDs scoped; tombstones and partial coverage |
| pa_memory facts, preferences, deletion_requests | Memory repository | explicit confirmation/provenance; version CAS; deletion propagation |

Foreign keys are owner/scoped, not bare provider object IDs. Token storage is
outside these tables; ADR-013 binds TokenVault, keys and reconciliation scopes.
Public logs/metrics use opaque IDs, counts and reason codes. Never credentials,
mail text, chat text, report payloads or DSNs. Payload limits and schemas reject
unrecognized fields/versions and nonfinite values, including corrupted storage.

## 4. Program Design

Proposed file areas: src/prm/storage/ for bounded repositories/unit-of-work and
versioned state schema; src/prm/runtime/ for composition, worker, scheduler,
effect executor and connector transports. Existing domain modules remain the
source of business semantics; src/bot/ stays transport. The companion registry
specifies per-card allowed/forbidden files, verification, budgets and rollback.
The existing src/assistant/prm_post_answer_actions.py remains a compatibility
adapter for owner/result/version-bound post-answer callbacks; src/prm owns
policy/proposal/receipt semantics. This reuse boundary delegates to the shared
use cases and cannot create a second action engine or inherit a later topic.
This design packet activates no code/migration. PAI-00 owns reviewer/checker/
finalizer tooling and owner strategy; draft files<=72 covers the named scope in
docs/verification/PAI-00-file-manifest.json. PAI-01 owns design publication, B..F
runtime. Scope/acceptance remain independently reviewed and human-gated.

### Interfaces and invariants

StateUnitOfWork.begin() -> transaction; enqueue(tx, JobIntent) -> JobRef;
claim(queue, worker) -> Lease(job_id, generation, token, until);
checkpoint(lease, expected_version, object_ref) -> applied/unavailable;
heartbeat(lease, expected_generation, token) -> extended/stale;
recover_expired(now_from_db) -> safe_checkpoint_requeued/quarantined/awaiting_reconciliation;
verify_input(owner, object_id, version, digest) -> current/denied;
cancel(owner, job_ref, expected_version) -> pending_stopped/already_started/
completed/failed/cancelled/quarantined/awaiting_reconciliation/unavailable;
authorize_and_reserve(tx, typed_request) -> current scope-bound reservation;
prepare_effect(tx, exact_confirmation, reservation) -> unique AttemptRef;
dispatch(attempt_ref, fake_or_authorized_transport) -> receipt/unknown;
reconcile(attempt_ref, scoped_provider_evidence) -> resolved/unknown.

Job payload v1: job_id/type/schema_version, owner/connection/resource/purpose
refs, input object/version/digest, consent revision, absolute UTC deadline,
step/attempt/time bounds and idempotency key. No embedded AuthorizationDecision,
pickled object, executable callable, provider key or full private source body.
N/N-1 handlers accept only explicitly supported versions; unknown ones quarantine
without a provider call or deserialization execution. Schema migration refuses
a backend/runtime compatibility mismatch before intake.

Jobs: queued -> leased -> running -> result_ready -> completed.
Read-only failures may retry via retry_wait within bounds, else failed.
Cancellation stops unstarted steps and moves safe work to cancelled.
Cancellation reports existing terminal states accurately; an unresolved external
attempt keeps awaiting_reconciliation even when later unstarted work is cancelled.
Missing/currently unavailable state is not described as already-started work.
Durable effects are separate: prepared -> succeeded/known_no_effect/unknown.
Dispatching/dispatch_started is an in-flight transaction marker, not a separately
committed observable state: locks remain held through the bounded call. Crash
or connection loss can therefore leave durable prepared even after a send.
Operator status describes prepared as potentially started/awaiting evidence,
never as known-no-effect. Recovery treats prepared and unknown identically. Lease expiry recovers safe compute checkpoints only. Unknown or any
unresolved prepared effect blocks re-dispatch; it requires reconciliation.
Progress is committed checkpoint metadata, not optimistic model narration.
Heartbeat requires current lease/token/generation and DB validity; it cannot
extend a cancelled/expired job. Recovery requeues only bounded safe compute,
quarantines unsupported schema versions and never reclaims an effect to send.
Checkpoint and final dispatch revalidate input object/version/digest and current
source visibility; stale/missing/deleted inputs fail closed.

DB time governs leases/validity; monotonic time governs local durations.
Claims use ordered short transactions and SKIP LOCKED. Fenced CAS checks token,
generation, lease validity and state; stale workers cannot publish results,
extend a lease or settle a new effect. They cannot be fenced at the provider,
so the separate durable attempt is mandatory.

The [proposed ADR-013](../adr/ADR-013-pa-durable-runtime.md) details the two-phase
prepared-attempt commit, final scope locks through one bounded call, and
pause/revoke ordering. It deliberately retains the current strict semantics.
Do not drop the locked final guard before proving an equivalent sequencer.

Scheduler locks due schedule rows, enqueues a unique owner/schedule/revision/
occurrence job and advances next_due_at in ONE transaction. Quiet hours/DST and
source-deadline recalculation reuse PA-09 domain rules. Catch-up coalesces one
current brief per scope; expired occurrences record skipped reasons, never a
burst of historic messages. Deadline notifications require fresh source checks.
Background collection/delivery grants remain distinct from foreground reads.
Reservation timing and proven-unused release are specified in ADR-013
§Scheduler reservation lifecycle; prepared/unknown spend never refunds from status.

### Synthetic defaults and load profile

Proposed test-only configuration: two read workers, one effect executor, one
scheduler; 30 s job lease/5 s heartbeat; transport timeout 10 s; three bounded
read retries including Retry-After; payload 64 KiB of refs/metadata; checkpoint
bound 16 KiB. Actual provider defaults are pending measurements/configuration.
Final effect locks cover only current scope grant/consent/proposal and the
specific reservation/attempt. Shared request/job/day/month budget-window rows
are locked only during short reserve/settle transactions, never across transport.
Synthetic lock timeout 1 s and statement timeout 2 s apply to those transactions;
transport bound 10 s, final transaction idle bound 15 s and separate effect pool
prevent global starvation. Timeout/disconnect after prepared preserves unknown
and conservative spend; no effect retry. Live bounds require measurements.

Unknown fences block the same effect identity/confirmation and dependent steps
of its job/operation group. Unrelated jobs/scopes continue under their own budgets
and consents. Owner sees awaiting_reconciliation and can cancel unstarted work;
the original attempt/reservation fence survives that cancellation.

Model/provider financial caps inherit current COST_BUDGET until owner decision;
do not substitute these test values for authorization.

Freeze synthetic load: 1 interactive request/s for 60 s, burst 10 then 20,
two schedulers ticking the same 100 schedules, 20 concurrent reservation
requests competing for 10 units, and 50 conflicting confirm/cancel operations.
Require unique intake/occurrence/effect keys, zero unauthorized calls and stale
writes, no lost terminal receipts, bounded queue admission, prompt cancel/status.
Measure p50/p95/p99 intake/queue/runtime/lock wait separately. Proposed intake
p95 <=2 s, Chat <=10 s, Search <=45 s are targets, not observed performance.
Fake transport tests establish mechanics; paid/live latency/cost needs new scope.

### Retention and deletion

Synthetic fixtures only before explicit retention acceptance. Proposed setup
shows conversation 30 days, temp uploads until processing ends with a cleanup
deadline, source-derived facts until revoke/selected expiry and explicit memory
until deletion. No default silently saves live private history. Owner must
select report/source/history/backup windows before live persistence.
Revocation hides related source/results, invalidates jobs/caches/reader links,
and queues derived deletion without deleting independent Telegram archive.
Operational attempts/receipts retain only minimal hashes/status/provider refs
needed to prevent replay; retention exceptions and backup expiry are shown
before acceptance. Restore replays deletion tombstones and preserves unknown
effect fences; cannot revive revoked authority or deleted reader links.

### Test database and cutover

PAI-02 pins driver and test PostgreSQL after checking official docs. A test CLI
requires explicit synthetic target, loopback host, dedicated database/role and
test marker; no production DSN/.env reading or default SQLite fallback. A
non-skipped real PostgreSQL suite covers constraints, rollback, version
compatibility and separate-process races. Isolated test database creation is
already within this assignment; service enablement/production remain separate.

PAI-25 rehearses versioned export/import on synthetic copies with counts,
normalized checksums, exact identity/digests, references and receipt states.
SQLite backup API captures a consistent WAL snapshot. PAI-28 alone can perform
authorized cutover: stop intake/claims, drain or record unknown, freeze writer,
final export/check, switch one writer and retain source read-only.
After new writes rollback requires verified delta transfer or forward fix;
restoring an old snapshot alone could duplicate effects and is forbidden.

### Unknown settlement and cross-store deletion

Unknown spend stays owner-visible and charged conservatively to its original
request/job/day/month window; rollover cannot refund or restart that job.
Provider evidence settles actual usage by CAS, or explicit owner-confirmed
write-off consumes the entire upper reservation once. The operator can inspect
unknown totals, cancel remaining work, or fund a NEW bounded operation ID.
None of these choices retries an unknown external effect or silently increases
a cap. Declining additional budget visibly blocks that work. PAI-03/23/26 test
permanent unknown, window rollover, visible refusal, conservative one-use
settlement and explicitly funded new-operation continuation.

PostgreSQL is the visibility authority across both stores. First commit an
owner/resource/revision deletion tombstone and invalidate jobs/caches/reader
links; every serving path checks current authority and denies unavailable
authority. Then idempotent per-store steps remove selected derived PostgreSQL
rows/artifacts and SQLite derived/index rows under the same deletion ID.
Independent canonical Telegram records are preserved. Each store tracks a
watermark; unreachable cleanup remains pending with bounded retries and an
owner-visible partial_deletion status, never complete. Offline SQLite cleanup
does not permit stale serving. Restore applies authority tombstones before
opening reads, then resumes cleanup. PAI-21/25/26 cover offline-store revoke,
stale cache/job denial, resumed cleanup and both restore directions. Backup/
provider expiry exceptions are shown before acceptance, not called immediate
physical deletion.

## 5. Maintainability Risks

Keep queue implementation narrow and repository transactions explicit.
Do not create a second grant registry, action engine or provider secret path.
Repository contract tests preserve semantics across current and new backend;
shared DTOs do not prove concurrency. Narrow locks cost connections and
pause latency; monitor before considering a sequencer. Optional Redis and
archive migration remain measured conditional cards with new ADRs.

## 6. Verification Strategy

Acceptance argv in PAI.design.json mirrors each card and uses
tools/run_pai_acceptance.py: explicit test paths, strict markers, nonzero
observed cases and failure on skip/xfail/error. PAI-26 additionally requires all
69 named requirement cases and all exact scenario/recovery nodes from the matrix.
Counts/identities prevent omissions; Test Critic and behavioral assertions still
establish usefulness/correctness. Structural checks independently compare full
Markdown/cards/registry/matrix IDs and dependencies; they are subject to the
separate tooling audit above.
New tests/test_pai_* files are planned and MUST be written and registered before code-card completion.
Missing files/skip are failures or unknown evidence, never PASS.
The phase-A checker verifies structure/mapping only, not new product behavior.
focused-prm is the code-phase floor; retrofit-boundaries covers changed runtime/
legacy/deploy. Preserve before/after failures and run exact targeted suites.

Program design review must specifically challenge DB disconnect during send,
prepared-attempt crash, reservation settlement, deletion/backup restore, stale
lease and revocation/send races. Product design review covers all full-spec
outcomes, actual ingress paths, truthful status and private reader UX.
Fixtures, actual renders, provider integration, judge verdicts and human
usefulness remain distinct; final gates are PAI-26..29 / PA-18.

## 7. Vertical Slices

PAI.design.json registers all32 draft packets. A=instructions/design,
B=durable state, C=execution, D=core product, E=sources/actions,
F=completeness/recovery, G=separately scoped real completion. Product cards
must wire real application/ingress/adapters, with only external I/O faked;
infrastructure proves real multiprocess storage/lifecycle. No skeleton closure.

## 8. Open Decisions

Project brief/planning depth are selected. Exact hash-bound feature design,
live account/retention/cost/provider decisions and conditional scaling remain
pending; neither time nor a configured key supplies them.

Requirements-matrix-SHA256: a1f8ed85ff92ce3d7a084b40c232d39ef0352710cc53afbdaca1c4ff2b8f6d7b

## 9. Human Approval

Human-required, hash-bound workflow; no approval fields supplied by the author.
Review the paired Markdown/JSON and ADR-013, complete independent product/program
reviews through an agreed compliant runner, then approve in pinned workflow.
This draft registers scope only; original PA review_required state is preserved.
Formal acceptance/completion depends on that gate. ADR-014/015 and the current
IMPLEMENTATION_CONTRACT separately authorize local PAI-02..26 implementation
with synthetic sources while design reviews/human acceptance remain open;
ADR-015 sequences the completed local pass before tests/reviews. This is explicit
owner sequencing, not invented design acceptance. No live/release authority.


## 10. Concrete evidence bindings

ADR-013 §Concrete evidence bindings retains the full baseline/manifest/test/
human/live record contract. PAI-00 reconciliation_regression explicitly runs
{python} tools/run_pai_acceptance.py -q tests/test_playbook_bridge.py
 tests/test_assistant_conversation.py tests/test_prm_product_ux_eval.py
 tests/test_pai_plan.py tests/test_opencode_role_review.py tests/test_memory_research.py
 tests/test_pai_acceptance_guard.py; all seven exist and are matrix-bound.
This exact argv at88da0f5 refutes the alleged omitted bridge/memory suites;
no changed argv or claimed new run. Formal planned state remains distinct from
local implementation/dated synthetic runtime evidence; see ADR-013 bindings.
