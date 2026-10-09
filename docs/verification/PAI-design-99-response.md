# Review99 STOP — concrete P1 response and preserved failures

2026-10-09. Actual program/product99 reviewed9098d0c, STOP_SHIP with1 P1/3 P2;
403.435s, observed glm-5.3/requested max/observed effort unknown,
usage42822/30014/72836. Exact immutable receipt/input/report/log hashes are in
PAI-review-continuation-99.json. Program/foundation98 was ADVISORY;
program/sources100 and completeness101 timed out after7202.238/7202.230s, with
no valid verdict/model/usage and unknown cost/outcome. All101 starts count.
No active review process remained on continuation; no result was substituted.

P1: distinguish trusted live pre-callback SQLite acquisition failure from
at/after-callback failure. KnownDeliveryNotStarted records not_sent with
transport_not_started; this exact adapter evidence survives the shared policy's
ScopeTransportUnknown wrapper. No SQLite rollback/empty ledger/crash proves
absence. Budgets and operation/attempt identities stay conservative; no automatic
refund/resend. UI says sending did not start without inventing provider evidence.
All default durable sends are designed for one serial effect dispatcher; read
workers enqueue. Unrelated archive SQLite writers can still cause busy.

Real held-SQLite-writer plus PostgreSQL policy test gives zero provider calls and
not_sent; held-reader COMMIT busy after one accepted synthetic call stays unknown.
The first known-not-sent multipart part also settles its aggregate not_sent;
a later failure preserves prior-part receipts and the aggregate unknown fence.
Interrupt-before-any-child remains unknown. Repeat dispatch preserves the exact
attempt identity and produces no additional calls. Both new exact REQUIRED nodes
were registered in registry/tasks/matrix before their implementation. Current
full-spec runtime acceptance is not claimed by this scoped verification.

Controlled continuation uses a new explicit owner-requested result/occurrence,
fresh identity/current permissions/schedule/budget, and fresh confirmation for
Act. It never resets or aliases the original unresolved effect. The current
Telegram sender has acceptance receipts only; unsupported lookup remains visibly
unresolved. An owner's non-receipt assertion alone is not provider absence proof.

P2 dispositions: PAI-10 owns src/prm/cli.py; PAI-28 now explicitly owns
src/external_watch/** stop/rewire and singleton dispatcher cutover, with actual
service/timer changes still separately gated. PAI-12's suggested exact slice-level
injection node remains open P2; existing/PAI-26 tests are not relabeled as it.
Reconciliation capability limitations are explicit above, without adopting an
unsafe owner-assertion shortcut. Actual98 P2s remain in its immutable report;
current-tooling wording now points to genuine93, not historical79. No P2 is
invented as fully accepted, and the implementer does not close P1 independently.

Initial prior-turn targeted test failed because shared policy wrapped the typed
adapter exception; local exact-call capture corrected it, preserving the log.
Current strict slice09 tests:87 passed40.95s, zero skips/failures. Plan/bridge first
reported4 failures44passes because the map was20048 characters and the pinned
renderer limit is20000; compact audit prose shortened to19894, without changing
requirements or weakening the guard. Corrected48 passed3.41s. Pin/32 packets/
69 exact IDs/ten scenarios/diff checks passed. Exact current commands/results/
source hashes and all prior logs: PAI-validation-20261009-99.json.

Actual require_tooling_audit accepted unchanged critical sources against genuine93.
Design/runtime-only corrections invalidate older design parts, not this tooling
manifest. Allocate ONE fresh full program/product102 independent P1 recheck under
ongoing necessary-review authority; remaining103..109 are blocked until closure.
All eight new parts must share one corrected committed HEAD/design. Same public/
synthetic sources/provider/model/max/input1MB/output131072/watchdog7200,
one explicit request per part, no automatic retry/fallback. Real finalizer and
pinned generic parser are mandatory. No human/live/release acceptance is granted.

## Preserved actual independent report

# Independent OpenCode Go program_design_review

PROGRAM_DESIGN_REVIEW: STOP_SHIP

{
  "verdict": "STOP_SHIP",
  "findings": [
    {
      "severity": "P1",
      "title": "PAI-09/ADR-013: SQLite lock failure after prepared attempt is specified as 'unknown' even when the send provably never started; concurrent-s",
      "issue": "ADR-013 §Cross-store delivery sets the watch-store SQLite busy_timeout to 500ms (below the 10s transport bound) and mandates that 'a lock failure after a prepared attempt keeps unknown, never auto-resends or proves no effect'. A BEGIN IMMEDIATE busy_timeout expiry happens BEFORE the sender callback is invoked, so no provider call occurred and known_no_effect is locally provable; classifying it as unknown (a) breaks spec §3.3's required distinction between 'действие не выполнено' and 'результат отправки неизвестен' and PAI-09's own outcome 'правдиво показывают исход', and (b) permanently fences that effect identity against re-dispatch ('Unknown or any unresolved prepared effect blocks re-dispatch'; the fence even survives cancellation), leaving an ordinary reply/digest in awaiting_reconcil",
      "fix": "In ADR-013/PAI-09: (1) specify the dispatch topology — all durable sends, foreground and background, dispatched by the single effect executor serially, or an explicit PG admission lock per SQLite store so contenders queue instead of failing at 500ms; (2) distinguish pre-callback lock-acquisition failure (transition prepared -> known_no_effect, re-dispatchable) from failures at/after the transport call (unknown); (3) register the concurrent-sender/busy_timeout case in tests/test_pai_delivery.py next to test_postgres_authority_spans_legacy_sqlite_send."
    },
    {
      "severity": "P2",
      "title": "Registry file-scope gaps: legacy external_watch ownership and PAI-10 CLI file",
      "issue": "PAI-08 moves watch scheduling to PostgreSQL but src/external_watch/** (retained per spec §10.1 as the public watch adapter, with its own timers/writers on the same explicit-path SQLite store) is in no PAI-07..15 slice's allowed_files; decommissioning or idempotent coexistence of the legacy loop is unowned, feeding the P1 contention case and a duplicate-delivery risk during cutover that depends on unstated shared occurrence/effect keys. Separately, PAI-10's scope claims the composition root injects the model route into 'Telegram/CLI/application' but src/prm/cli.py is not in PAI-10's allowed_files (only PAI-07's), so the card cannot complete its stated CLI scope without a registry amendment.",
      "fix": "Name the owning card (PAI-08 or a cutover card) and allowed files for stopping/rewiring legacy external_watch timers and writers, or document the shared idempotency identity that makes legacy and new paths duplicate-safe; add src/prm/cli.py to PAI-10's allowed_files or state that CLI consumes the root only via src/prm/application.py."
    },
    {
      "severity": "P2",
      "title": "PAI-12 has no slice-level required security-path acceptance",
      "issue": "PAI-10, PAI-11 and PAI-13 each register a REQUIRED security_path_acceptance node for untrusted-content/authority boundaries (SEC-01/SEC-02), but PAI-12's web/GitHub fetched-content rule ('untrusted text не выдаёт инструментам прав') has no exact test node; its first behavioral verification is deferred to PAI-26's SC13.2-09, two phases after the adapter code lands. This is an internal-consistency gap in the programme's own security-acceptance convention, not a proven runtime defect (the behavior is specified and PAI-26 covers it).",
      "fix": "Register an exact required node in tests/test_pai_web_github.py (e.g. test_fetched_web_content_injection_cannot_create_authority_or_effects) mirroring the PAI-11/13 pattern, and bind it in PAI.requirements.json security_test_nodes."
    },
    {
      "severity": "P2",
      "title": "Reconciliation evidence for unknown Telegram sends is undefined",
      "issue": "PAI-09 mandates a 'provider reconciliation adapter and UI for unknown', and WATCH-04 requires stored states, receipts AND a сверка procedure; but the design never states what evidence reconcile() can obtain for the primary transport (Telegram Bot API exposes no message-status lookup), so a crash at the prepare/dispatch boundary can leave an ordinary reply in permanent unknown with no stated resolution path (owner-confirm-not-seen -> known_no_effect, or equivalent), making the conservative fence effectively irreversible for chat replies.",
      "fix": "Specify per-transport reconciliation capability in PAI-09/ADR-013: for transports with no evidence API, define an auditable owner-resolution action (e.g. owner confirms non-receipt resolves to known_no_effect once), and cover it in tests/test_pai_delivery.py."
    }
  ],
  "not_verified": [
    "No implementation exists for PAI-07..15 (status 'planned'); all behaviors, new tests/test_pai_* files and acceptance outcomes are unverified plans, and the cited dated runtime snapshot (caf97a7) was not re-verified here.",
    "Actual contents/correctness of the reused legacy contracts: locked-send implementation in src/bot/telegram_delivery.py, watch store schema, src/prm/watch_jobs.py and src/external_watch/ paths (source not supplied).",
    "PA-09 quiet-hours/DST/deadline-recalculation domain rules that PAI-08 reuses (docs/design/PA.md not supplied); urgent-exception consent model unverifiable in this packet.",
    "Kill-at-precommit/dispatch/settlement, DB-disconnect-during-send, lost-ACK and DB-outage recovery test contents (planned under PAI-09/PAI-26; not written).",
    "All latency/lock-wait/queue-lag figures (intake p95<=2s, Chat<=10s, Search<=45s) are stated targets, not measurements; freeze-load concurrency outcomes are verified only at PAI-26.",
    "Real Telegram/HTTP/provider behavior: every in-phase verification uses fake transports/servers/fixtures.",
    "RU/EN retrieval holdout recall, editorial-selection quality holdout, and cost/latency measurements for PAI-11/13/14.",
    "Reader endpoint network binding and owner-authentication mechanism details; real rendered Telegram/HTML/PDF visual quality (deferred to PAI-27/29 gates)."
  ],
  "summary": "The PAI-07..15 product-phase design is unusually rigorous on permissions (SEC-01/02 nodes, guards before HTTP, PG authority spanning the retained SQLite locked-send), durable attempts, unknown-effect fencing, scheduler idempotency and recovery, with internally consistent registry/dependency/matrix bindings. One P1 blocks: ADR-013/PAI-09 specify that ANY SQLite lock failure after a prepared attempt yields 'unknown' and blocks re-dispatch, but a busy_timeout (500ms) failure acquiring the SQLite write lock occurs before the sender callback runs, so the message provably never sent is reported as unknown-send — violating spec §3.3's explicit not-performed vs unknown distinction and PAI-09's own truthfulness outcome — and is permanently fenced pending manual reconciliation. The case is reachable because foreground replies and background digests use distinct purpose grants (PAI.md: final locks cover 'only current scope' rows), the retained legacy external_watch writer shares the same store and is owned by no slice, and the design never pins which process dispatches foreground sends. Remaining P2s cover registry file-scope gaps, PAI-12's missing slice-level security node, and undefined reconciliation evidence for Telegram unknowns. Verdict STOP_SHIP until the P1 is resolved in ADR-013/PAI-09; this phase review alone approves nothing and leaves the listed items unverified."
}
