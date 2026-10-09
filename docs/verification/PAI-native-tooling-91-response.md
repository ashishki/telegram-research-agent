# Actual tooling91 STOP — duplicated approval argv fixed; independent92 next

2026-10-09. Genuine native91 reviewedf64c504, STOP_SHIP (1 P1/2 P2),995.972s,
observed glm-5.3/requested max/observed effort unknown. Usage47293 prompt/56153
completion/103446 total. Receipt PAI-review-continuation-91.json binds actual
immutable result/report/input/log/command; no implementer override or acceptance.

P1 reproduced with the REAL pinned feature_workflow.build_parser: duplicate
--root and --feature-id take the LAST value, while the old bridge read FIRST.
No actual approval executed. Local bridge now rejects duplicate gated options,
parses canonical approve syntax with allow_abbrev=False, disallows '--', and
handles real help by exiting locally (never forwarding an approval invocation).
Eight ambiguity/abbreviation/help-placement cases never reach pinned execution;
real-kit duplicate parsing is exercised. Canonical PAI routes still invoke the
actual independent design-record guard; root must be assigned workspace.
Upstream/pin untouched, no universal hook or human approval forged.

P2 tier provenance: tools/test_tiers.py added to TOOLING_REFS, with current-audit
invalidation when that exact source is changed. P2 post-call drift: HEAD/module/
dependency/input/design/tooling drift checks now live inside the receipt-producing
try. Failure records actual attempt/model/finish/usage when available, outcome
unknown, and no verdict/summary content; drift cannot publish or auto-retry.

Command:
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_opencode_role_review.py tests/test_playbook_bridge.py tests/test_pai_acceptance_guard.py tests/test_pai_plan.py
168 passed7.67s; zero failures/skips. Pin and32/69/ten planning checks passed.
Log .playbook-artifacts/pai-validation-20261009-91/scoped.log
SHA256 795adf60cfb7afe61d55616a2fba53874f9882c46a9fb7c437a58e4647809aea.

Next scoped commit, then ONE genuine native92 max/input1MB/output131072/watchdog7200.91 consumed,100 allocated under ongoing authority; product93 is design88 P1 recheck only AFTER accepted current92 audit. Fresh complete roles93..100 all at one unchanged HEAD/design. Old79/91 STOP/prior complete programme records retained; not current acceptance. Human/live/product/production/release gates unchanged.

## Actual immutable tooling91 report

# Independent OpenCode Go program_design_review

PROGRAM_DESIGN_REVIEW: STOP_SHIP

{
  "verdict": "STOP_SHIP",
  "findings": [
    {
      "severity": "P1",
      "title": "playbook.py approval gate uses first-match option parsing; duplicated --feature-id tokens bypass the PAI tooling-audit gate",
      "issue": "tools/playbook.py main() gates PAI approve on option_value(args,'--feature-id')=='PAI', but option_value() returns the FIRST occurrence while the forwarded pinned feature_workflow (standard argparse) resolves the LAST; bare --help/-h tokens also skip the gate where the consumer would not treat them as help (e.g. after '--'). Reachable case: playbook.py feature_workflow approve --feature-id OTHER --feature-id PAI skips require_trusted_design_records(ROOT,'PAI') and forwards to the pinned approve, which (last-wins) approves PAI without current tooling-audit currency or the opencode_go_complete binding; --root desyncs the same way. No other guard in the packet re-checks audit currency (the upstream checker was deliberately unaltered), so the enforced independent tooling gate fails on the only",
      "fix": "Reject duplicate or ambiguous occurrences of gated options and any '--'/'--help'/'-h' tokens in the bridge gating context, or evaluate the gate with the consumer's own parser semantics (e.g. have the pinned tool emit its resolved configuration before approving). Add negative tests for duplicated --feature-id/--root and help-token placement."
    },
    {
      "severity": "P2",
      "title": "tools/test_tiers.py is outside TOOLING_REFS, so tier-evidence drift never invalidates a tooling audit",
      "issue": "PAI-native-tooling-74-response.md §5 records that tools/test_tiers.py's pai-complete tier passes --require-spec-matrix and that the full-tier proof was bound and run, but tools/test_tiers.py is absent from TOOLING_REFS in tools/opencode_role_review.py. require_tooling_audit() re-hashes only manifest documents, so editing the tier orchestrator (e.g. dropping the matrix flag) leaves a recorded tooling PASS current and invisible to the tooling reviewer, contrary to the policy that any critical evidence-source change requires a fresh independent re-audit before design receipts are consumed.",
      "fix": "Add tools/test_tiers.py (and any other referenced evidence-construction source) to TOOLING_REFS so changes force a fresh independent tooling audit, and add a negative test that a modified tier source invalidates a previously matching audit."
    },
    {
      "severity": "P2",
      "title": "Post-call drift discards a received verdict without a durable failure receipt",
      "issue": "In tools/opencode_role_review.py execute(), the drift checks (HEAD, runtime dependencies, gate modules, packet documents, design hashes, tooling audit) run after the try block that writes failure.json. When one triggers after a successful provider response, the run directory keeps attempt.json with status 'request_prepared' and has neither failure.json nor result.json, so a completed call whose verdict was discarded is indistinguishable from a call never attempted - contrary to the durable attempted/unknown-outcome receipt the deep transport already writes (native-74 §2). Evidential only: no retry exists and no verdict is published.",
      "fix": "Wrap the post-call drift checks so any block after a provider response also writes failure.json with status no_valid_verdict, provider_call attempted and provider_outcome unknown, storing no verdict content; add a drift test asserting the receipt exists."
    }
  ],
  "not_verified": [
    "Pinned upstream feature_workflow/approve parser internals (duplicate-option and '--' handling) are not in the packet; the P1 case assumes standard argparse last-wins semantics.",
    "tools/test_tiers.py content is not supplied; the pai-complete --require-spec-matrix binding is known only from PAI-native-tooling-74-response.md.",
    "No signed or append-only attestation: result sidecars, reports and PAI-next-review-packets.json authority records are forgeable by a privileged workspace writer; genuineness rests on trusted Git/workspace.",
    "Real provider SSE event shapes (model field on every event, usage events, effort forwarding) are unverified; the transport fails closed on any mismatch.",
    "No live provider, credentials, accounts or execution available to this reviewer; all conclusions are static review of the supplied packet.",
    "docs/verification/PAI-next-review-packets.json actual records (model, owner amendments, caps) were not supplied; authority enforcement was reviewed as code only."
  ],
  "summary": "Tooling-scope audit of the review transport/checker chain: playbook bridge, run_codex_role, opencode_role_review, mimo_code_review transport, check_pai_plan, finalize_opencode_design_reviews, run_pai_acceptance and their tests. Verified strengths: authority and budget gates precede credential lookup; packet sources are bound to the captured HEAD with mode, nofollow, nlink and restricted-content checks; stream EOF, truncation, size and identity failures are fail-closed with fixed diagnostics and no provider-text leakage; the phase partition and four-phase finalizer enforce full slice/spec coverage, hash-bound reports, STOP dominance and single publication. One P1 stops ship: the bridge's PAI approval gate parses a token stream first-match while the forwarded pinned consumer resolves last-wins (and the gate skips on bare help tokens), so duplicated --feature-id/--root tokens can bypass require_trusted_design_records on the supported route. Two P2s: tools/test_tiers.py is outside TOOLING_REFS so tier-evidence drift never forces re-audit, and post-call drift blocks discard a received verdict without a failure receipt. Local hashes are not signed or append-only; privileged wholesale replacement and provider-side identity remain unverifiable and are preserved as stated limitations. This audit grants no deployment, human design acceptance or release authority."
}
