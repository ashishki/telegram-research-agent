# Native tooling audit #41 response — STOP_SHIP preserved

Actual native pinned local entrypoint: run_codex_role.py --provider opencode-go,
PAI-00 program_design_review --tooling-review --thinking-disabled, 16000 output /
900 s. Native result: .playbook-artifacts/opencode-runs/
opencode-0eb60db79e9b451cbca4b5564109e886/result.json. Reviewed HEAD 4cfea92.
Original immutable report returns STOP_SHIP; no tooling gate is unlocked.

Concrete schema mismatch: provider schema capped findings at 12 while the
parser accepted 50 and did not enforce all string/shape ceilings. parse_response
now validates against the same VERDICT_SCHEMA with jsonschema, and the explicit
parser count is also 12. Negative cases reject 13 findings, oversized title /
summary and undeclared keys. Fixed diagnostics cannot echo provider data.

Concrete provenance improvement: every manifest entry now includes exact
rendered-section SHA256/byte count alongside its original source hash, and the
native run preserves input_packet.txt with the existing overall input SHA.
The real tooling packet test extracts every actual section and verifies each
rendered hash/size. Lossless JSON factoring still decodes and compares against
the original; AST normalization retains the full executable source.

Other audit allegations need independent resolution against actual code/tests:

- The prompt explicitly permits and explains lossless $N/$table, rather than
  forbidding them; its factor_json decoder checks exact reconstructed equality.
- The finalizer requires all four groups, exact role/feature/HEAD/design/source
  hashes, every 32 slice and spec section, and the CURRENT genuine tooling audit.
  Tests already reject head/scope/document drift, missing groups and stale audits.
- The supplied tests already include malformed identity/verdict, contradictions,
  truncation/timeouts/output bounds, redirects, source/report tamper and planning /
  egress gates before credential lookup. Their actual execution is synthetic
  evidence; independent code review cannot pretend it executed those tests.
- Hash integrity is not a cryptographic approval signature or proof against a
  fully privileged repository/DB adversary. Reviewers cannot grant human approval.

Scope remains the existing backend; no new role framework/authority was added.
The explicit native thinking mode requested/observed values are distinct.
No source transformations or receipt fields are hidden from the new audit.

Exact affected command:

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q -x tests/test_opencode_role_review.py tests/test_pai_acceptance_guard.py tests/test_playbook_bridge.py
```

Schema alignment: 80 passed in 3.52 s; section provenance: 80 passed in 3.18 s;
final real rendered-section check: 81 passed in 3.67 s. Zero skips/failures.
Next is an actual native independent tooling re-audit on the new committed SHA;
source/fixture passes cannot clear #41 or permit consuming design records.
