# PA — Personal Assistant Programme Design

Status: review_required. Planning depth: designed_slices. Risk: high.
The owner requested this design and its publication; exact hash-bound human
approval has not been recorded. Never manufacture that approval.

## Product outcome

One natural conversation unifies Chat, archive/web AI Search, attractive weekly
and topical Briefs, controlled Watch and confirmed Act. The full requirements
are `docs/PERSONAL_ASSISTANT_SPEC.md`; this compact map is not a replacement
for them. Do not stop after the first useful slice or declare an MVP the target.

## Current system and reuse

`src/prm/` remains the application seam; `src/bot/` is transport/presentation.
Reuse SQLite archive identity, evidence/citation contracts, saved-action
confirmation and tested external-watch delivery behavior. Existing archive
research must continue to work. Current free chat/synthesis gates and heuristic
short-lived dialogue need intentional redesign, not accidental flag changes.
The baseline CI failure is identified in the current handoff; diagnose first.

## Shape and responsibilities

Use a modular monolith with bounded capability adapters and a durable worker
for long/repeated work. No second bot, duplicated source-of-truth database or
unjustified microservice/vector-platform migration. New logical modules under
`src/prm/` may cover conversation, policy/capabilities, research, briefs,
connectors, actions, jobs and academic rules. Do not create empty frameworks
in advance of working vertical slices.

Request flow:
message -> ConversationState -> task understanding -> bounded plan -> permission
check -> typed tool results -> evidence/objects -> answer or ActionProposal ->
verification -> delivery receipt. Permission checks also run before data
leaves the system and immediately before an external write/send. The model
chooses among explicitly available tools; it never grants its own authority.

## Interfaces and invariants

- ConversationState: topic, object refs, versioned drafts/results, memory refs,
  pending proposal and jobs. A compressed summary is not write authority.
- CapabilityGrant: owner/account/resource/operation/data/provider, expiry and
  revision. Mail read is not mail write; voice is not an egress exception.
- ToolResult/EvidenceItem: status, sources/versions, timestamps, coverage and
  bounded evidence; distinguish absent, inaccessible, stale and partial.
- ResearchResult: useful answer, claim-evidence mapping, gaps and next steps.
- BriefDocument: immutable report version, period/timezone, sections, selection
  reasons, evidence and coverage. Telegram/HTML/PDF/Markdown use this SAME
  object. Reformatting does not silently regenerate or update facts.
- AcademicActionCandidate: obligation/opportunity, source, deadline precision,
  importance/applicability/confidence, lifecycle. Local done != Canvas submit.
- ActionProposal/Confirmation/ActionReceipt: exact arguments/versions, source
  result/version and optional project reference, one-use approval bound to
  owner/conversation/content, actual provider result and reconciliation.
- WatchSubscription/Job: grant revision, schedule, quiet hours, cap, lifecycle,
  checkpoints, lease and bounded retries. Unknown send != failed send.

All schemas versioned, account identity preserved even for one operator,
cache/index derived and revocable. No unbounded raw-corpus or mail export.

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

- `context_kind="prm"` and `source_result_id`, the freshly generated
  `context_id` for this answer;
- `source_snapshot`, the bounded answer fields used by a proposal: title,
  query, body, source refs, bounded evidence, primary intent, response
  contract, project value and offered action codes; and
- `source_result_version`, SHA-256 of the UTF-8 encoding of that snapshot with
  `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"),
  allow_nan=False)`. Lists retain the source-result order after bounded
  de-duplication; the digest is recomputed from `source_snapshot` in
  `_load_context`, and downstream proposal construction uses that validated
  snapshot rather than mutable duplicate summary fields;
- optional `source_project_ref={origin: answer.project_name, value: ...}`; it
  is a display/provenance value, never an authorization input; and
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

The registration and callback interfaces therefore carry all three fields:
`build_post_answer_actions(..., chat_id, actor_id, owner_chat_id)` and
`handle_prm_post_answer_callback(..., chat_id, actor_id, owner_chat_id)`.
The callback handler compares both persisted hashes with the incoming tuple; a
group, absent identity or mismatch returns unavailable and performs no write.
This limitation must remain explicit until a separately designed multi-actor
model exists.

`_register_context` is the only creator, immediately after a rendered answer.
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
the row and memory/receipt counts before each rejected case to prove this.

Legacy natural-language save/watch selection must not call
`handle_post_answer_callback` in PA-00 and must not synthesize an actor ID; it
asks for the current inline action instead. The no-reroute test instruments the
application/search entrypoint and requires zero calls for an old callback.

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
exposing it), then selects exactly
`chat_id_hash IN (:prm_owner_hash, :utd_owner_hash) AND expires_at > :now AND
status NOT IN ('confirmed','cancelled','expired')`. It is deliberately
conservative: any returned legacy, malformed or unknown row is a blocker. Its
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

## UX and briefs

Natural language, object-aware followups and clean topic changes are required.
A greeting is not an archive query; shorten means shorten the selected result.
Show truthful progress, cancellation and understandable connection/error state.
Weekly brief starts with what matters, actions and genuinely useful changes,
not 40 links. Personal relevance must have a reason. Do not invent read counts.
Telegram overview targets 1–2 screens; details unfold. Private mobile HTML is
accessible/light-dark; PDF has readable Cyrillic, hierarchy, sources and proper
page breaks. Visual inspection of real renderings is an acceptance gate.

## Academic integration

Implement the original `docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md` as a
subject module on common connectors, permissions, briefing and jobs. No reuse
of public-watch consent for private mail/Canvas. Verify institution policy and
provider scopes. Selected mail plus permitted assignments/events/announcements
come first; unsupported institution access remains an external blocker, not a
fake implemented connector. Preserve conflicting dates, unclear deadlines,
eligibility uncertainty and source versus local completion state.

## Failure and recovery

Test revoked grants while queued, expired confirmation, duplicate updates,
changed recipient/time, provider timeout, 429, injection in every source type,
missing/stale source, restart, DST and disk/restore failures. Never convert a
failed delivery into a visible-success state. Return useful partial answers;
make unavailable source coverage explicit. Finalized writes are not rolled
back by forgetting a conversation.

## Migration and rollback

Additive changes and measured rerouting, no rewrite of the archive or restart
of completed PRM-SN work. Rehearse migrations/backup restore on disposable
copies; production requires separate approval. New capabilities default off
until configured/granted. Each slice registry entry declares its own rollback.
Old report timers remain off. Read-only/archive fallback survives new-feature
outages. Avoid legacy handler growth; extract shared delivery only with tests.

## Vertical slices and acceptance

The 19 entries in `PA.design.json` are the dependency/scope registry, mirrored
by task IDs PA-00..PA-18 in `docs/tasks.md`. PA-00 first classifies the baseline
as evaluator, active dispatch, or both and proves the callback/source invariant
with named positive and denial tests; it does not preserve a stale project merely
to satisfy the old corpus. Those test functions are planned test-first work in
PA-00, not evidence that exists before human design approval. The existing
commands are regression floors, NOT sufficient feature evidence. Before
starting each code slice, register exact new acceptance test functions and add
them to its executable verification list/project verifier; show intended
failures for required semantic test-first changes. Split an oversized slice by
revising the registry and approval as necessary, not by silently exceeding its
budget.

In this checkout the supported direct focused invocation is
`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q ...`;
`python` is not assumed to exist. Registry `{python}` means the resolved
`sys.executable`. PA-00 records its exact path/version and both environment
values in the before/after receipt.

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
