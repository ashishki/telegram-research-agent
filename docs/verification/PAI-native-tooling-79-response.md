# Native GLM tooling79 — actual ADVISORY, current gate accepted

2026-10-09. Reviewed committed HEAD88da0f54aad02b58ec1c606e0360c47223ba34e4.
Actual bounded request: GLM-5.3/OpenCode Go, requested reasoning=max,
output131072, watchdog7200s, public code/synthetic inputs only, one request.
Exit0 after601.788s; provider-reported glm-5.3; observed effort unknown.
Usage46484 prompt/31947 completion/78431 total, cost unknown.
No P0/P1; four P2. Actual runner and require_tooling_audit accept ADVISORY
against unchanged current critical sources, real pinned modules and reconstructed
packet. No implementer acceptance/verdict substitution. Historical STOPs/length
failures unchanged. PAI-review-continuation-79.json binds result/report/input/log
hashes and exact command. No human design/live/release approval.

Retained advisory work, deferred to avoid invalidating the current audit while
all eight design parts use one unchanged HEAD/design:

- CLI abbreviation/alternate spelling: reviewer conditional on upstream parser,
  not independently exercised; proposed real-kit negative test remains pending.
- Mutable budget/authority file: not HEAD-bound like packet sources. Actual call
  count/state must evolve during one frozen design set. A future change should
  separate stable owner scope from mutable consumption, then re-audit; wholesale
  privileged authority replacement stays outside the declared trust boundary.
- Cadence/projection text: engineering A..G and four full-design groups are distinct;
  clearer explanation and the PROJECT_BRIEF stub wording remain advisory work.
- Evidence atomicity: improve crash robustness without treating torn files as a
  complete verdict; current consumers reparse/revalidate and fail closed.

Full independent findings/not_verified/summary follow verbatim from the actual
read-only reviewer. This preserves allegations and limits, not implementation
agreement with every inference. No provider reasoning text is recorded.

# Independent OpenCode Go program_design_review

PROGRAM_DESIGN_REVIEW: ADVISORY

{
  "verdict": "ADVISORY",
  "findings": [
    {
      "severity": "P2",
      "title": "PAI approve gate matches only exact flag spelling; upstream parser variants can skip it",
      "issue": "In tools/playbook.py main(), the PAI approval gate triggers only when 'approve' is an exact args element and option_value(args,'--feature-id') returns exactly 'PAI'. No guard exists between this sniff and subprocess.run forwarding to the pinned feature_workflow.py. If the pinned kit's argparse keeps the stdlib default allow_abbrev=True (upstream source not supplied), 'python tools/playbook.py feature_workflow approve --feature PAI ...' skips require_trusted_design_records and reaches upstream approve, which per REVIEW_POLICY manufactures a codex_exec binding from a report at its default path — the exact stale-receipt bypass this gate was added to stop. Existing negative tests cover only the exact '--feature-id PAI'/'--feature-id=PAI' forms. Reachability depends on the unverifiable upstream",
      "fix": "Canonicalize or strictly re-parse the forwarded argv for approve (reject abbreviated/unknown option tokens, enumerate approve-like subcommands), or push an allow_abbrev=False pin change through the separately reviewed upstream proposal; add a real-kit abbreviation negative test."
    },
    {
      "severity": "P2",
      "title": "Credential-gating authority file is the one input not bound to captured HEAD",
      "issue": "tools/opencode_role_review.py reviewer_model_authority() and extended_review_authority() read docs/verification/PAI-next-review-packets.json live, before _api_key(). That file is in neither PACKET_REFS, TOOLING_REFS nor the snapshot manifest, so verify_packet_snapshot and require_tooling_audit never bind it to HEAD. Concrete case: after any recorded tooling PASS, an uncommitted edit adding per_call_output_authority / raising per_call_timeout_seconds_maximum unlocks --output-token-cap 131072 or --timeout-seconds 7200 with only a content sha256 recorded in evidence; nothing distinguishes owner-recorded from locally edited authority, and the dirty-input denial applied to every packet document is not applied to the credential unlock.",
      "fix": "Include PAI-next-review-packets.json in the packet manifest/verify_packet_snapshot (or require equality with its committed-HEAD blob) before key lookup, mirroring the dirty-review-input policy."
    },
    {
      "severity": "P2",
      "title": "Policy/projection text drift can mislead consumers and reviewers",
      "issue": "docs/REVIEW_POLICY.md cadence lists seven phase groups 'A=00..01 ... G=27..29' (30 tasks), while the implemented REVIEW_GROUPS are four groups covering PAI-00..31 (foundation 0-6, product 7-15, sources 16-20, completeness 21-31) and finalize_opencode_design_reviews.py requires exactly those four parts. Separately, prepare_packet() replaces docs/PROJECT_BRIEF.md for program_design_review with the stub 'Authority hash retained in manifest; full feature brief/spec included.', which asserts inclusion of a document that was in fact omitted (only its hash is retained). Both texts contradict the code they describe.",
      "fix": "Rewrite the REVIEW_POLICY cadence paragraph to match the four-group aggregator and 32-slice registry, and reword the PROJECT_BRIEF stub to state the brief is omitted with the original hash retained."
    },
    {
      "severity": "P2",
      "title": "opencode evidence writes are not atomic, unlike the deep-review writer",
      "issue": "opencode_role_review.execute() writes report.md, result.json and result.json.sha256 via plain write_text() with no same-directory temp file, fsync or os.replace, while mimo_code_review._write_report already implements the atomic pattern. A crash can leave torn files; because the .sha256 is computed by re-reading the torn bytes, the pair stays internally consistent and every consumer (require_tooling_audit, finalize, parse_response) re-parses and revalidates, so acceptance fails closed. This is robustness, not a publishable-verdict risk.",
      "fix": "Reuse the same atomic write helper (temp file in run_dir, flush, fsync, os.replace) for report.md and result.json before publishing its hash."
    }
  ],
  "not_verified": [
    "Pinned upstream kit d570163 contents (feature_workflow/approve CLI, approve_feature_design, feature_design_lib): whether abbreviated or alternate approve spellings are actually reachable past the playbook.py PAI gate.",
    "Committed content/provenance of docs/verification/PAI-next-review-packets.json; it gates credentials at runtime but is outside the reviewed snapshot.",
    "PAI.design.json, PAI.requirements.json, PAI.md, PERSONAL_ASSISTANT_SPEC.md and the tasks pack: phase design/matrix content, and whether every mandatory scenario carries and enforces a recovery_test_node.",
    "Live provider behavior of opencode.ai/zen/go/v1 and GLM-5.3 (SSE shapes, usage/effort telemetry, redirects); no live egress was performed in this review.",
    "Claimed scoped test executions (117/120 passing) in PAI-native-tooling-74-response.md; reviewers have no execution tools and only assessed sources statically.",
    "Signed physical-model identity or append-only external attestation; explicitly outside the stated trust boundary and not claimed by this code.",
    "Privileged replacement of runner/workspace/Git and direct upstream/import execution outside tools/playbook.py; outside local hash guarantees and the wrapper's claimed scope.",
    "Torn-write and symlink race windows between is_symlink/hash checks and subsequent reads under concurrent privileged local processes."
  ],
  "summary": "Static review of the actual review transport/checker (playbook wrapper, opencode role review, GLM/Mimo transport, plan checker, four-phase finalizer, strict acceptance runner and their negative tests) within the stated trusted-runner/workspace/Git boundary. No P0/P1 runtime defect is proven. The native76 EOF allegation is refuted by the code and reproducer: empty bytes are falsy, the EOF check precedes byte counting, and empty/JSON-only/JSON+stop-before-DONE streams all raise review_stream_incomplete with no payload returned. Verified strengths: fail-closed gates (planning, egress, call-cap, model/effort, tooling audit, snapshot, budget authority) precede credential lookup; strict lossless verdict schema with P0/P1-forces-STOP_SHIP enforced at parse and re-checked at aggregation; failure receipts are fixed-text, outcome-unknown, leak-free with no retry anywhere; packet sources are HEAD-bound, blob-typed, link-denied and secret-scanned; factor_json is backstopped by a decode round-trip guard; the finalizer requires four hash-bound same-model phases under a current independent tooling audit; the acceptance runner denies skips, duplicates, missing matrix bindings and implicit suite runs. Four P2 items remain (approve-gate flag sniffing robustness, the un-HEAD-bound credential authority file, policy/projection text drift, non-atomic evidence writes), plus the preserved limitations in not_verified; none block within the declared boundary."
}
