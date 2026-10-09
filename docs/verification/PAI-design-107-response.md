# Actual107 STOP — durable academic-state ownership response

2026-10-09. Actual program/sources107 atfa8aade:STOP_SHIP1P1/5P2,
767.099s, observed glm-5.3/requested max/observed effort unknown,
usage41664/58101/99765. Genuine immutable command/result/report/input/log binding:
PAI-review-continuation-107.json. Its substantive summary independently confirms
review99/105 contracts (vault/refresh/revoke/restore exclusion,202≠completion,
separate evidence-read consent/no-match≠absence/no replay) while a NEW P1 blocks
this phase. Original STOP remains unchanged; no implementer acceptance.

P1 academic-home ownership: PAI-19 now owns the early shared memory-core bootstrap
and actual runtime/academic.py, memory.py, deletion.py, setup.py, migration.py and
storage/** paths. Stage/academic state uses existing PAI-02 pa_runtime memory
object versions/heads with owner/digest/version CAS; explicit stage confirmation
uses the existing shared pa_memory preview/one-use/tombstone primitives. Local/
owner-reported/provider-confirmed completion have distinct provenance semantics,
never inferred from a mail subject or dialogue context. No duplicate state engine
or schema was created. PAI-21 now explicitly depends on19 and expands the SAME
library; task pack/formal tasks/registry/matrix/table map updated consistently.
PAI-19 required restart test registered before implementation.

New real-PG test constructs fresh JobQueue/AcademicRuntime without conversation
state, confirms stage explicitly, persists local completion, refuses a foreign
actor and consumed preview, and observes zero source HTTP/submission calls. This
proves currently implemented stage/local-done persistence, not the entire future
completion-provenance/Canvas/live profile contract. No runtime source changed.
Other current runtime hashes retain the prior87/163-case evidence; no broad rerun.

P2 scheduler allegation is not reproduced: actual git show fa8aade already lists
src/prm/runtime/scheduler.py in PAI-19 allowed_files, matching expected_paths.
Original allegation/report preserved; no checker weakened or actual STOP
overridden. Other P2s (callback/verifier/refresh placement, provider drafts and
calendar update/cancel evidence, exact mail/Canvas injection nodes, same-connection
cursor concurrency) remain in the original report for later scoped disposition.

Verified21 strict scoped cases31.84s/zero skips or failures;48 plan/bridge2.55s;
pin/32 packets/69 exact IDs/ten scenarios/diff checks pass. Commands/log/source
hashes and committed scheduler probe: PAI-validation-20261009-107.json.
Actual current-tooling93 consumer passes unchanged critical hashes. No current
full-spec runtime, independent implementation-source, human design, institution,
private-provider, production/service/timer or release acceptance claimed.

Next ONE actual full sources108 recheck after scoped commit. Remaining109..115
stay blocked until usable no-P0/P1 closure. All eight fresh parts require SAME
corrected committed HEAD/design/current93 gate; ongoing necessary-review authority
covers115, same public/synthetic/provider/model/max/input1MB/output131072/7200,
no automatic retry/fallback. Real four-part finalizers and pinned consumers only.

## Original actual independent report

# Independent OpenCode Go program_design_review

PROGRAM_DESIGN_REVIEW: STOP_SHIP

{
  "verdict": "STOP_SHIP",
  "findings": [
    {
      "severity": "P1",
      "title": "PAI-19 has no owned durable storage for the ACADEMIC-02 stage profile and ACADEMIC-05 local completion states its bound acceptance and the (",
      "issue": "In docs/design/PAI.design.json slice PAI-19, allowed_files resolves to src/prm/academic_inbox.py, src/prm/runtime/transports/**, src/prm/application.py, src/prm/runtime/composition.py, src/prm/watch_jobs.py plus docs/tests/fixtures/tools; src/prm/storage/** and src/prm/runtime/migration.py are excluded, and docs/design/PAI.requirements.json expected_paths for PAI-19 likewise contains no storage path. No dependency (PAI-08/14/17/18) supplies a profile/preferences repository; the natural home per PAI.md §3 (pa_memory facts/preferences) is wired only in PAI-21, which runs later and does not list ACADEMIC-02/05. Yet PAI.requirements.json binds ACADEMIC-02 (explicitly selected stage, never auto-derived) and ACADEMIC-05 (distinct 'готово локально' / 'пользователь сообщил' / 'источник подтвердил'",
      "fix": "Before PAI-19 implementation, assign an explicit durable home for the stage profile and per-item local completion states: either add src/prm/storage/** plus schema/migration ownership and a named repository contract to PAI-19's allowed_files/expected_interfaces, or rebind ACADEMIC-02/05 acceptance to the slice owning pa_memory and declare the corresponding dependency. Update PAI.design.json and PAI.requirements.json consistently and re-run the structural plan check."
    },
    {
      "severity": "P2",
      "title": "PAI-19 registry/matrix path inconsistency: src/prm/runtime/scheduler.py is an expected path in PAI.requirements.json but absent from PAI-16…",
      "issue": "PAI.requirements.json slice_bindings.PAI-19.expected_paths resolves to [src/prm/academic_inbox.py, src/prm/runtime/transports/**, src/prm/application.py, src/prm/runtime/composition.py, src/prm/runtime/scheduler.py, src/prm/watch_jobs.py] (symbol $35, cross-checked against PAI-08's binding), while PAI.design.json PAI-19 allowed_files contains transports ($35), application ($19), composition ($30) and watch_jobs ($39) but not $34 (src/prm/runtime/scheduler.py). An implementer or checker following one document diverges from the other (manifest violation vs. missing reminder wiring coverage). Slices PAI-16, PAI-17, PAI-18 and PAI-20 were checked and are consistent.",
      "fix": "Reconcile both registries for PAI-19 (add scheduler.py to allowed_files if academic reminder wiring requires it, otherwise drop it from expected_paths) and make tools/check_pai_plan.py verify expected_paths ⊆ allowed_files per slice."
    },
    {
      "severity": "P2",
      "title": "PAI-16 OAuth callback transport, PKCE verifier persistence and token-refresh placement vs. the final effect transaction are unspecified",
      "issue": "PAI-16's user-visible outcome requires completing an interactive provider consent, but no document states which process/endpoint serves the OAuth redirect (loopback listener in the application/executor process vs. reader endpoint vs. bot deep-link) — while PAI.md §3 bars the render process from network/provider secrets — nor where the PKCE code_verifier and pending-flow state persist across the round trip (PostgreSQL pending-connection row vs. in-memory, restart behavior). Related: ADR-013 permits 'one bounded transport call' under the final effect locks with a 15 s idle bound, so connection/token refresh must complete before entering the PAI-20 dispatch transaction, but that ordering is only implicit; a refresh inside the locked transaction can abort after prepared (safe by the unknown-fE",
      "fix": "Pin in PAI-16/ADR-013: callback server ownership (single loopback listener in the application or effect-executor process, never the render process), a persisted pending-flow row (state, PKCE verifier, expiry) in PostgreSQL, and the explicit rule that token refresh finishes before acquiring the final effect transaction locks."
    },
    {
      "severity": "P2",
      "title": "PAI-20 reconciliation evidence paths unspecified for provider drafts and calendar update/cancel",
      "issue": "Mail send has an exact SentItems attempt+digest evidence binding with three required nodes, but (a) provider draft creation — explicitly a write in PAI-20's scope ('Provider draft тоже write') — has no stated ACK-loss/no-match evidence path or required fixture, and (b) calendar update/cancel are declared 'unresolved until stronger evidence' with no attribution mechanism (e.g., Graph event extended properties/open extensions carrying attempt+digest), making those unknowns practically unsettleable except by owner write-off. Both stay conservative (no replay/alias/reset), so this is not a correctness breach, but the owner-visible consequences and fixture coverage are missing; calendar endpoints are also absent from ADR-013's checked-sources list.",
      "fix": "Specify per-operation reconciliation contracts: draft lookup by attempt/digest header where the official API supports it (with a required fixture), and calendar attribution via extended properties if API-verified — otherwise explicitly document permanent-unknown plus write-off UX — and add the corresponding fixtures to PAI-20's required list."
    },
    {
      "severity": "P2",
      "title": "No dedicated required security-path nodes for mail and Canvas content injection (PAI-17/PAI-19)",
      "issue": "SEC-01 and SC13.2-09 map mail and Canvas content as untrusted inputs (PAI-17 and PAI-19 appear in both slice lists), but unlike archive (PAI-11), tool results (PAI-13), chat fallback (PAI-10), connections (PAI-16) and actions (PAI-20), neither slice has a REQUIRED security-path node; injection safety for Graph subjects/senders and Canvas announcements — attacker-influencable text flowing into synthesis, Brief and summaries — is currently bound only via general acceptance and the PAI-26 scenario.",
      "fix": "Add required security-path nodes mirroring the PAI-11/13 pattern (e.g., tests/test_pai_graph_mail.py::<node>: retrieved mail content cannot create authority/grants/effects; tests/test_pai_academic_runtime.py::<node>: Canvas/mail content cannot create authority/effects) and bind them in PAI.requirements.json SEC-01 security_test_nodes."
    },
    {
      "severity": "P2",
      "title": "Concurrent syncs of the same connection are not serialized (PAI-17/PAI-18)",
      "issue": "Job uniqueness is per job identity (PAI.md §3/§4), so a manual sync request and a scheduled occurrence for the same connection can run concurrently in two workers, both consuming the same delta cursor: duplicate provider pages (429/rate-limit pressure) and last-writer-wins cursor updates that can regress the cursor and force refetch. Correctness is preserved only if source_records writes are idempotent upserts per (connection, provider object ID) including replayed deletions — implied by ARCH-02 uniqueness but not stated as an acceptance case for this path; no cursor CAS or per-connection lease appears in the pa_connections constraints ('account/provider IDs scoped; tombstones and partial coverage').",
      "fix": "Add a per-connection cursor lease/CAS (or coalesce concurrent sync jobs per connection resource) to the connector repository contract, and add an explicit PAI-17/18 acceptance case for idempotent source-record upserts and tombstoned deletions under concurrent/refetching syncs."
    }
  ],
  "not_verified": [
    "docs/PA_IMPLEMENTATION_TASKS.md per-card scope/acceptance anchors for PAI-16..20 and the PA-02/PA-10/PA-11/PA-12/PA-13/PA-17 ID-to-spec-requirement correspondence (referenced, document not supplied).",
    "docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md — ACADEMIC-01 authority for the PAI-19 module (categories, authority rules, Nebula handling, minimal Canvas fields); not supplied, PAI-19's compliance unverified.",
    "Actual Microsoft Graph semantics asserted in ADR-013 review105 (sendMail custom x-headers persisting into SentItems and returned via list/get message $select=internetMessageHeaders; calendar transactionId/extended-property attribution; free",
    "Canvas API endpoints/scopes and institutional permission status (spec §15); PAI-19 offline-adapter parity with the real API unknown.",
    "Existence and content of all planned tests and REQUIRED nodes for this phase (tests/test_pai_connections.py, test_pai_graph_mail.py, test_pai_schedule_runtime.py, test_pai_academic_runtime.py, test_pai_action_runtime.py and the five named",
    "Whether tools/check_pai_plan.py cross-checks expected_paths against allowed_files (would it catch the PAI-19 scheduler.py mismatch); tooling sources not supplied.",
    "Current independent tooling-audit gate state (native93 ADVISORY, REVIEW_POLICY GLM-5.3 binding, result/report hashes) — recorded claims only, not re-verified here.",
    "Dated runtime evidence (snapshot caf97a7: 320 synthetic cases / 69 IDs / 10 scenarios) and PAI-00 reconciliation/manifest records — historical, not current verification; docs/verification/PAI-00-file-manifest.json and PAI-progress.md not"
  ],
  "summary": "Phase E (PAI-16..20, sources/actions) is largely sound at design depth: ADR-013's review99/105 contracts are strong and correctly bound into these slices (serialized same-connection refresh before HTTP, at-rest vault binding with revoke deletion and export/restore exclusion, Graph 202 ≠ completed effect, no-match ≠ absence, reconciliation read consent denied before HTTP, mismatched digest keeps unknown, no replay/alias/reset of unknown attempts, provider-token-width vs application-filter disclosure), slice dependencies and per-slice verification argv are internally consistent for PAI-16/17/18/20, and all live/provider/production authority is properly deferred to later gates. One P1 blocker stops this phase: PAI-19 must durably hold the ACADEMIC-02 stage profile and ACADEMIC-05 local completion states — the background weekly Brief and reminders need them without a conversation — but its file manifest excludes every durable-state path (src/prm/storage/**, runtime/migration.py) and the pa_memory preference repository only arrives in PAI-21, which does not own those requirements, so the bound acceptance cases are unimplementable as specified without breaching the manifest. Five P2s address the PAI-19 scheduler.py registry/matrix mismatch, unspecified PAI-16 OAuth callback/verifier/refresh placement, missing PAI-20 draft and calendar update/cancel reconciliation evidence paths, absent dedicated mail/Canvas injection nodes, and unserialized concurrent same-connection syncs. This phase alone cannot approve the full design; the foundation (00..06), product (07..15) and completeness"
}
