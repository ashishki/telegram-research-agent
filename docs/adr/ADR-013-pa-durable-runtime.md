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
