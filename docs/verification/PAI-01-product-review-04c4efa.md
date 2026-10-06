# Independent OpenCode Go product_design_review

PRODUCT_DESIGN_REVIEW: STOP_SHIP

{
  "verdict": "STOP_SHIP",
  "findings": [
    {
      "severity": "P1",
      "title": "Design-only slice grants unverified edit access to production runtime code and to its own gate",
      "issue": "PAI-01 declares 'No application code or DB migration is implemented by this packet' and its rollback claims production is unchanged, yet the registry allows changes to src/prm/capabilities.py, src/prm/watch_jobs.py and src/prm/confirmed_actions.py (the live policy/watch/action contracts) plus tools/check_pai_plan.py, the very checker that validates the plan. The card's only verification is planning_structure, so any edit to those runtime modules would land with no behavioral test gate, and the card can modify the check that certifies itself. This contradicts ASSISTANT_BOUNDARIES/IMPLEMENTATION_CONTRACT expectations that changed runtime surfaces get targeted tests and independent risk review.",
      "fix": "Remove src/prm/capabilities.py, src/prm/watch_jobs.py, src/prm/confirmed_actions.py from PAI-01 allowed_files (defer to PAI-03/04/06 where tests exist), or add an explicit required test invocation covering every listed source file and forbid editing tools/check_pai_plan.py inside the card it validates (route checker changes to PAI-00 or a separate reviewed change)."
    },
    {
      "severity": "P1",
      "title": "Spec-level requirement and scenario traceability is asserted, not demonstrated in the supplied registry",
      "issue": "PAI.design.json maps slices only to coarse PA-00..PA-18 stage IDs. The full spec's binding requirement IDs (UX-01..05, CHAT-01/02, SEARCH-01..04, BRIEF-01..07, WATCH-01..04, ACT-01..03, MEM-01..03, CONNECT-01..03, EVIDENCE-01..03, RAG-01, VISUAL-01..04, SEC-01..04, PERM-01, ACADEMIC-01..05, MEDIA-01..03, COST-01/02, MODEL-01/02, OPS-01/02, ARCH-01/02, EVAL-01..03, MIGRATION-01, DONE-01) and the mandatory user scenarios of spec 13.2 have no per-slice -> path/test/review mapping anywhere in the packet. PAI.md delegates this to 'PA-Refs in the task pack', which is not supplied and is therefore unverifiable. Concrete risks: ambiguous 'yes' binding (UX-03), delivery-failure honesty (UX-05), VISUAL-01..04 render budgets/Cyrillic/dark theme, prompt-injection per source type and secrets-in-errors (SEC-01..03), and claim-to-evidence thresholds (EVAL-01) can be silently dropped while every PA-xx mapping still looks complete. The spec and brief make the requirement-to-path/test/review/user-evidence matrix the product proof.",
      "fix": "Add an explicit fine-grained spec-ID -> slice -> verification -> review mapping (extend expected_interfaces or a PAI requirement-coverage table) covering every spec requirement ID and 13.2 scenario, or supply the referenced task-pack PA-Refs as reviewable evidence before design approval. Make PAI-26 acceptance enumerate the exact scenario list rather than the generic phrase 'E2E из спецификации'."
    },
    {
      "severity": "P2",
      "title": "Lifecycle of unresolved unknown reservations against budgets is undefined",
      "issue": "PAI-03 and ADR-013 require that unknown spend is retained and that a crashed worker's reservation survives until conservative settlement, and that unresolved prepared effects block re-dispatch and may stay unknown forever when provider evidence is unavailable. The design never states what happens to the reserved request/job/day/month units in that permanent-unknown case: whether they stay locked indefinitely (denying all further work), are released after an owner decision, are written off, or how the owner sees and resolves the blockage. Under the frozen load profile (20 concurrent reservations competing for 10 units) this can exhaust the budget silently.",
      "fix": "Specify budget accounting for unresolved reservations: owner-visible 'unknown spend' state, an explicit owner decision path to write off or continue, and the resulting cap behavior, plus a test where a permanently unknown attempt consumes reservation units and the operator can see and resolve it."
    },
    {
      "severity": "P2",
      "title": "Deletion/revocation propagation across the two stores is not specified",
      "issue": "PostgreSQL owns PA authority/derived state while SQLite keeps canonical archive plus derived index state. The design specifies tombstone replay on restore and derived-deletion queueing, but not how a deletion/revoke is applied consistently to derived rows living in the SQLite-side derived stores, what happens if one store is unreachable during propagation, or how partial deletion is reported to the owner. Without this, 'удалённое не возвращается из кэша или отложенной job' (PAI-21 outcome) is not enforceable end to end.",
      "fix": "Define per-store deletion steps, idempotent tombstones in both stores, retry/failure semantics and a truthful owner-visible partial-deletion status; add a test that deletes/revokes while one store is unavailable and proves no stale derived content is served after recovery."
    },
    {
      "severity": "P2",
      "title": "No consistency gate between PAI.md, PAI.design.json and ADR-013",
      "issue": "The only required check for this card validates plan structure, not agreement between the prose design, the machine registry and the proposed ADR. Referenced test files (tests/test_pai_*), fixtures, allowed_files/forbidden_files conflicts (e.g. PAI-24 lists systemd/** as both), dependency ordering, change budgets and the 'PA requirement coverage' strings are not checked for existence or mutual consistency, so drift can be approved as-is.",
      "fix": "Extend or add a checker (reviewed separately from the design card) that verifies referenced files/tests exist, allowed/forbidden overlap, dependency completeness, and that every declared expected_interface maps to a slice and a verification command."
    }
  ],
  "not_verified": [
    "No executed evidence supplied for the required planning_structure gate (tools/check_pai_plan.py run and exit code at the reviewed SHA).",
    "No hash-bound human design approval record exists (approval_policy=human_required; ADR-013 status is proposed; no approval fields may be manufactured).",
    "The companion task pack with PA-Refs (docs/tasks.md, docs/PA_IMPLEMENTATION_TASKS.md) is not in the packet, so claimed requirement coverage cannot be checked.",
    "No measurement evidence for lease/fencing, SKIP LOCKED contention, lock-wait/pause latency, DB-disconnect-during-send, prepared-attempt crash, reservation settlement, stale-lease and revoke/send races; these are planned for PAI-02/26 and remain unrun.",
    "Driver/PostgreSQL version pinning and official-documentation checks are deferred to PAI-02; no compatibility evidence exists.",
    "Behavior of SQLite archive reference revalidation and derived-index consistency under concurrent deletion/corruption is not demonstrated.",
    "Current contents and contracts of src/prm/capabilities.py, src/prm/watch_jobs.py, src/prm/confirmed_actions.py were not reviewed; the described in-memory receipt store and partial policy behavior are unverified against HEAD.",
    "Baseline regression state at HEAD (PAI-00 focused-prm result and reproduction of the historical failing test) is referenced but not evidenced in this packet.",
    "Provider idempotency/reconciliation semantics for mail/calendar effects, secret-store design and live retention/cost/schedule parameters remain owner decisions and unverified.",
    "No real rendered Telegram/HTML/PDF inspection, provider integration, or owner usefulness evidence exists; these are correctly deferred to PAI-15/26..29."
  ],
  "summary": "The PAI-01 design is genuinely durable-aware: two-phase prepared attempts, narrow row locking with a bounded final guard, fence tokens for DB writes only, unknown-effect blocking, transactional scheduler enqueue, test-DB isolation, single-writer cutover and restore/tombstone rules are stated with the right failure semantics, and ADR-013 honestly retains strict revoke/send ordering and refuses blind takeover of external attempts. However, the slice as registered contradicts its own 'no code' claim by allowing edits to live policy/watch/action modules and to the plan checker with only a structure check as verification, and the registry traces requirements only to coarse PA stage IDs while the spec's binding requirement IDs and mandatory user scenarios have no demonstrated mapping in the supplied packet (delegated to an unsupplied task pack). Budget behavior for permanently unknown reservations and cross-store deletion propagation are also unspecified. Because a P1 scope/verification hole and a P1 traceability gap are present, this packet cannot pass product design review as-is; resolve both, then re-review before the hash-bound human design approval."
}
