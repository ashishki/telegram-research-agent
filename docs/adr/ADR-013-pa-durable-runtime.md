# ADR-013: PostgreSQL authority/jobs and retained SQLite archive

Date: 2026-10-06
Status: proposed; independent design reviews and hash-bound human approval pending.
Design: [PAI](../design/PAI.md). No infrastructure or runtime is activated here.

## Proposed decision

One modular Python product and release. PostgreSQL owns mutable PA authority,
conversation/result references, budgets, confirmations, attempts, subscriptions
and jobs. SQLite raw_posts/posts/posts_fts keeps canonical Telegram source IDs
and retrieval. No distributed transaction or dual-write between databases:
workers load a version/digest-bound archive reference and revalidate it.
Archive workers remain on the archive host; never network-mount SQLite WAL.

Use a small PostgreSQL job repository with FOR UPDATE SKIP LOCKED, no broker,
Redis or workflow engine initially. The queue persists intentions and object
refs, never Python callables/pickle, credentials or whole mailbox payloads.
Transactional enqueue, policy reservations and side-effect records share one
database transaction. A new library would otherwise need to expose the same
authority transaction and avoid becoming a second action-state source.
The narrow repository is bounded to enqueue/claim/heartbeat/checkpoint/cancel/
complete/recover; it does not become a generic workflow language.

Procrastinate remains a plausible alternative requiring a measured integration
spike. Celery/Redis/RabbitMQ add a second reliability surface/outbox and do not
solve unknown effects. Temporal is deferred until measured workflow complexity.
No assertion about current package releases/support is used to choose them.
Pin the driver/DB/test image and check official docs during PAI-02.

## Final effect ordering

Choose narrow row locking rather than an unproven sequencer. In one durable
transaction, lock grant revisions, subscription/proposal and reservation rows
in deterministic key order; validate current scope/consent/expiry and claim a
one-use attempt, then commit the prepared attempt BEFORE any provider call.
After commit, a second transaction reacquires those same policy rows, checks
cancellation/revocation/version/time/budget, marks dispatch_started, and holds
only the affected row locks through one bounded transport call and settlement.
If revocation won the lock first, no call occurs. If dispatch won first,
pause/revoke acknowledgement waits for that bounded call; never imply an effect
already started has been undone. Other scopes/jobs retain short transactions.

Loss of the DB connection/transaction during transport cannot fence the
provider. The precommitted prepared attempt remains durable and blocks automatic
takeover. Recovery treats every unresolved prepared/dispatching attempt as
potentially unknown, even if the sender might not have started. A checkpoint
or lease expiry never proves no effect. Only separately authorized reconciliation
with provider evidence establishes success or known-no-effect. If that evidence
is unavailable, keep unknown and require an explicit new decision. Never resend
because a local receipt or provider search result is absent.

One effect executor initially, but correctness depends on DB uniqueness/locks,
not process count. Fence tokens govern only database writes. Prepared attempts
have no automatic reclaim-to-send. A future short-transaction per-scope sequencer
must be separately designed and race-tested before changing this contract.

## Authority and lifecycle

Shared grants preserve owner/connection/resource/operation/data-class/provider/
purpose, time validity and revision. A serialized job is not a grant. Worker
loads current authority before EACH provider call and final effect. Unknown
pricing fails closed for paid reservation; multi-call groups settle measured
usage atomically. A worker crash preserves its reservation until conservative
settlement; no silent refund/reallocation of potentially incurred spend.

Confirmation is owner/conversation/result/version/content/recipient/account/
time-bound, expiring and single-use. A crash after claim cannot restore its
token. Plain yes resolves one currently visible exact proposal only, without
new routing/search. Unknown outcomes never become failed/retryable on restore.

## Consequences and gates

Holding narrow locks through a bounded transport occupies a DB connection and
delays changes within that scope; enforce timeout, lock ordering and separate
interactive/render/effect pools. Cancellation acknowledges pending work stopped
but reports already-started work accurately. Tests must kill processes during
every precommit/dispatch/settlement boundary, including DB disconnection while
a fake provider completes after timeout.

Synthetic isolated test DB only in PAI-02: explicit loopback test DSN, separate
role/database and explicit target marker, no production/.env/default fallback.
Runtime backend selection is explicit and disabled until configured. No new
production data, service/timer, credentials, provider call or paid work here.

Single-writer cutover requires PAI-25 copy rehearsal and PAI-28 scoped authority.
Before new PostgreSQL writes, verified snapshot rollback is possible; afterwards
only tested delta transfer or forward fix preserves receipts/unknown fences.
Redis and archive migration require measured triggers and separate ADRs.

## Unknown settlement and cross-store deletion

Permanent unknown spend remains conservatively consumed in its original window.
Owner-confirmed write-off consumes the upper bound; new work requires a distinct
funded operation and never refunds/retries the unknown effect. PAI-03/23/26 test
visible exhaustion, rollover and one-use conservative settlement.

PostgreSQL tombstones govern visibility before non-atomic physical cleanup.
Idempotent per-store steps/watermarks mark unavailable cleanup pending/partial;
serving checks deny stale data and unavailable authority. Restores replay
authority tombstones before reads. Independent canonical archive records are
preserved. PAI-21/25/26 test outage, restart/restore and partial deletion.

## Contract clarifications after independent foundation review

Durable effects have prepared and terminal states. dispatch_started is a
transaction-local marker held with the final locks through transport/settlement;
it need not become separately observable. Prepared may already have sent;
recovery/operator views remain potentially unknown and never auto-resend.
Grant/consent/proposal and per-attempt reservation locks span the call; shared
budget-window locks do not. Synthetic lock/statement bounds are 1/2 s, call
bound 10 s, final idle transaction bound 15 s with a separate effect pool.
Timeout preserves prepared/unknown and conservatively consumed budget.
Unknown blocks that effect identity and dependent job/group steps, while
unrelated work continues. Heartbeat/fencing, input digest/visibility validation,
safe compute recovery and version quarantine are explicit PAI interfaces.
PAI-05 precedes PAI-06 to establish shared conversation/object contracts.
The existing src/assistant/prm_post_answer_actions.py is a compatibility adapter
calling shared src/prm action semantics; it is not a separate action engine.

## Scheduler reservation lifecycle — review80 clarification

Scheduler enqueue records intent and a unique occurrence, not a paid reservation
for every due schedule. Workers reserve for the next bounded external step after
claim/current-grant validation and before dispatch; the reservation and that
step's durable attempt/enqueue changes share a transaction when applicable.
ADR-013's shared transaction requirement does not mandate reserving at schedule
enqueue. Cancellation/pause/revocation before any billable invocation or durable
prepared/unknown attempt settles a held unused reservation once at zero and
releases its upper bound. Already measured usage is settled as measured; possible
invocation/prepared/unknown spend stays conservative and cannot be refunded from
job status alone. PAI-03/08/26 must verify both unused release and unknown fences.

## Concrete evidence bindings — full PAI compact-map companion

PAI-00 tests/test_prm_product_ux_eval.py and tests/test_opencode_role_review.py already occur in BOTH slice argv and matrix.test_files;
all seven named regression files exist. check_pai_plan validates full69 IDs,
exact ten scenario/recovery bindings, hashes, dependencies and case identity;
run_pai_acceptance requires actual named cases/zero skips, not planned evidence.
The actual PAI-00 reconciliation_regression argv is {python}
tools/run_pai_acceptance.py -q tests/test_playbook_bridge.py
tests/test_assistant_conversation.py tests/test_prm_product_ux_eval.py
tests/test_pai_plan.py tests/test_opencode_role_review.py tests/test_memory_research.py
tests/test_pai_acceptance_guard.py. Both alleged missing files are explicitly
registered at88da0f5 and unchanged here; no fabricated run or weakened guard.
Formal planned slice status does not imply absent local implementation evidence:
the separate runtime snapshot caf97a7 has320 synthetic cases/69 requirement IDs/
ten scenarios, as bound in PAI-release-candidate.json. That dated runtime evidence
is neither current tooling verification nor real provider/human product acceptance.
Baseline PAI-00-reconciliation.md binds exact clock-fixture failures, commands,
causes and corrections at 8faee4; old PA-00 UX was already repaired.
PAI-00-file-manifest.json mechanically binds 66 paths<=72, uniqueness/existence/
allowed scope and rollback boundaries; feature-design/source publications belong
to PAI-01/B..F. Manifest SHA256: 87f7ba6178da7fed20781debccde9b979cd863f001bcc61b184d7ef2785f4852.
Future human records: .playbook-artifacts/workflows/PAI/approval.json (real pinned
TTY, human identity/date/design hashes/role refs); controlled PAI-29/owner-acceptance.json
(candidateSHA/date/owner/per69ID+tenScenario live/visual/usefulness evidence hashes).
Do not forge future date/SHA. Controlled PAI-27/approved-scope.json and durable
expiring CapabilityGrants separately bind exact live account/provider/operation/
egress/bounds; policy checks before credentials/transport/final effects. PAI-28/
cutover-approval.json binds production SHA/target/window/rollback. No live approval.
Receipt schemas, immutable identity/hash/scope/verdict checks and tooling/design/
human separation are specified in REVIEW_POLICY.md and enforced by actual native
consumers. Full factual bindings: docs/verification/PAI-design-evidence-bindings.md.

## Historical tooling audit — actual native79

Actual native tooling79 completed ADVISORY on committed
88da0f54aad02b58ec1c606e0360c47223ba34e4, after the GLM/max/output changes.
Result: .playbook-artifacts/opencode-runs/opencode-64253758e95a49e488ae30255d4ed3e3/result.json;
SHA256: 28cabae0ee814f9033272aef279af712e82671fe9642a8db4cf059e3d6d808d2.
Report SHA256: d909d9223e5e67cc0ca00f9f011926478644bb6adba4e0c865a89b4c4e432d0a.
Observed model glm-5.3; requested max, observed effort unknown;0 P0/0 P1/4 P2.
The actual require_tooling_audit consumer accepted its unchanged critical hashes;
PAI-review-continuation-79.json and PAI-native-tooling-79-response.md preserve
command/input/usage/provenance/findings. Audit78's length failure and prior STOPs
remain unchanged historical evidence, not the current gate. This design-only
wording correction does not alter audited tooling/policy or promote a role record.

## Cross-store delivery and security-path bindings — product review88

PostgreSQL is the authority for source grants, delivery consent/subscription,
proposal and reservation. Acquire PG authority rows in the existing deterministic
source-before-subscription order BEFORE entering any retained SQLite locked-send.
Keep those same PG locks through the ENTIRE SQLite transaction and bounded sender
callback; SQLite commits/closes before releasing PG. Never check PG, release it,
then enter SQLite. No SQLite-first/PG-second path. Synthetic SQLite busy_timeout
is500ms, below the transport bound. A trusted live adapter that fails acquiring
SQLite before ENTERING the sender callback proves known_no_effect: report not_sent
with transport_not_started, preserve the original attempt, and do not auto-resend.
Failure at/after callback entry, worker loss or a prepared record alone stays
unknown; a SQLite rollback/empty local ledger never proves no external effect. Revoke-wins-lock means no sender;
dispatch-wins means revoke acknowledgement waits until the bounded sender exits.
PAI-09 registers test_postgres_authority_spans_legacy_sqlite_send for both outcomes.

PAI-09 rechecks quiet hours/time windows at actual delivery (queue delay/recovery
cannot turn a routine digest into an urgent exception). Foreground replies retain
existing durable prepared/unknown semantics and permission checks; proposed
latency targets do not justify weaker replay/reconciliation fences.

SEC-01 now explicitly binds PAI-11 archive synthesis and PAI-13 tool-result
synthesis; SEC-02 binds PAI-10's provider/data-class refusal. Each has a REQUIRED
security_path_acceptance entry with an exact test node in the existing registered
file. SC13.2-09 binds10/11/13 as well and runs those behaviours in its real synthetic
scenario. The unique69 requirement identities and ten scenarios are retained.
New tests exercise actual SQLite retrieval/HTTP/PostgreSQL policy and durable jobs
using synthetic inputs, not keyword-only assertions or fabricated role approval.
PAI-09/15 explicitly own composition-root registration; PAI-12 local acceptance
uses fake I/O and existing credential patterns, with no implicit private access.

## Pre-dispatch busy and controlled continuation — review99

One serial effect executor dispatches all durable foreground/background delivery; bot/
read workers enqueue effects, never call retained SQLite send independently.
Legacy external_watch timers remain disabled; PAI-28 owns explicit writer/cutover
coordination, not implicit coexistence. Unrelated archive ingestion may still
hold a SQLite writer lock, so serialization does not eliminate busy failures.

KnownDeliveryNotStarted is trusted adapter evidence for the CURRENT attempt:
SQLite BEGIN IMMEDIATE fails before any provider callback entry. It yields
known_no_effect/not_sent; UI states the send did not begin. Confirmation/attempt
identity is never silently replayed. An owner-requested new delivery needs a new
attempt identity and fresh current scope/schedule/source/budget checks; confirmed
Act additionally needs a fresh single-use confirmation. A known-not-sent result
is visible and can be continued explicitly; it is not permanent unknown-send.

After provider callback entry, commit/lock errors or absence of a SQLite row keep
unknown and conservative spend. No automatic retry/refund; original fences
survive. No Telegram receipt/search API or owner 'I did not see it' assertion is
invented as proof of non-delivery. If evidence is unavailable, keep unresolved
unknown and allow unrelated new work, not replay of the unknown effect.

PAI-09's REQUIRED exact test node test_sqlite_busy_boundary_distinguishes_no_send
covers a real held SQLite writer BEFORE sender entry (zero external calls,
not_sent) and a held reader causing COMMIT busy AFTER a synthetic provider accepts
(one call, unknown/no replay). Existing PG revoke races and unknown ACK-loss tests
remain mandatory. Fixtures do not grant operator/live or new role acceptance.

For multipart replies, the live first-part known-no-effect result also makes the
aggregate not_sent. Once any earlier part was accepted, later known-no-effect
does not establish absence for the aggregate: preserve its partial/unknown fence
and per-part receipts. An interrupted aggregate with no child record remains
unknown; absence of a child is never substituted for live adapter evidence.
REQUIRED test_multipart_not_started_does_not_claim_absence_after_prior_send binds
both outcomes. The UI describes transport_not_started as locally not started,
without claiming a provider supplied absence evidence.

Controlled continuation does not reset a terminal delivery or its operation
fence. A new owner-requested answer/result uses a new request/job/effect identity;
a new requested digest uses a fresh authorized occurrence and current schedule
constraints. An unresolved unknown effect cannot be replayed by creating an
alias for that same effect. The current Telegram sender supplies acceptance
receipts only; no lookup evidence is implemented or claimed. Unsupported
reconciliation stays visibly unresolved, and does not prevent unrelated work.
Provider lookup, if added, requires its own exact read scope/evidence binding.

PAI-28 explicitly owns src/external_watch/** stop/rewire coordination and the
singleton serial dispatcher cutover; local design/file ownership does not
authorize changing an actual service or timer. PAI-10 owns src/prm/cli.py for
the shared chat route. Review99's PAI-12 exact security-node suggestion remains
an open P2: its existing scoped tests and PAI-26 scenario are not relabeled as
that missing required node. Independent recheck must assess the updated design.

# Binding secret-store and reconciliation contract — review105

PAI-16 TokenVault is the existing src/prm/runtime/connections.py implementation,
not a second credential backend. One absolute private directory outside repo/
archive/artifacts, mode0700, random opaque sealed_* files mode0600, authenticated
Fernet encryption with the existing46.x dependency, bounded reads/writes and
fsync. PostgreSQL stores owner/connection/account/revision and opaque references
only; no credential payload. Only a validated connection-row lookup may resolve
its active reference. Key bootstrap is an explicit PAI_* vault_key_env supplied
by the operator from separately protected service credentials; no inferred key,
automatic disk key creation, key scans, or storing key beside ciphertext.
Fixture keys are fresh ephemeral generated values. Live location/key owner
and retention selections remain in the PAI-27 approved-scope gate.

Refresh holds the owner/connection row, commits awaiting_refresh+monotone
revision BEFORE endpoint I/O, then rechecks same revision/account/reference
under lock. Concurrent refresh is refused/coalesced; timeout/worker loss requires
interactive reconnect, never replaying old rotating refresh token. Revocation
clears active ref and increments revision before deleting encrypted credential/
PKCE entries; provider-wide revocation remains a separate operator/provider
operation. Cleanup retries only unreferenced metadata and never erases a ref
active for any owner. Physical backup erase/secure erase is not falsely promised.

PAI-24/25 backup/export excludes the vault and master key; restored connection
metadata cannot revive credentials. Restores keep egress off and require explicit
re-auth/new scope/retention; a missing/wrong key refuses access. Rotation chooses
reconnect with a fresh separately protected key after authorized drain/disconnect;
no automatic decrypt/re-encrypt sweep or revived grant. Any future vault backup
needs separate encrypted backup/retention/key authority. PAI-16 required tests
bind ciphertext/permissions/wrong-key, revoke deletion, exclusion from frozen
export, code-directory refusal and exact same-connection concurrent refresh.

PAI-20/16 Graph sendMail202 is accepted for processing, not completed nor a
provider message ID. request-id is tracing metadata only. The mail action stays
unknown/pending verification until an exact separately permitted SentItems
read finds a message ID with both x-pai-attempt and x-pai-content-digest; bounded
no-match or missing read consent proves no absence. No automatic resend, alias,
or refund of original attempt. Choosing write with verification must visibly
include Mail.ReadBasic/Mail.Read and a distinct app read grant bound to
owner/connection/resource/provider/action.reconcile. Mail.ReadBasic is the
least-privileged listing permission per Microsoft docs; local $select limits to
id/internetMessageHeaders, never bodies/attachments. Provider token permission
is mailbox-wide while application selection is bounded SentItems; disclose
this distinction. If header field access is unavailable, keep unknown and
request explicit scoped escalation; never silently select Mail.Read.

Calendar create gets provider event ID or uses transactionId under an explicitly
permitted calendar event read; update/cancel require exact original event ID/
version. A trace ID/absent event/changed state never proves cancellation by this
attempt. Unknown update/cancel remain unresolved until stronger evidence is
available. Calendar scopes and application lookup grant are separate, no new
mail/contact scope. Required PAI-20 HTTP fixtures bind202-empty-body/trace-ID,
ACK loss with matching evidence, read-denied zero extra GETs, revoked OAuth
scope, no-match/collision, and no replay after success or unresolved unknown.

Sources checked2026-10-09: Microsoft Graph user-sendmail/message-send/list-messages/
message-get v1.0 and Cryptography46.0.3 Fernet official docs. These fixture and
design contracts neither select a live provider/account nor grant production,
service/key rotation, paid product egress, human acceptance or real integration.


Official sources (checked2026-10-09): [Graph sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0), [Graph message send](https://learn.microsoft.com/en-us/graph/api/message-send?view=graph-rest-1.0), [Graph list messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0), [Graph get message](https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0), [Cryptography46.0.3 Fernet](https://cryptography.io/en/46.0.3/fernet/).
