# PA — Personal Assistant Programme Design

Status: review_required. Planning depth: designed_slices. Risk: high.
The owner requested this design and its publication; exact hash-bound human
approval has not been recorded. Never manufacture that approval.

## Architecture contract

Use a modular monolith and durable worker: no second bot, duplicate source DB or
platform migration. Flow is message ->
ConversationState -> bounded plan -> permission check -> typed evidence/object
result -> answer/ActionProposal -> verification/receipt; checks run before data
egress and again before external write/send, and the model never grants itself
authority. Versioned types cover state/grants/evidence, immutable briefs,
academic lifecycle, one-use proposal/receipt and watched work. Preserve account
identity and revocable bounded derived data.

### Confirmation-context invariant

An action preview and its confirmation bind to an immutable source result and
version, action code, chat/owner, expiry, and optional source-project reference.
They never obtain authority or project meaning from `last_project_name`,
`last_topic`, or a freshly routed query. A plain-language “yes” is accepted
only while exactly one matching preview remains current in that conversation;
an explicit new topic, expiry, chat/actor mismatch, changed proposal, or missing
source makes it ambiguous and it must fail closed or ask the operator to choose.
An old inline callback may show a new preview only from its server-bound source
context; it does not rerun search or route a later answer. The source project
label may be displayed when present, but it must come from that immutable
source, not from mutable dialogue state.

PA-00 makes the existing durable Telegram callback path safe without pretending
that it already implements full natural-language confirmation. Its additive
`summary_json` binding is `prm_post_answer_action_binding.v1` and contains:

- `context_kind="prm"` and required `source_result_id`, the exact lowercase
  10-hex `context_id` table key for this answer. Callback ID, row key and
  binding field must be byte-for-byte equal; there is no second result ID;
- `source_snapshot` with exactly `title`, `query`, `body`, `source_refs`,
  `evidence_items`, `project_name`, `primary_intent`, `response_contract_id`,
  `direct_count`, `partial_count`, and `offered_action_codes`. Counts are
  non-boolean integers `0..1000000`; text is
  whitespace-normalized and bounded (240, 220, 240, 240, 64, 64 respectively);
  refs are first-seen exact HTTPS strings <=512 chars (max 5), evidence is
  first-seen `(HTTPS <=512-char URL, normalized <=400-char snippet)` pairs
  (max 5), and offered
  recognized codes are first-seen (max 20). Missing scalar/list values become
  `""`/`[]`/`0`; unknown keys are excluded; booleans, non-integral/non-finite
  numbers or non-serializable values reject controls. V1 has no date field;
  source URL/value text is not otherwise normalized; and
- `source_result_version`, SHA-256 of the UTF-8 encoding of that snapshot with
  `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"),
  allow_nan=False)`. Lists retain the source-result order after bounded
  de-duplication; one pure `canonicalize_prm_action_snapshot(answer)` routine
  builds the snapshot and digest during registration and recomputes/validates it
  during loading, and downstream proposal construction uses only that validated
  snapshot rather than mutable duplicate summary fields. A `TypeError`,
  `ValueError`, non-finite value or non-serializable source returns no controls
  while still rendering the answer; it creates neither a context row nor a
  receipt; and
- optional `source_project_ref={origin: answer.project_name, value:
  source_snapshot.project_name}` only when that nonempty bounded snapshot field
  exists; it is an exact copy for display/provenance, never authority; and
- offered action codes, `owner_chat_id_hash`, `actor_id_hash` and expiry. The
  callback validates its requested action against those codes and the row before
  proposal/confirmation work.

PA-00 is deliberately private-owner only: controls render only when a positive
private `actor_id == chat_id == owner_chat_id` is available. `owner_chat_id`
comes only from the already-required `TELEGRAM_OWNER_CHAT_ID` startup boundary;
it is passed as data, not read again from a callback or inferred from a stored
row. PA-00 defines one shared
`canonical_private_owner_id(value) -> str | None` helper for registration,
callback, polling and compatibility dispatch. It accepts only an ASCII decimal
string matching `[1-9][0-9]{0,18}` whose integer value is at most
`9223372036854775807`, and returns that unchanged canonical string; it rejects
zero, negatives, `+`/whitespace/leading zero forms, non-numeric values and
out-of-range values. Equality is tested only between three non-`None` canonical
values. The tests exercise that predicate at registration, callback, Telegram
text/embedded-transcript/completed-voice paths and compatibility dispatch. The
identity propagation matrix is part of PA-00's implementation scope:

| ingress | authenticated identity propagated | action-control behavior |
| --- | --- | --- |
| Telegram text, embedded transcript, and completed voice transcript in `bot.bot` | message `chat.id`, message `from.id`, configured owner chat ID -> `bot.handlers.dispatch_command` -> `bot.prm_handlers.dispatch_prm_command` -> `_post_answer_action_bundle` -> registration | controls only after all three equal; ordinary answer remains available without controls otherwise |
| Compatibility `bot.handlers.dispatch_command` callers | explicit `actor_id` and `owner_chat_id` keyword inputs forwarded unchanged | a missing/incomplete tuple is a safe no-controls answer; it must not synthesize `actor_id=chat_id` |
| Telegram inline callback in `bot.bot._handle_callback` | callback message `chat.id`, callback `from.id`, configured owner chat ID -> `bot.callbacks.handle_prm_post_answer_callback` -> PRM action handler | reject before proposal work unless all three equal; UTD namespaces retain their separate existing contract |
| direct/unit/CLI call with no authenticated tuple | none | it may exercise read-only answer rendering, but must neither register nor accept a PRM post-answer control |

`test_prm_entrypoints_propagate_private_owner_identity_or_render_no_controls`
is a matrix over text, embedded/completed-voice transcript, compatibility
dispatch and inline callback, with positive, absent, group, malformed,
noncanonical and out-of-range IDs. It proves unchanged propagation only on the
allowed path; every other cell has no control or is unavailable.

The registration and callback interfaces therefore carry all three fields:
`build_post_answer_actions(..., chat_id, actor_id, owner_chat_id)` and
`handle_prm_post_answer_callback(..., chat_id, actor_id, owner_chat_id)`.
The tuple-bearing transport signatures are
`bot.bot.dispatch_command(..., actor_id=None, owner_chat_id=None)`,
`bot.handlers.dispatch_command(..., actor_id=None, owner_chat_id=None)`,
`bot.prm_handlers.dispatch_prm_command(..., actor_id=None, owner_chat_id=None)`,
and `_post_answer_action_bundle(..., actor_id=None, owner_chat_id=None)`.
`run_bot` alone extracts the Telegram sender plus configured owner and passes
them unchanged; omitted tuple defaults mean answer-without-controls. The
callback facade is `handle_prm_post_answer_callback(..., chat_id, actor_id=None,
owner_chat_id=None)`: this rule applies only to `prma`/`prmc`; `utdp`/`utdc`/
`utdw`/`utds` keep their existing separate contracts.
The callback handler compares both persisted hashes with the incoming tuple; a
group, absent identity or mismatch returns unavailable and performs no write.
This limitation must remain explicit until a separately designed multi-actor
model exists. The legacy `bot.legacy_handlers._prm_post_answer_markup` is an
intentional no-controls path in PA-00: it has no authenticated actor/owner
tuple, so it may render its answer but receives `reply_markup=None` from the
shared builder.

`_register_context` is the only creator after a rendered answer.
The callback pipeline has an explicit read-only validation phase: parse prefix,
context ID and action; load one row; validate private identity, row status and
expiry, binding schema/context ID, canonical digest, offered action, and the
requested draft/confirmation action. Only after every check succeeds may a
separate mutation phase create a proposal, claim a confirmation, record a
receipt, cancel a valid context, or update status. A missing row, bad parse,
malformed/pre-binding/tampered binding, expired context, wrong chat/actor/owner
or unoffered action returns the same fail-closed unavailable result. It makes
zero `INSERT`, `UPDATE` or `DELETE` statements in
`prm_post_answer_proposals`, makes no memory/receipt write, and does not clean
up expired contexts on this callback path. Expiry cleanup is a separately
authorized maintenance concern, not an invalid-input side effect. Tests snapshot
the row and memory/receipt counts before each rejected case and trace the outer
callback handler (not merely a helper) to prove this. A malformed callback
parse or malformed row JSON is caught at that boundary and returns that same
unavailable result rather than raising.

`validate_prm_post_answer_callback(...) -> ValidatedPrmAction | Unavailable` is
pure/read-only. Its immutable result holds context/action, canonical source
snapshot, row status/expiry, and SHA-256 fingerprints of the stored
`summary_json` and `proposals_json`. `apply_validated_prm_action(db_path,
validated) -> AppliedAction | Unavailable` never reparses callback data: in one
transaction it conditionally rereads/updates exactly that context only when
status, expiry and both fingerprints still match, then performs its one allowed
proposal/receipt/status mutation. A failed compare-and-swap returns unavailable
with no durable write; success consumes the bound transition once. Transport
validates once: invalid -> acknowledge “Action unavailable” and no follow-up;
valid -> apply CAS -> acknowledge/render only on success, otherwise the same
unavailable acknowledgement. Thus no mutation follows acknowledgement for a
different row state. UTD keeps its separate acknowledgement contract.
`bot._handle_callback` first classifies the prefix: for `prma`/`prmc`, malformed
data, missing message/chat, wrong owner, group, absent or noncanonical identity
all enter that validation result rather than an earlier transport denial. Each
gets exactly one `Action unavailable` acknowledgement, no follow-up and no
durable write. Only non-PRM/UTD prefixes retain existing acknowledgement paths.
`test_handle_callback_validates_prm_before_acknowledgement` covers
`bot.bot._handle_callback`, stale validation and malformed callback/row JSON.

Legacy natural-language save/watch never calls `handle_post_answer_callback` or
synthesizes an actor ID. Without a valid control it says: “This action is
unavailable. Run the request again to receive a new action button.” It never
reads `_PRM_DIALOG_STATE` or turns its last project/topic/context into a
callback; the no-reroute test requires zero application/search calls.

Initial `offered_action_codes` authorize only the buttons rendered with the
answer. A non-initial callback code is accepted solely through the following
server-bound dynamic state machine, stored under reserved `proposals_json`
keys after the full immutable binding/identity validation:

- a valid initially offered `n` with more than one bound evidence item records
  a selection-open state and issues only `n1` through the actual bounded item
  count; a child code requires that state, index and parent `n` offer;
- a valid initially offered `m` or `x` records its exact reason-parent and
  issues the displayed reason codes; each reason requires that issued parent;
- a valid selection or proposal preview records the exact `c` cancel issuance;
  `c` requires that issuance, current ready/pending state and no confirmation
  lock; and
- `prmc:<context>:<action>` requires the exact proposal/token created by a
  valid preceding action; it cannot create a proposal itself.

No other dynamic code is accepted. A forged, stale or cross-transition `c`,
`n1`–`n5`, reason, or confirmation fails read-only as unavailable. The action
tests cover every positive transition and a forged transition before its parent.

The existing UTD flows share this table but are not PRM bindings. PA-00 repairs
their clean-schema incompatibility without a migration: `utd_state` in their
`summary_json` is authoritative, while table status maps `draft -> ready`,
`previewed|confirming -> pending`, `confirmed -> confirmed`, and
`cancelled|expired -> cancelled`. `encode_utd_proposal_state` and
`decode_utd_proposal_state` atomically maintain that pair in
`assistant.utd_profile_store` only. `utd_profile.py` invokes this storage API
but performs no direct proposal-state SQL. Typed `UtdTransitionResult(applied|
unavailable)` owns `BEGIN IMMEDIATE`/commit-or-rollback; callers cannot nest or
partially own its transaction. Missing, malformed or
mismatched state/status (including untagged `pending`) fails closed without a
write. `transition_utd_proposal(conn, context_id, expected, next)` begins one
transaction, decodes the current pair, and conditionally updates both encoded
JSON and mapped status only where the exact expected logical state, mapped
status and prior JSON fingerprint still match. Allowed transitions are
`draft -> draft|previewed|cancelled`; `previewed -> draft|confirming|cancelled|expired`;
`confirming -> confirmed|previewed|cancelled|expired`; terminal states have none. All
onboarding, draft load/save/discard, profile preview/confirm/cancel and
subscription start/claim/finish/cancel call that codec/guard. A canonical-schema
integration test executes every transition and races confirm/cancel: exactly one
CAS wins. A provider-confirm known-no-write failure transitions
`confirming -> previewed` by CAS so the exact preview can be retried. Timeout,
crash or ambiguous provider outcome leaves `confirming` locked: no retry occurs
until explicit reconciliation establishes confirmed, cancelled, or known-no-write
previewed. `draft -> draft` is guarded category/settings edit; `previewed ->
draft` atomically invalidates its confirmation and old callback. Acceptance is
blank onboarding -> category -> preview -> return/edit -> old-confirmation denial
-> new preview -> confirm. Recovery tests cover both outcomes. This permits a real UTD-path drain fixture; shared drain blocks old
UTD code until active mapped rows are gone.

This is JSON-additive: PA-00 adds no table migration. Only `context_kind=prm`
rows receive/require this binding; the shared UTD draft representation is not
rewritten. Pre-change and partially-created PRM rows fail closed under the new
code.

PA-00 has no destructive shared-table rollback. A rollback to a pre-PA-00 PRM
handler is prohibited until a read-only, owner-restricted drain report proves
there are no unexpired active rows for that owner in either established hash
namespace. The report canonicalizes the raw owner once, calculates
`:prm_owner_hash` with the current `prm.post-answer.v1` algorithm and
`:utd_owner_hash` by invoking the current `assistant.utd_profile_store._chat_hash`
helper (therefore using the configured `PI_SAVE_CONFIRMATION_SECRET` without
exposing it), then SELECTs all rows for either hash before strict JSON/status/UTC
expiry parsing. Nonterminal unexpired rows block; issued PRM confirmation locks
and UTD `confirming` block regardless of expiry until reconciliation. Bad,
malformed or unknown data is unavailable and blocks; no loader/drain deletes a
confirming payload. Its
only classification is derived from `summary_json`: `prm_binding_v1` when
`context_kind="prm"`; `legacy_prm_candidate` when the old PRM
`primary_intent`/`allowed_actions` shape is present; `utd_profile` or
`utd_subscription` for their current `kind` values; otherwise `unknown`.
Every classification is a rollback blocker rather than a mutation target. The
callable is
`read_prm_rollback_drain(db_path, *, owner_chat_id, now=None) -> dict`, located
with the PRM action store. It first canonicalizes the owner, treats a missing
database/table, bad owner or SQL/JSON error as
`{status: "unavailable", blocker_count: null}` and forbids rollback. For a
valid read it returns only `status="blocked"|"clear"`, supplied UTC `now`,
`blocker_count`, and count-only `classifications` of
`prm_binding_v1`, `legacy_prm_candidate`, `utd_profile`, `utd_subscription`,
and `unknown`; it never emits a raw chat ID, context ID or payload. Its SQLite
connection is read-only and may execute only the selector/metadata `SELECT`s.
A trace-callback test creates a genuine UTD row through its current onboarding
path/hash, then proves it is a blocker and that no non-`SELECT` statement
occurs, including for unavailable rows. The order is: stop rendering new PRM
controls; keep the PA-00 handler in
fail-closed drain mode; wait for/cancel only through a valid current user
action until the report is zero; independently capture the zero report; only
then activate an old handler. There is no automatic `DELETE`, generic
`UPDATE`, or UTD selector in this procedure. Confirmed receipts and all UTD
drafts are preserved. PA-00 tests the report's private-owner restriction and
that a UTD row cannot be modified by its query.

PA-03 owns the complete plain-language `yes` state: it adds an explicit current
confirmation reference to `ConversationState`, clears it on an independent
topic/cancellation and requires an exact matching visible proposal. PA-13 adds
the corresponding provider-write confirmation and reconciliation. Thus PA-00
tests callback/source integrity and denies unsafe legacy text action selection;
it does not claim that natural-language confirmation is already shipped.

## Vertical slices and acceptance

`PA.design.json` is the dependency/scope registry for PA-00..18. PA-00
classifies the baseline as evaluator, dispatch, or both. Its evaluator has two
separate cases: free-text save/watch is denied without inventing a preview,
callback, retrieval call or `eval-*` ID; a declared immutable bound-inline
fixture checks project provenance. It never preserves stale dialogue merely to
satisfy the old corpus. The direct handler tests prove the real callback path.

These are planned test-first tests, not pre-approval evidence. Existing commands
are regression floors; each code slice registers exact acceptance tests and
intended semantic failures before implementation. PA-00 records interpreter,
HEAD, runtime mode and evaluator IDs; historic `cc105…` is reference-only. Its
scope includes the affected callbacks/UTD/ledger tests and legacy markup within
`files<=22`.

Independent product/program design review precedes exact human approval.
Slice/Test Critic/privacy reviews follow risk; full review is batched at phase
boundaries, never replaced by a model's self-review. Required human acceptance,
live account grants and release decisions remain explicit. Continue through
all ready assigned work after passed gates; independent external access blockers
do not cancel unrelated work or justify falsely claiming whole completion.

## Requirement coverage by slice

CHAT/UX -> PA-03; MEM -> PA-03/14; SEARCH/EVIDENCE/RAG -> PA-04/05/06;
BRIEF/VISUAL -> PA-07/08; WATCH -> PA-09; CONNECT -> PA-10/11;
ACADEMIC -> PA-12; PERM/SEC/ACT -> PA-02/13/17; MEDIA -> PA-15;
MODEL/COST -> PA-02/16; ARCH/OPS/MIGRATION -> PA-00/01/17;
EVAL/DONE -> all slices and PA-18. Read corresponding spec sections on demand.

No test result, working provider, visual approval or token-saving percentage
is asserted by this design. Full product acceptance needs current project
checks, adversarial/positive holdouts, real authorized integration and owner
usefulness/visual evidence.
