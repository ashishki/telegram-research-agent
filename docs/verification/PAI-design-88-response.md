# Product phase88 STOP — concrete P1 response and full-packet tooling rescope

2026-10-09. Actual product/design part88 reviewed84155e2;472.356s,
observed glm-5.3, requested max/observed effort unknown; usage41015/23807/64822.
STOP_SHIP with2 P1/4 P2. Receipt PAI-review-continuation-88.json preserves
command/result/report/input hashes. Other product parts87/89/90 were ADVISORY;
old full program record81/85/83/86 is preserved at84155e2, not current approval.

P1 cross-store order: ADR-013 now explicitly acquires PostgreSQL authority rows
before retained SQLite locked-send and holds them through its entire transaction
and bounded sender, SQLite closes before PG release. Revoke wins => zero sender;
in-flight dispatch wins => revoke ACK waits. Two actual PostgreSQL/SQLite race
cases prove both outcomes; runtime authority implementation was not weakened.

P1 matrix omissions: SEC-01 binds PAI-11/13, SEC-02 binds PAI-10, SC13.2-09 binds
all three. Exact REQUIRED security_path_acceptance nodes are registered before
test implementation in each slice/task/matrix, using existing files already in
pai-complete/project verification. Real SQLite FTS->source-bound archive HTTP,
durable gather/synthesis with a real copied SQLite archive, and mixed-provider
private-data refusal are exercised. SQL grant/proposal/effect snapshots remain
unchanged despite hostile source instructions; unpermitted provider gets zero
HTTP, separately permitted user text can proceed without private history. Named
SEC-01/SEC-02 and SC13.2-09 execute the new behaviours. All69 IDs/ten scenarios
remain unique; new matrix SHA is recorded in PAI.md. No fixture acceptance is
promoted to governed human or independent role closure.

P2 quiet hours and PG->SQLite order/busy timeout made explicit; composition.py
owned by09/15;12 local acceptance uses fakes/existing credential patterns with
no assumed private-repo/OAuth access. Foreground durable reply fences retained;
we did not adopt the suggested reduction of durability to meet unmeasured SLOs.

Initial new test run: three tests passed before research fixture stalled in
SQLite backup with its own uncommitted source writes. SIGINT did not unwind that
native loop; own pytest terminated SIGTERM(exit143), its sole remaining synthetic
cluster identified by startup window/PID/pa-synthetic marker and stopped. First
cleanup assertion expected2 clusters and observed1, aborting before mutation;
module fixtures had already closed others. Only the exact own process/cluster
was stopped. Initial log preserved; source conn.commit before backup corrected
fixture ordering, no assertion/guard weakening. Final targeted8 passed39.54s.

Design prepare-only exceeded the old200000-byte input bound (exit2, no key/HTTP).
Under the owner's maximum-resource directive, engineering capacity is1MB for the
SAME fixed public/synthetic refs; separate input authority required before keys
above200000. No truncation/private-source expansion. Old6000-token analysis hint
removed; minLength declares existing nonempty summary/finding consumer checks;
no invalid empty summary promoted. Cadence distinguishes7 engineering vs4 design
review groups; PROJECT_BRIEF projection now honestly states omitted text/hash.
All audited-source changes require actual new tooling91, then product92 P1
recheck and a complete fresh role set93..99 at one unchanged HEAD/design.90 calls
consumed;99 allocated under ongoing authority; no model fallback/automatic retry.

Final checks and log hashes follow in PAI-validation-20261009-88.json:30 plan/
bridge tests,157 tooling tests,62 scoped strict acceptance cases/zero skips,
pin/32-packet/69-ID/ten-scenario structure. No full historical pytest; no current
full-spec runtime tier claimed from these scoped cases. All live/formal gates open.

## Preserved actual independent part88 report

# Independent OpenCode Go product_design_review

PRODUCT_DESIGN_REVIEW: STOP_SHIP

{
  "verdict": "STOP_SHIP",
  "findings": [
    {
      "severity": "P1",
      "title": "PAI-09: cross-store pause/revoke/send ordering between retained SQLite locked-send and PostgreSQL authority is unspecified",
      "issue": "PAI-09 wires durable attempts/receipts to foreground/background delivery and mandates the PAI-01 pause/revoke/send ordering, while simultaneously retaining the watch store's tested locked-send contract ('Do not take `sender` out of the SQLite transaction without equivalent proven behavior'). ADR-013's final-effect contract holds only PostgreSQL policy/consent/subscription/reservation locks through the bounded transport call; it never defines how the retained SQLite send transaction is nested under PostgreSQL revocation authority. Reachable failing case: owner revokes the subscription/grant in PostgreSQL after the pre-send check but while the delivery worker is inside the SQLite locked-send; the Telegram message is delivered despite revocation, violating WATCH-03 ('отзыв прав после постанов",
      "fix": "Specify in ADR-013/PAI-09 that PostgreSQL authority locks are acquired and held across the entire SQLite locked-send, or migrate the send into the PostgreSQL prepared-attempt contract after proving equivalent duplicate-send prevention; add a revoke-wins-lock vs in-flight-send race case to PAI-09 acceptance (tests/test_pai_delivery.py)."
    },
    {
      "severity": "P1",
      "title": "Coverage matrix omits this phase's implementing slices for SEC-01 and SEC-02",
      "issue": "PAI.requirements.json binds SEC-01 (prompt injection; 'letters, pages, documents, comments and posts are data, not instructions') to PAI-12/17/19/21/22/26 and SEC-02 (fallback provider only for permitted data classes) to PAI-03/16/22 — but the paths built in this phase are absent: archive post excerpts/tool results feed model synthesis in PAI-11 (src/prm/archive_synthesis_transport.py, src/prm/synthesis.py) and PAI-13, and the privacy-safe chat fallback is implemented in PAI-10's model route (src/prm/runtime/composition.py). Since PAI-26 completion requires actual wired evidence per mapped behavior and counts/identities prevent omissions, these untrusted-content and fallback paths never receive a named acceptance case anywhere. Reachable cases: a Telegram channel post retrieved as top FTS证",
      "fix": "Add PAI-11 and PAI-13 to SEC-01 and SC13.2-09 slice bindings with named archive/tool-result injection test nodes; add PAI-10 to SEC-02 with a fallback-refusal-for-unpermitted-data-class case; re-hash the matrix."
    },
    {
      "severity": "P2",
      "title": "Quiet-hours/DST enforcement at delivery time not bound",
      "issue": "PAI-08 computes quiet hours/DST at schedule time; PAI-09's pre-send guard set names only pause/revoke ordering. A job enqueued before quiet hours begin but executed during them (queue delay, lease recovery, catch-up) delivers a non-urgent digest inside quiet hours, violating WATCH-02 ('обычная новость не перебивает тихие часы').",
      "fix": "Bind a delivery-time quiet-hours/time-window recheck into PAI-09's pre-send guard set (or PAI-08's delivery step) and add a delayed-job-into-quiet-hours case to PAI-08/09 acceptance."
    },
    {
      "severity": "P2",
      "title": "Composition-root file ownership gap for PAI-09 and PAI-15",
      "issue": "Every other runtime slice in this phase (PAI-07/08/10/11/12/13/14) lists src/prm/runtime/composition.py in allowed_files; PAI-09 (effect executor and delivery-contract wiring) and PAI-15 (reader endpoint) do not, and PAI-26 may only edit tests. If effect-executor/reader registration belongs to the single composition root, no slice in the registry can perform that edit, risking unfinished vertical wiring despite 'No skeleton closure'. Concrete case: PAI-09 completes all allowed-file edits but the effect executor is never instantiated in the runtime; background watch attempts never dispatch and no later slice (PAI-26) can repair it within its file budget.",
      "fix": "Add src/prm/runtime/composition.py to PAI-09/PAI-15 allowed_files, or explicitly assign the registration edit to a named owning slice in the registry."
    },
    {
      "severity": "P2",
      "title": "PAI-12 credential boundary before the secret store is unspecified",
      "issue": "PAI-12 implements web-search and GitHub read adapters before PAI-16's secret store/OAuth exists, while PAI.md §5 forbids creating a second provider secret path. Without a stated boundary, implementers may add ad-hoc token handling in src/prm/public_web.py or src/prm/runtime/transports/** (parallel secret path) or silently assume authenticated private-repo reads are available.",
      "fix": "State in PAI-12's scope that it uses only the existing env-var/documented-secret pattern or unauthenticated public reads, with no new token storage; defer authenticated/private-repo access to PAI-16+."
    },
    {
      "severity": "P2",
      "title": "Foreground answers: durable prepared effect vs permission-checked send ambiguity",
      "issue": "PAI-09's outcome routes 'ответ' through the same final-permission contract as Watch/Act. If every conversational reply becomes a durable two-phase prepared effect, it conflicts with the stated intake p95 ≤2 s / Chat ≤10 s targets and the burst load profile; if it is only a final permission check plus post-transport receipt, that must be stated so per-message durability/reconciliation is not implied.",
      "fix": "Specify that conversation replies undergo the final permission/transport-bound check and receipt but are not per-message durable prepared effects requiring reconciliation; reserve prepared attempts for background delivery and confirmed actions."
    }
  ],
  "not_verified": [
    "Actual implementation and runtime evidence for PAI-07..PAI-15 (all slices 'planned'; no code or test results supplied)",
    "docs/PA_IMPLEMENTATION_TASKS.md PA-00..18 requirement definitions and the PA-09 material-change/quiet-hours/DST domain rules referenced by PAI-08 (source document not supplied)",
    "Spec sections 0, 2, 8, 11, 12, 14 (declared phase set supplies only sections 1, 3, 4, 5, 6, 7, 9, 10, 13, 15)",
    "Existence and content of planned test files (tests/test_pai_ingress_jobs.py, test_pai_scheduler.py, test_pai_delivery.py, test_pai_chat_runtime.py, test_pai_archive_search.py, test_pai_web_github.py, test_pai_deep_research.py, test_pai_bri-",
    "Runtime snapshot caf97a7 (320 synthetic cases / 69 IDs / 10 scenarios): dated evidence, not verified as current",
    "Requirements-matrix SHA256 32d8dbbc… lossless reproduction and symbol resolution beyond the supplied strings",
    "Actual provider/API documentation checks (search, GitHub, Graph) deferred to implementation",
    "Performance targets (intake p95 ≤2 s, Chat ≤10 s, Search ≤45 s): proposed, unmeasured — no load data supplied for this phase's paths"
  ],
  "summary": "PAI-07..PAI-15 is largely coherent as a design: dependency ordering is acyclic and consistent, each slice's acceptance argv exactly matches its PAI.requirements.json test_files, durable job/scheduler/effect contracts and unknown-effect handling follow ADR-013, ingress returns results by request ID rather than last_topic, scheduler catch-up coalescing prevents notification avalanches, and PAI-15 binds real-render checks per EVAL-03. Two P1 defects block this phase: (1) PAI-09 leaves the pause/revoke/send ordering between the retained SQLite locked-send and PostgreSQL revocation authority unspecified — a reachable revoke-during-send race violating WATCH-03/UX-05 that the PostgreSQL-only ADR-013 guard set does not cover; (2) the binding matrix omits this phase's implementing slices for SEC-01 (archive/tool-result prompt injection: PAI-11/PAI-13 absent) and SEC-02 (chat fallback data-class enforcement: PAI-10 absent), so mandatory permission/privacy behaviors on paths built in this phase never acquire named acceptance obligations. P2 items: quiet-hours recheck at delivery time, composition-root file ownership for PAI-09/PAI-15, the pre-secret-store credential boundary for PAI-12, and the foreground-answer effect-vs-check ambiguity. These are design/registry defects in a planned phase; no implementation, live, or deployment authority is granted or assessed here."
}
