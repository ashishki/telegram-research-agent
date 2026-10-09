# Actual110 current independent tooling gate

2026-10-09. Tooling110 atcb7020f: ADVISORY/no P0/P1,834.581s,
usage52048/49281/101329, observed glm-5.3/requested max/observed effort unknown.
PAI-review-continuation-110.json binds actual command/input/report/result/log.
Actual require_tooling_audit accepted the immutable current sources/pin/runtime
and substantive report; no implementer replacement or model/telemetry invention.
The placeholder rejection/prompt changes have actual independent tooling evidence.
This is not full PAI design/implementation/human/live acceptance.

Five P2 advisories remain exactly in the immutable report: explicit-key missing
file env fallback; mutable authority manifest coverage; acceptance-test committed
provenance; aggregate approval-time integrity checks; malformed-input diagnostics.
They are retained, not silently fixed or called accepted. Audit110 binds cb7020f only. The later product-verification assignment changes
active test registration in tools/test_tiers.py; do not consume110 as an audit of
that newer source. No further governed design publication or112..118 batch ran.
All human/private/live/production/service/timer/release/other-role gates remain.

## Original actual independent report

# Independent OpenCode Go program_design_review

PROGRAM_DESIGN_REVIEW: ADVISORY

{
  "verdict": "ADVISORY",
  "findings": [
    {
      "severity": "P2",
      "title": "Explicit --key-file absence silently substitutes environment credentials",
      "issue": "tools/mimo_code_review.py::_api_key honors a supplied key file only when Path(explicit_file).is_file(); a missing or misspelled path silently falls through to OPENCODE_API_KEY or OPENCODE_API_KEY_FILE. Reachable case: run tools/run_codex_role.py with '--provider opencode-go run --task PAI-00 --feature-id F --role program_design_review --key-file /reviews/missing.key --allow-provider-egress --call-cap 1' while OPENCODE_API_KEY is set: every planning/authority/snapshot gate passes and the single provider call executes under a different credential source with no diagnostic, contradicting the owner-directed reviewed key location.",
      "fix": "In _api_key, when explicit_file is non-empty but the path is absent or unreadable, raise a fixed ValueError naming only the missing source (fail closed); never fall back to other credential sources when an explicit key file was requested."
    },
    {
      "severity": "P2",
      "title": "Budget/authority record is outside the tooling-audit critical-source set",
      "issue": "tools/opencode_role_review.py::require_tooling_audit accepts an audit only when its documents equal TOOLING_REFS plus the two boundary docs; docs/verification/PAI-next-review-packets.json, which gates model selection and timeout/output/input maxima before credentials, is not in that set, and the audit result's recorded reviewer_model_authority sha256 is never re-compared. Editing that record (e.g., raising per_call_output_tokens_maximum or switching the selected model) leaves a standing PASS/ADVISORY audit 'current', so design reviews and finalize proceed under changed authority without the fresh re-audit REVIEW_POLICY promises for critical sources. execute() re-validates the live record, so no unsafe allow is reachable; the defect is audit-invalidation coverage.",
      "fix": "Add the authority record path to TOOLING_REFS (and the manifest set check), or in require_tooling_audit require result['reviewer_model_authority']['sha256'] plus any extended/input authority shas to equal the current record's digest, so authority drift invalidates standing audits before design receipts are consumed."
    },
    {
      "severity": "P2",
      "title": "Acceptance runner executes arbitrary or dirty test files without committed-HEAD verification",
      "issue": "tools/run_pai_acceptance.py::main accepts any positional whose first '::' segment ends in '.py' (including absolute and out-of-repo paths) and runs pytest without verifying the executed files are tracked regular blobs at captured HEAD, unlike verify_packet_snapshot for review packets. Reachable case: a working-tree-only or dirtied tests/test_pai_requirements.py with vacuous cases still produces 'PAI full-spec acceptance: N acceptance cases, zero skips/failures', because classname/name matrix matching is purely path- and name-derived. Operator-invoked and not machine-consumed for approval gates, hence P2, but acceptance provenance is weaker than the declared fail-closed standard.",
      "fix": "Restrict positional paths to repo-relative tests/**.py and, mirroring verify_packet_snapshot, verify each executed file is a tracked 100644/100755 blob at the captured HEAD with a matching worktree digest before pytest runs; reject all other paths with a fixed diagnostic."
    },
    {
      "severity": "P2",
      "title": "Aggregate approval evidence lacks hash re-verification at the approval gate",
      "issue": "tools/finalize_opencode_design_reviews.py::finalize writes the aggregate result.json without a .sha256 sidecar, and tools/opencode_role_review.py::require_trusted_design_records re-reads the bound result.json/aggregate evidence checking only the reviewer_binding prefix and tooling_audit_ref equality, never a stored hash. Post-finalize drift in those JSON files would go undetected at 'feature_workflow approve --feature-id PAI'; phase sidecars are verified only inside finalize itself. Trusted-workspace boundary applies, but the handling is asymmetric with phase evidence.",
      "fix": "Write result.json.sha256 for the aggregate and, in require_trusted_design_records, re-verify the sidecar hash (and the referenced report hash) of the bound evidence path before treating the design record as trusted at approval time."
    },
    {
      "severity": "P2",
      "title": "Fail-closed denials surface as untyped crashes on malformed inputs",
      "issue": "tools/check_pai_plan.py::check raises IndexError when the spec lacks a '### 13.2.' section or change_budget lacks '<=' (main's except tuple omits IndexError), and tools/opencode_role_review.py::factor_json decode raises TypeError/KeyError for documents containing literal '$table'-shaped objects. All outcomes exit nonzero (fail-closed), but tracebacks replace fixed diagnostics, and a design file containing reserved '$table' syntax can never be packeted for review.",
      "fix": "Validate presence and shape explicitly (spec section header, change_budget format, '$table' object shape) and raise ReviewBlocked/ValueError with fixed messages; add IndexError to check_pai_plan.main's caught exception tuple."
    }
  ],
  "not_verified": [
    "Test and ledger pass claims (117 and 120 scoped runs, native76 EOF log, reproducer output) were not executed here; this assessment is static reading of code and tests only.",
    "Independence and authenticity of tooling-audit result.json/report.md artifacts cannot be verified by code; no signed or append-only attestation exists within the stated boundary.",
    "Provider identity, reasoning effort and usage are provider-reported metadata over TLS; observed glm-5.3 and requested max effort are not cryptographically attested.",
    "Pinned upstream kit sources (feature_workflow, approve_feature_design, feature_design_lib, playbook_validate, prompt renderer) are outside this packet; integrity rests on the commit pin and clean-worktree checks.",
    "SPEC_GROUPS-to-spec-section mapping semantics are unverified; PERSONAL_ASSISTANT_SPEC and the PAI design/matrix contents are not part of this tooling packet.",
    "Owner messages and maxima in docs/verification/PAI-next-review-packets.json are trusted committed data; authenticity beyond Git history and content privacy beyond the fixed markers are unverified.",
    "Live OpenCode Go endpoint behavior (real SSE error shapes, usage-only events, GLM reasoning telemetry, redirect attempts) was not exercised; only synthetic streams were reviewed.",
    "Full PAI feature design, product runtime, live accounts, human acceptance and deployment are outside this transport/checker audit."
  ],
  "summary": "Scope: the PAI-00 tooling packet (21 documents) covering the tools/playbook.py pin and approval bridge, run_codex_role routing, opencode_role_review packet preparation, pre-credential gates, single provider execution and evidence publication, the mimo_code_review SSE transport and failure receipts, check_pai_plan registry/matrix verification, finalize_opencode_design_reviews four-phase aggregation, run_pai_acceptance strict report checking, test_tiers, render proxies, the four offline test suites, REVIEW_POLICY, the pin lock and dev requirements. Conclusion: no P0/P1 on the supported route. Credential lookup is preceded by planning, egress, single-call, model/input/output/timeout authority, tooling-audit and committed-HEAD snapshot gates; packets are hash-bound with fail-closed EOF, oversize, placeholder and drift handling; STOP_SHIP audits and phase identity/scope/HEAD drift block publication; the native76 EOF P0 allegation is refuted by the code's empty-line EOF raise and its recorded stream state, consistent with Python len(b'')==0 semantics. Five P2 hardening items remain: silent env-key substitution for a missing explicit key file; the budget/authority record outside the tooling-audit critical-source set; acceptance runs lacking committed-HEAD verification of executed test files; no hash re-verification of aggregate evidence at the approval gate; untyped crash paths in fail-closed denials. Evidence limits: no tests were executed; independence of audit artifacts, provider identity/effort telemetry, pinned upstream kit sources, spec-section mapping semantics and live SSE"
}
