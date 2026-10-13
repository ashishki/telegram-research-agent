# D05 + D06 — frozen local review and focused repairs

Full reviewer `/root/daily03_readonly_review`, fresh independent read-only
collaboration process; inherited active defaults/no override, observed model/
effort unknown. Reviewed exact `2318bbe4f1e58af571583a7d3fedd3bcb55f34b1`, base
`980087f92ae758e616200f57ccad1ea558aa1de4`; binary diff SHA-256
`90de225bec9e1b8d21103e276447d8bd7a4d860540ad983d8b5c5d4242a1a051`.
One full accumulated verdict **STOP**; no P0. No writes/pytest/DB/HTTP/provider/
credentials. Two read-only memory probes used committed Git bytes and
PYTHONDONTWRITEBYTECODE=1. Test ledger inspected, not independently rerun.

| Finding | Severity | Frozen evidence and repair |
| --- | --- | --- |
| DAILY03-R01 | P1 | model_protocol.py:189–204 checked only before blocking readline; cancellation/source/deadline changes during terminal delimiter still returned accepted text. Recheck immediately after reads, before deltas and final acceptance; retain partial count, unknown cost and logical no-repeat. |
| DAILY03-R02 | P1 | evaluation.py:181–215 accepted DAILY-007 with unrelated source ref a*64/digest b*64/version999, action.dispatch denied/calls0, and unrelated model identity/input. Freeze driver receipt contract; require exact source ref/digest/version, tool/status/call relation, calibrated synthetic input fingerprints/identity and every input/result/turn binding. Integrity of trusted capture is not execution authenticity. |
| DAILY03-R03 | P2 | Some subsystem outputs were reconstructed from final status; Watch confirmation already appeared paused and Act preview unknown. Capture each operation at its boundary, and explicitly label native assistant turns versus subsystem status projections. |
| DAILY03-R04 | P2 | Native capture checked freeze only at start. Compare HEAD/tracked/untracked implementation state again before publication; drift fails without an artifact. |
| DAILY03-R05 | P2 retained | Socket inactivity timeout and completed-read bounds do not interrupt one slow-drip blocking read at the absolute deadline. Post-read guards prevent acceptance after expiry, but prompt interruption needs an incremental/abort transport. No network reproduction; do not claim a hard read deadline or immediate cancellation. |

Reviewer found no additional P0/P1 in explicit credential/endpoint scopes,
redirect/proxy denial, alias/media boundaries, durable no-repeat, unknown cost
or accepted-reply accounting preservation. Actual twenty-case pre-fix CLI capture
was outside the frozen reviewer evidence and is retained as historical regression
input, not current acceptance.

Implementer reproduced R01/R02 before repair with:
`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q --tb=short tests/test_daily_model_protocols.py::test_terminal_sse_read_rechecks_before_acceptance tests/test_daily_eval_manifest.py::test_real_trace_rejects_unrelated_receipt_relationships`:
**exit 1, 11 failed /2.37s** (three terminal changes and eight corrupt receipt
relationships were wrongly accepted).

After repairs:

- Same prefix, `tests/test_daily_model_protocols.py::test_terminal_sse_read_rechecks_before_acceptance tests/test_daily_eval_manifest.py::test_real_trace_rejects_unrelated_receipt_relationships tests/test_daily_eval_manifest.py::test_matching_words_or_claimed_success_cannot_replace_constraints tests/test_daily_eval_manifest.py::test_public_projection_withholds_undeclared_assistant_and_rejects_secret_input`: exit 0, **13 passed /2.05s**.
- Same prefix, `tests/test_daily_model_protocols.py::test_terminal_sse_read_rechecks_before_acceptance tests/test_daily_model_protocols.py::test_stream_complete_and_cancel_partial_no_final_result tests/test_daily_model_protocols.py::test_scoped_runtime_receipt_accounting_and_reconstruction_fence[cancel] tests/test_daily_eval_manifest.py::test_real_trace_rejects_unrelated_receipt_relationships tests/test_daily_eval_manifest.py::test_daily_native_case[DAILY-007] tests/test_daily_eval_manifest.py::test_daily_native_case[DAILY-019] tests/test_daily_eval_manifest.py::test_daily_native_case[DAILY-020]`: exit 0, **16 passed /18.31s**, includes isolated-PG source/Watch/Act and scoped cancel/no-repeat.

The new fixture fingerprints were calibrated from the actual frozen 2318bbe
capture. These are dev regression fingerprints; no independent holdout, model
quality or human usefulness is inferred. Packet/source/turn/model relationships
are checked; the local producer/JSON is not cryptographically authenticated.

Narrow independent reviewer `/root/daily03_p1_recheck` returned **PASS — R01/R02
closed, no new P0/P1 within this fix scope** on
`e10365e4c41eb8d8585c9679450e6b2c94d96eaf`; range `2318bbe..e10365e`, binary diff
SHA-256 `b946977d423c651919cae11187b9bcbdee310d18924bc0499672fed0959b51ee`.
Requested inherited defaults/no override; observed model/effort unknown. Fresh
read-only collaboration process, no writes/pytest/DB/HTTP/provider/credentials.

Independent committed-byte memory probes rejected all six delta/terminal
cancel/deadline/source changes. Terminal cancel/deadline retained 16 partial
characters and retry_allowed:false; unchanged stream accepted with stop/usage.
The durable attempt/accounting paths were inspected and remain no-repeat.
A trusted old DAILY-007 capture projected into repaired schema passed; thirteen
independent source/ref/version/tool/status/call/model/input/result/binding/view
mutations were denied. Source-ref/digest probes changed both object and binding;
frozen source equality, not only two-copy disagreement, rejected them.
Implementer PG/test counts were inspected, not independently rerun. R05 retained;
trace integrity is not cryptographic execution authentication. No second full
review ran. Non-Codex Go/governed/human gates remain open.

Additional schema/drift checks: same P/--tb=short, `tests/test_daily_eval_manifest.py::test_capture_refuses_head_drift_before_publication tests/test_daily_eval_manifest.py::test_missing_cases_or_cross_split_source_and_scenario_leaks_fail tests/test_daily_eval_manifest.py::test_trace_requires_complete_typed_evidence_and_rejects_secret_canaries tests/test_daily_eval_manifest.py::test_suite_cannot_accept_missing_or_duplicate_cases`: exit 0, **15 passed /2.04s**.
