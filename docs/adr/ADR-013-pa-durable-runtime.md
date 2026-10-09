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

## Current tooling audit — actual native79

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
