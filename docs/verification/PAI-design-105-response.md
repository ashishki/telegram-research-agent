# Actual105 STOP — binding token-store and reconciliation response

2026-10-09. Actual program/sources105 reviewed1fd2452, STOP_SHIP2P1/4P2;
481.740s, observed glm-5.3/requested max/observed effort unknown,
usage40109/37130/77239. PAI-review-continuation-105.json preserves genuine
command/input/report/result/log hashes. Program104 was substantive ADVISORY;
106's actual ADVISORY summary=Incomplete. is not used as a complete part.
All106 starts consumed; original STOP/failure/poor-quality reports unchanged.

P1 secret-store binding: ADR-013 now names EXISTING TokenVault in connections.py,
Fernet46.x, private external0700 directory/0600 opaque ciphertext files, bounded
I/O+fsync, PG owner/connection/account/revision references, separately protected
operator-supplied PAI_* key, no automatic key/storage/account choice, serialized
awaiting_refresh/revision-before-I/O and conservative ACK-loss handling, revoke
cleanup and no provider-wide revocation claim. Code additionally refuses any
vault inside application code/Git. Master key/vault excluded from exports and
ordinary restore; fresh-key/re-auth/drained-rotation procedure explicitly owned
by PAI-24/25/27, no live operation executed or accepted here. REQUIRED exact
PAI-16 tests bind ciphertext/permissions/wrong key/repo refusal, real frozen PG
export exclusion, revoke deletion and two-thread same-connection refresh with
one actual synthetic token endpoint call. No fake private key enters public data.

P1 evidence scope: ADR-013/PAI-16/20 explicitly bind delegated Mail.ReadBasic
(or separately selected escalation) plus a distinct current app action.reconcile
read grant for bounded SentItems id/headers; token breadth vs app filter is
visible, consent never inferred from Mail.Send. Calendar lookup separately
requires calendar read scope; unsupported update/cancel evidence stays unknown.
Graph202 empty body is only accepted processing. request-id is tracing metadata,
never a completed-effect/object receipt. Adapter keeps202 unknown until exact
attempt+digest matching yields a provider message ID, and refuses missing OAuth
read scope under the SAME connection lock before HTTP. No nested second locked
connection, no replay/alias/refund of original unknown effect.

HTTP fixture corrected to real202 empty-body/request-id shape, with bounded
SentItems evidence generated from exact accepted synthetic write headers. Existing
preview/edit/double-click test now requires actual authorized reconciliation to
reach its original terminal success claim; it still proves exactly one write.
New REQUIRED PAI-20 cases bind accepted202 and lost ACK with allowed/denied read,
zero extra GET when permission is absent, narrowed OAuth scope denial before HTTP,
and wrong digest retaining unknown. Nodes registered before implementation in
registry/task/matrix; actual source and fixture ownership/expected_paths recorded.

P2 dispositions: the PAI-16/20 exact security-node gap is addressed; PAI-19 node,
SEC-04 setup UI, per-connection sync/cursor serialization, calendar minimization/
throttling enumeration and PAI-18 dependency amendments remain advisory work,
not silently complete. Current103/104 advisories and106 actual incomplete findings
remain in their immutable reports. Historical native79 heading is corrected;
actual current93 tooling hashes pass without any critical tooling changes.

Verified13 targeted cases52.31s,163 strict affected cases220.21s, zero skips/
failures; final48 plan/bridge3.10s, pin/32 packets/69 IDs/ten scenarios/diff pass.
Exact commands/results/source hashes: PAI-validation-20261009-105.json. No full
historical pytest, current full-spec runtime, live API/account, or independent
implementation-source acceptance is claimed. Official sources checked2026-10-09:
[Graph sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0),
[message send](https://learn.microsoft.com/en-us/graph/api/message-send?view=graph-rest-1.0),
[list messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0),
[get message](https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0),
[Fernet46.0.3](https://cryptography.io/en/46.0.3/fernet/).

Next ONE full program/sources107 independent P1 recheck after scoped commit;
remaining108..114 blocked until usable closure. All eight fresh parts must use
one corrected committed HEAD/design/current93 audit. Ongoing necessary-review
budget covers114; same public/synthetic/provider/model/max/input1MB/output131072/
watchdog7200, no automatic retry/fallback. Only real four-part finalizers/pinned
parsers may publish; no human/live/service/timer/production/release approval.

## Original actual independent report

# Independent OpenCode Go program_design_review

PROGRAM_DESIGN_REVIEW: STOP_SHIP

{
  "verdict": "STOP_SHIP",
  "findings": [
    {
      "severity": "P1",
      "title": "OAuth token secret store is implemented by PAI-16 but designed nowhere in the programme",
      "issue": "PAI.md §3 places token storage 'outside these tables under a separately designed secret-store reference', yet no supplied document and no registered slice (PAI-00..31) contains that design; PAI-16 nonetheless lists src/prm/runtime/secret_store.py in allowed_files with only the phrase 'защищённое token storage, refresh/revoke/rotation'. Storage medium, encryption at rest and key bootstrap, per-connection layout, backup/restore behavior, PAI-24 secret-rotation interaction, deletion-on-revoke and the concurrent-refresh serialization mechanism are all unbound — in contrast to the explicit interfaces specified for jobs/effects/repositories. Concrete reachable case: PAI-16 lands a plaintext per-connection token file (or a PG side table outside the declared pa_* namespaces) with no at-rest保护; PAI",
      "fix": "Before PAI-16 implementation, publish a binding design (extend PAI-16 scope or a small ADR) fixing: storage medium/location, encryption at rest and key bootstrap/rotation, access control with owner/connection binding, behavior under PAI-24 backup/restore and PAI-25 export/import (tokens excluded or protected; re-auth after restore), deletion on revoke, and the concurrent-refresh serialization mechanism; register required security-path test nodes (no token material in logs/fixtures/artifacts/backups; at-rest protection; revoke deletes store entries)."
    },
    {
      "severity": "P1",
      "title": "Reconcile adapters have no authorized evidence source; ACT-02 provider-ID receipt is unachievable for the Graph mail-send timeout path",
      "issue": "PAI-20's deliverable is 'executor/reconcile adapters для выбранных mail и calendar операций' and ACT-02 requires receipts with provider IDs, but neither PAI-16's minimal-scope connection design nor PAI-20 binds the read scope needed to produce 'scoped_provider_evidence' for the PAI.md interface reconcile(attempt_ref, scoped_provider_evidence) -> resolved/unknown. Microsoft Graph sendMail (and send-draft) return 202 with no body — no provider object ID exists at dispatch — so for the designed 10 s transport-bound timeout case (ADR-013: only separately authorized reconciliation with provider evidence establishes success), the reconcile adapter must read e.g. sentItems, which PERM-01 will correctly deny under a write-only/minimal-scope grant. Reachable failing case: owner confirms a send, the",
      "fix": "Bind reconciliation evidence into the grant design: for each write-capable connection PAI-16 must either include the minimal provider read scope PAI-20's reconcile adapters need (sentItems/basic read for mail send; event read for calendar writes) with explicit CONNECT-03 UI disclosure, or adopt an ID-bearing flow (draft-create-then-send with recorded draft ID plus the read scope) and document the residual limitation. PAI-20 acceptance must add a timeout-then-authorized-reconciliation case proving the evidence path, and an unauthorized-evidence case that stays visibly unknown with no replay."
    },
    {
      "severity": "P2",
      "title": "Concurrent per-connection sync/cursor advancement is unspecified",
      "issue": "pa_connections cursors are authoritative delta state, but the design specifies fencing only for jobs (SKIP LOCKED claims, unique owner/schedule/revision/occurrence) and effects — nothing prevents or serializes two syncs of the same connection. Reachable case: a weekly-brief schedule and a mail watch (or two overlapping on-demand reads) create two distinct jobs that both run delta sync on the same mailbox on the two read workers; interleaved cursor writes and delta resets cause redundant provider calls, quota/429 churn, duplicate watch-evidence processing and interleaved partial derived-store reads visible to brief generation (source_records uniqueness suppresses duplicates but not the wasted work or inconsistent read snapshots). No existing guard addresses this: 'Background collection/d' ",
      "fix": "State a single-writer rule per connection (connection-row lock/lease or a coalesced sync job keyed by owner/connection) or monotonic CAS cursor writes with revalidation on conflict, and add a separate-process race test to tests/test_pai_graph_mail.py / tests/test_pai_schedule_runtime.py."
    },
    {
      "severity": "P2",
      "title": "PAI-18 calendar adapter lacks the minimization and throttling parity PAI-17 has for mail",
      "issue": "PAI-17 mandates minimal fields (no bodies/attachments by default) plus 429 and partial-page handling. PAI-18's scope (src/prm/schedule_connectors.py, transports/**) covers paging/sync, free/busy, recurrence/exceptions, source/local timezone and deleted/cancelled events but says nothing about a default minimal field set — calendar bodies, online-meeting blobs and third-party attendee PII are equally private under the SEC-03 posture and the brief/conflict use case needs only ids, subject, start/end/timezone, organizer, conflict-relevant attendees, recurrence and etag — nor about 429/partial-page handling for calendar batch sync.",
      "fix": "Add to PAI-18's scope: default minimal calendar fields (exclude bodies/attachments by default) with the same owner-visible minimal-scope escalation path as PAI-17, and explicit 429/partial-page handling (or state that the shared transports/** layer owns it and bind a test in tests/test_pai_schedule_runtime.py)."
    },
    {
      "severity": "P2",
      "title": "PAI-18 dependency registry inconsistent with its own Brief/watch wiring",
      "issue": "PAI-18's scope wires 'ответы, Brief и watch evidence', directly using PAI-14's brief source hooks and PAI-08's watch subscriptions, but its dependencies list only PAI-10 and PAI-16 — while PAI-17, which only feeds Brief, does declare PAI-14. The plan-checker-validated dependency graph therefore understates PAI-18's real prerequisites; strict dependency-order execution could start PAI-18 before its Brief/watch integration surfaces exist (phase ordering E-after-D mitigates this in practice).",
      "fix": "Add PAI-14 (and PAI-08 for watch evidence) to PAI-18's dependencies in PAI.design.json, or narrow PAI-18's scope to conversation/contacts and move the Brief/watch wiring to a slice that declares those dependencies."
    },
    {
      "severity": "P2",
      "title": "Phase-E binding gaps: no required security-path nodes for PAI-16/19/20 and SEC-04 setup display unbound",
      "issue": "PAI-09/10/11/13 each carry a REQUIRED security_path_acceptance entry with exact test nodes, but the phase's OAuth/secrets slice (PAI-16), academic-source injection slice (PAI-19, bound to SEC-01/SC13.2-09) and provider-write slice (PAI-20) have none — only generic per-requirement cases in the acceptance argv. Separately, SEC-04's 'retention terms shown at setup, not silently accepted' is bound only to PAI-21/25 (deletion/restore), not to PAI-16's connection-setup UI where source-derived persistence begins; the global 'owner must select windows before live persistence' gate covers live data, but the setup-time display obligation has no owning slice. Same class as the programme's own recorded open P2 for PAI-12.",
      "fix": "Register required exact security-path nodes: PAI-16 (secret material never in logs/fixtures/artifacts/backups; token-breadth vs app-filter display), PAI-19 (academic source injection cannot create authority or effects), PAI-20 (timeout -> unknown with no replay; unauthorized evidence stays unknown); and bind SEC-04's setup-time retention display to PAI-16's connection confirm flow in PAI.requirements.json."
    }
  ],
  "not_verified": [
    "Existence and behavior of all planned phase-E code and tests (src/prm/runtime/connections.py, src/prm/runtime/secret_store.py, src/prm/mail_connector.py, src/prm/schedule_connectors.py, src/prm/academic_inbox.py, src/prm/confirmed_actions,6",
    "Spec sections 0..7, 11, 12 and 14 and the full §13.1 thresholds were not supplied; full-product coverage judged only on §8/§9/§10/§13.2/§15 bindings for PAI-16..20",
    "docs/PA_IMPLEMENTATION_TASKS.md, docs/design/PA.design.json, docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md, ADR-014/015, docs/verification/** and PAI-00-file-manifest.json contents (referenced, not supplied)",
    "Microsoft Graph, Gmail and Canvas API semantics (sendMail/send-draft response shape and idempotency, delta-token lifetimes, ETag optimistic concurrency, free/busy and minimal scope sets, institutional Canvas permission) — deferred by design",
    "Pending owner decisions this phase depends on: provider selection (Graph assumed as default vs Gmail), exact minimal scope sets, retention windows, live account grants and Canvas institutional permission",
    "Prior-phase implementations PAI-02..15 (durable policy/budget/jobs/ingress/delivery/chat/brief runtime) that phase E builds on — owned by other review groups",
    "Fake-OAuth-server fidelity to a real callback/client, concurrent token-refresh serialization mechanism, and provider-side revocation detection handling",
    "Revocation/deletion cascade into PAI-17/18/19 derived stores, tombstone replay on restore, and backup treatment of connection state and tokens (PAI-21/24/25 interfaces — phase F, unreviewed here)"
  ],
  "summary": "Phase-E (PAI-16..20) review: the slices bind §8 connections (OAuth, Graph mail/calendar/contacts, Canvas-gated academic inbox) and §9 actions into the durable PA runtime with the right overall shape — guard-before-HTTP inside adapters, metadata-only mail reads by default with explicit owner-visible scope escalation, durable proposals/single-use confirmations through one serial effect executor with ADR-013 prepared/unknown fences, provider-specific idempotency semantics, and consistent requirement/scenario matrix bindings. Two P1 design gaps block: (1) the OAuth token secret store PAI-16 will implement is designed nowhere in the packet or registry — mechanism, at-rest protection, key/rotation, backup/restore and deletion semantics are unbound, while every other security-critical component has explicit interfaces; (2) PAI-20's reconcile adapters have no authorized evidence source — no slice binds the reconciliation read scope (or an ID-bearing draft-then-send flow) into PAI-16's minimal-scope grant set, so the Graph sendMail timeout path can never produce ACT-02's provider-ID receipt and degrades to permanent unknown. Secondary gaps: no serialization rule for concurrent same-connection syncs/cursor advancement; PAI-18 lacks mail-parity field minimization and 429/partial-page handling; PAI-18's declared dependencies omit PAI-14/PAI-08 that its own Brief/watch wiring requires; and the phase lacks the required security-path test nodes and SEC-04 setup-display binding that comparable high-risk slices carry. STOP_SHIP until the two P1s are resolved by binding design amendments; no"
}
