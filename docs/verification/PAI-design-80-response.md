# Program foundation80 — STOP preserved; design-only response

2026-10-09. Actual GLM-5.3 native phase80 reviewed88da0f5, exit1,
512.188s, requested max/observed effort unknown, usage35439 prompt/29341 completion/
64780 total. One P1/four P2; exact source/command/report/input/result provenance in
PAI-review-continuation-80.json. No complete programme record or human approval.

P1: PAI.md's gate wording named retired Mimo. Changed to the current owner-selected
reviewer via REVIEW_POLICY; actual native79 ADVISORY/accepted consumer/hash/identity
bindings are supplied in PAI.md and always-reviewed ADR-013. The alleged missing
current audit is contradicted by phase80's own genuine tooling_audit_ref, but the
stale normative wording was real. No implementer closure; fresh phase81 required.
Audited tooling/REVIEW_POLICY unchanged; real require_tooling_audit still accepts79.

P2 bridge/memory omission: original88da0f5 PAI-00 reconciliation_regression argv
already names both tests/test_playbook_bridge.py and tests/test_memory_research.py.
Exact existing argv made explicit; registry/checker/tests unchanged. P2 budget
lifecycle: scheduler enqueue is intent only; reserve per bounded external step;
proven-unused reservation may settle zero, prepared/unknown/previous billable usage
cannot refund from job status. P2 cancellation: accurate terminal/reconciliation/
unavailable outcomes specified. P2 sequencing: formal approval gates acceptance;
ADR-014/015 separately authorize the local synthetic pass before tests/reviews.
These are proposed design clarifications, not evidence of new runtime acceptance.

Initial four planning checks failed the pinned20000-character compact-map limit
(22971-byte first draft;20616/20122/20038-character iterations). Full evidence/
reservation details moved to always-reviewed ADR-013 and equivalent wording
compressed;19966-character final map. Requirements preserved, no pin/checker
weakening. Then git diff --check caught a trailing blank line; corrected.

Final planning command .venv-pai/bin/python tools/check_pai_plan.py passed all32
packets/69 IDs/ten scenarios; conditional30/31 files still planned/missing.
Scoped command:
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_pai_plan.py tests/test_playbook_bridge.py
30 passed2.63s; log .playbook-artifacts/pai-validation-20261009-maximum/design80-fix.log
Log SHA256: 4c32ea71405a97f66890ec9352d946973c4ba5055e6734f7251e2d7b48724a1d.
Fresh prepare-only foundation packet: 163629 bytes; input SHA256 1455fca435028f310c73deb2ea3a34c98f5dc178e90f5f299ae5a5472960e69b; planning gate clear, zero provider calls.

Next: commit the exact design/evidence changes, genuine independent phase81 foundation recheck on max/131072/7200; no dependent phases until P1 independently resolved. Allocate full phase set81..88 under ongoing authority;80 consumed before81, no actual calls invented. Human/live/release gates remain.

## Immutable independent phase80 report

# Independent OpenCode Go program_design_review

PROGRAM_DESIGN_REVIEW: STOP_SHIP

{
  "verdict": "STOP_SHIP",
  "findings": [
    {
      "severity": "P1",
      "title": "Normative tooling-audit gate names a retired reviewer and is unsatisfiable as recorded",
      "issue": "PAI.md §2 ('Review-tooling maintenance boundary') requires that 'require_tooling_audit checks an actual independent Mimo PASS/ADVISORY, ... [and] unchanged current code/tests/REVIEW_POLICY'. REVIEW_POLICY.md (2026-10-09, itself a critical source in the gate's list) records the owner's replacement of Mimo by GLM-5.3, states Mimo reports are 'never relabeled as GLM or accepted', and its own rule says any policy/critical-source change 'requires fresh independent re-audit before design receipts are consumed'. The only recorded re-audit attempt (Audit78) 'returned model glm-5.3 and finish_reason=length ... without a verdict'. Concrete reachable case: any consumer of PAI-00/PAI-01 design receipts running require_tooling_audit as specified today finds (a) no current Mimo route, (b) changed REVIEW",
      "fix": "Before approving PAI.md/PAI-01 or consuming any design receipt from this phase: amend PAI.md §2 to reference the currently pinned independent reviewer (or reviewer-agnostic wording deferring to REVIEW_POLICY), complete and record a genuine independent tooling audit PASS/ADVISORY bound to current critical-source hashes, then re-run require_tooling_audit to confirm unchanged hashes before record aggregation."
    },
    {
      "severity": "P2",
      "title": "Two matrix-bound PAI-00 regression files have no registered run command",
      "issue": "docs/design/PAI.requirements.json binds tests/test_playbook_bridge.py and tests/test_memory_research.py to PAI-00 only, but PAI-00's reconciliation_regression argv in docs/design/PAI.design.json runs tools/test_tiers.py and tests/test_openai_provider.py instead; no slice argv across the 32 registered slices runs those two files. PAI.md §10 asserts only that test_prm_product_ux_eval.py and test_opencode_role_review.py occur in both, and describes check_pai_plan as validating IDs/bindings/hashes/dependencies/case identity — not argv↔test_files equality. Concrete case: PAI-00 completes green on its registered argv while its two matrix-bound acceptance obligations were never executed, an omission the described structural checks cannot catch.",
      "fix": "Add tests/test_playbook_bridge.py and tests/test_memory_research.py to the PAI-00 reconciliation_regression argv (or bind them to an explicitly registered tier command), and extend check_pai_plan to enforce argv↔matrix test_files consistency wherever the matrix lists files."
    },
    {
      "severity": "P2",
      "title": "Budget reservation lifecycle unspecified for scheduler-enqueued and cancelled-before-dispatch work",
      "issue": "PAI.md §4's scheduler transaction ('locks due schedule rows, enqueues a unique ... job and advances next_due_at in ONE transaction') and PAI-08's scope omit any reservation, while ADR-013 states 'Transactional enqueue, policy reservations and side-effect records share one database transaction' — the two texts disagree on when authorize_and_reserve runs for background jobs. Separately, the reserve/settle contract (PAI-03, PAI.md §4) specifies only that *unknown* spend is never refunded; it never states that a job cancelled, paused, or invalidated by source revocation before dispatch settles zero and releases its upper-bound reservation. Concrete case: the freeze profile's 100 due schedules each hold an enqueue-time upper-bound reservation, the owner pauses/unsubscribes before dispatch, and—",
      "fix": "In the PAI-01/PAI-03 design record, pin reservation timing for scheduler-enqueued jobs (claim-time vs enqueue-transaction) and mandate zero-settlement/release of reservations for jobs cancelled, paused, or invalidated before dispatch or by revocation."
    },
    {
      "severity": "P2",
      "title": "cancel() result enum misreports terminal jobs",
      "issue": "PAI.md §4 defines cancel(owner, job_ref, expected_version) -> pending_stopped/already_started, but the PAI-06 job state machine includes completed/failed/cancelled. Concrete case: an owner cancels a job that already completed; per the written enum the caller must surface 'already_started', which contradicts ADR-013's own rule that cancellation 'reports already-started work accurately' and the programme's truthful-status requirement (ACT-03). Jobs blocked on an unknown attempt also have no distinct cancel outcome, though the awaiting_reconciliation status is separately specified.",
      "fix": "Extend the specified cancel() result set (e.g., pending_stopped/already_started/completed/failed/awaiting_reconciliation) in PAI.md §4 before PAI-06 implementation, and bind the truthful mapping in tests."
    },
    {
      "severity": "P2",
      "title": "PAI.md §9 sequencing text contradicts recorded owner sequencing (ADR-014/015)",
      "issue": "PAI.md §9 states 'PAI-02..26 depend on that gate. Prepare independent authorized maintenance and review/access packets while waiting', implying B-phase implementation waits for the human design-approval gate. IMPLEMENTATION_CONTRACT.md ADR-014/015 (2026-10-07, later than PAI.md's 2026-10-06 creation) records the owner's instruction to 'proceed with local PAI-02..26 implementation while design reviews/formal acceptance remain open'. Concrete case: an implementer of PAI-02..06 reading the hash-bound design record either stalls on a stale gate or treats the contract's supersession as an undocumented bypass, leaving the normative sequencing ambiguous at approval time.",
      "fix": "Update PAI.md §9 to state the ADR-014/015 sequencing explicitly: local PAI-02..26 implementation is authorized while independent design reviews and formal acceptance/human approval remain open and gating completion."
    }
  ],
  "not_verified": [
    "No runtime evidence exists for PAI-02..06 (status planned): all repository, lease/fencing, reservation, unknown-effect and recovery semantics are design-only; none of the mapped test files or requirement cases has been executed.",
    "Referenced evidence artifacts (docs/verification/PAI-00-reconciliation.md, PAI-00-file-manifest.json, PAI-design-evidence-bindings.md, PAI-progress.md) and all recorded hashes (requirements-matrix SHA256, manifest SHA256, spec_sha256) were",
    "Behavior of tools/check_pai_plan.py and tools/run_pai_acceptance.py (argv↔matrix equality, skip/xfail enforcement, nonzero-case checks) was not supplied; whether the P2 mapping gap would surface mechanically is unverified.",
    "Whether any genuine independent tooling-audit PASS/ADVISORY bound to current critical-source hashes exists outside the supplied packet; the recorded Audit78 ended without a verdict.",
    "Independent product-design review verdicts for ADR-013/PAI.md and the pinned-runner approval workflow state: none supplied; human approval fields are absent by design.",
    "Real PostgreSQL driver/version pinning, isolated test-DB creation, separate-process race and kill-boundary tests: planned under PAI-02 only, not observed.",
    "Live provider, account, service, timer or production state: none claimed in the packet; all live gates remain separate (PAI-27..29) and were not reviewed.",
    "Cross-phase slices PAI-07..31 and unsupplied spec sections (1, 3-8, 12, 13) were not reviewed in this phase; this review cannot approve the full design."
  ],
  "summary": "The PAI-00..06 design is strong on the hard parts: the prepared-attempt two-phase commit with locks held through one bounded call, lease/fencing, unknown-effect fencing with no auto-resend, conservative one-use budget settlement, tombstone-first cross-store deletion and restore ordering are specified consistently across PAI.md, ADR-013 and PAI.design.json, and the 69-requirement/10-scenario matrix maps every in-scope requirement (PLAN-01..03, ARCH-01/02, MIGRATION-01, COST-01, SEC-02, PERM-01, ACT-01..03, BRIEF-03, CHAT-02, MEM-01, OPS-01, UX-03/04) to these slices with dependencies matching ADR-013 (PAI-05 precedes PAI-06). No P0 was found: no duplicate-effect, authorization-bypass or data-loss path is left open by the written design. One P1 blocks: the phase's own evidence chain is broken — PAI.md §2 hard-codes the retired Mimo reviewer in the normative require_tooling_audit gate, the 2026-10-09 reviewer/policy change invalidated that gate by its own rule, the sole re-audit attempt ended without a verdict, and design records are meanwhile routed through the gated backend; as written the gate is unsatisfiable or must be bypassed before any PAI-01 receipt is trusted or approved. Remaining findings are advisory: two matrix-bound PAI-00 regression files lack any registered run command; reservation lifecycle for scheduler-enqueued and cancelled-before-dispatch work is unspecified (budget-window exhaustion by never-executed reservations); the cancel() enum misreports terminal jobs; PAI.md §9 sequencing text is stale against ADR-014/015. Fix the gate wording and complete a bound"
}
