# Native92 ADVISORY and additional canonical feature-ID correction

2026-10-09. Actual92 reviewed9337faf, ADVISORY/no P0/P1,935.685s;
observed glm-5.3/requested max/observed effort unknown; usage50820/47418/98238.
It independently closes91 duplicate-argv/tier/post-call-drift changes. Exact
native result/report/input/log in PAI-review-continuation-92.json. No human or
live approval. Two P2 retained: legacy deep parse failure receipt (open advisory),
and generic bridge legacy Codex run route (addressed locally below).

Additional read-only root analysis, during the frozen92 request, used the REAL
pinned parser and a mocked upstream executor: absolute feature-id ending in
'docs/design/PAI' resolves the actual PAI.design.json, but the bridge did not call
the PAI audit (zero audit calls, one mock forwarding). No real approval executed.
Original evidence: .playbook-artifacts/pai-validation-20261009-91/path-alias-probe.json.
Current bridge only accepts canonical ASCII feature IDs, not paths/traversal/
whitespace. Four new negative cases reject before any pinned execution. This is
new source after92 and requires genuine independent93; no self-closure claimed.

Generic tools/playbook.py run_codex_role now permits historical verify/help only;
fresh runs must use the existing local --provider opencode-go wrapper. Three
negative launch cases cover no args/run/global-root+run. No upstream pin change,
no default reviewer replacement, and legacy receipt verification preserved.

Max/code/data limits unchanged: explicit max/input1MB/output131072/watchdog7200,
same fixed public/synthetic scopes and one fresh request.172 tests passed6.42s
for canonical-ID correction; final175 passed7.20s including legacy bridge policy.
Command:
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_opencode_role_review.py tests/test_playbook_bridge.py tests/test_pai_acceptance_guard.py tests/test_pai_plan.py
Pin/32/69/ten planning and git diff --check passed. No assertion/guard weakened.
Final log SHA256: 6da28bde5941e05afa6084df0daaab1f9ac04c6478dbc88013340816b1b24334.

Next scoped commit then one actual native93;92 consumed,101 allocated under ongoing authority. Only accepted current93 tooling permits corrected design88 P1 recheck94 and full fresh94..101 set. No prior design/fixtures substituted; no human/private/live/product/production/service/timer/release authority.

## Actual immutable native92 report

# Independent OpenCode Go program_design_review

PROGRAM_DESIGN_REVIEW: ADVISORY

{
  "verdict": "ADVISORY",
  "findings": [
    {
      "severity": "P2",
      "title": "Legacy deep-review post-transport failures leave no durable receipt",
      "issue": "In tools/mimo_code_review.py main(), after a successful _call_model, a non-JSON body makes _parse_json raise ValueError('unparsable_model_json'), which propagates as a traceback with no report written to --out; the invalid_identity_or_completion and invalid_verdict branches likewise only print a fixed stdout status and return 1 without an artifact. Reachable case: provider returns finish_reason 'stop' with garbage content; unlike the _transport_failure path, no receipt records input_sha256/requested_model/provider_call_attempted. Advisory legacy path, fail-closed, no content leak.",
      "fix": "Route post-transport parse, identity and verdict failures through the same fixed-field atomic failure receipt already used for HTTP/network/incomplete transport in _transport_failure."
    },
    {
      "severity": "P2",
      "title": "Playbook bridge forwards legacy run_codex_role past the wrapper's reviewer policy",
      "issue": "tools/playbook.py main() lists 'run_codex_role' in TOOLS, so 'python tools/playbook.py run_codex_role run ...' executes the pinned upstream Codex runner directly, while tools/run_codex_role.py main() denies no-provider 'run' for PA reviews. No acceptance bypass was found: the PAI approve gate require_trusted_design_records accepts only opencode_go/opencode_go_complete bindings plus the current tooling audit, so codex-run evidence cannot publish or unlock design records; this is an operator-surface/policy inconsistency on the supported route, not a silent fallback.",
      "fix": "Remove 'run_codex_role' from generic TOOLS forwarding so the gated wrapper is its only route, or document this playbook invocation as an explicit privileged legacy surface."
    }
  ],
  "not_verified": [
    "Pinned upstream kit internals (feature_design_lib, feature_workflow, approve_feature_design, playbook_validate, renderers) are commit-pinned but not supplied for line-level review.",
    "Live OpenCode Go provider, TLS identity/effort telemetry and real SSE behavior were not exercised; static code reading only.",
    "The 31 PAI runtime test files named by the pai-complete tier were not supplied; existence and content unverified.",
    "docs/verification/PAI-next-review-packets.json and owner authority records were not supplied; only their guard logic was reviewed.",
    "The native76 EOF reproducer was not executed here; EOF fail-closed behavior is confirmed by code inspection only.",
    "verification/PAI-upstream-gate-proposal.md is referenced by policy but was not supplied for review.",
    "Privileged wholesale replacement of code/Git/artifacts remains outside local hash-integrity guarantees; no signed or append-only attestation exists.",
    "Full PAI feature design, product surfaces and human acceptance are outside this tooling-only scope."
  ],
  "summary": "Tooling-scope audit of the 21 supplied review-transport/checker sources. Every gate precedes credential lookup and the single budgeted provider call: planning gate, PAI four-phase requirement, explicit egress plus call_cap=1, recorded model/input/output/timeout authority, current independent tooling audit, and a committed-HEAD snapshot that rejects dirty, symlinked and hardlinked inputs. parse_response enforces the strict verdict schema and P0/P1=>STOP_SHIP; require_tooling_audit re-hashes every toolchain source, re-derives the stored packet through prepare_packet, and blocks on any matching STOP_SHIP or drift; finalize demands four same-model phases at one HEAD/design hash and republishes only via the pinned consumer with a single marker. The SSE reader fails closed at EOF and missing [DONE] with bounded wire/text/time; failure receipts are fixed-field and sentinel-tested against leaks. run_pai_acceptance cannot pass on missing, zero, skipped or duplicate cases, and the pai-complete tier binds --require-spec-matrix with honest scoped labeling. The native76 P0 allegation does not hold against this code: b'' is falsy, so _read_review_stream raises review_stream_incomplete with terminal_event eof before byte counting, consistent with the supplied reproducer. No P0/P1 found within the stated trust boundary; two P2 notes remain. This is tooling verification only, not feature-design approval, live-provider validation or human acceptance."
}
