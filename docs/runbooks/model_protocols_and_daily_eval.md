# Local model protocol and daily evaluation

D05/D06 full-reviewed source: `2318bbe`; fixed/narrow recheck: `e10365e`. This extends the existing durable runtime,
not a new model/provider loop. No configured descriptor is an egress grant or
an observed capability. Real canaries still need selected provider/data/budget.

`model.capabilities` is optional for legacy Chat Completions endpoints. Explicit
fields: protocol=chat_completions, token_parameter=max_tokens|max_completion_tokens,
accepted_models (exact returned IDs, at most eight), streaming, usage_semantics,
store_false, client_kind, session_ref and workload_ref. Output remains bounded
at 16,000 requested tokens/24,000 UTF-8 bytes. No arbitrary extra parameters.
Unsupported Responses/Messages/modality contracts fail rather than falling back.

Example public descriptor for a deliberately selected GPT-4o snapshot:

```json
{"protocol":"chat_completions","token_parameter":"max_completion_tokens",
 "accepted_models":["gpt-4o-2024-08-06"],"streaming":true,
 "usage_semantics":"openai_chat_output_includes_reasoning","store_false":true}
```

This example is prepared configuration, not account or privacy approval. Choose
exact identities for the actual selected endpoint; no automatic alias expansion.
A compatible Flash endpoint may explicitly select max_tokens and leave unknown
usage semantics. Do not infer streaming or known billing from Chat compatibility.
Go requires the exact Go endpoint, own fixed User-Agent and opaque stable session/
selected workload refs. Typical coding-traffic terms do not establish suitability
for continuous personal mail/news work. Missing access/policy does not block local
fixtures or evaluation.

Synchronous complete_with_receipt and opted-in stream_with_receipt share sealed
reservations, final guards and the logical attempt fence. SSE partial events are
untrusted text, with no action authority. Cancellation/EOF/missing usage/DONE,
invalid output, HTTP500 and transport loss remain non-retryable. Known rejection
has only status/retry_after; this does not establish a zero charge. Accepted
model identity/usage/stop/duration is durable without text/headers/URL. A slow blocking read may delay interruption; post-read guards prevent late
acceptance, not immediate cancellation (retained R05 P2). Accounting
loss retains the response and an unconfirmed marker, never another call.

The first twenty frozen tasks are dev regressions. Preserve the 120-unit target
and prepare independent source/scenario holdouts later; do not report a quality
score from mechanics. Public trace projection omits undeclared assistant text.
Trace view_kind distinguishes actual assistant turns from per-operation subsystem
status projections. Frozen driver/tool/source/version/input/result relationships
are required; fingerprints are calibrated dev inputs. JSON integrity does not
authenticate execution. Native fixture entrypoints differ by subsystem; Telegram/client acceptance is
separate. Export only synthetic fixtures, no personal reports or credentials.

After committing source/fixtures/tools, capture once on the frozen checkout:

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_daily_eval.py --output /tmp/daily-synthetic-traces.json
```

The tool checks HEAD/tracked/untracked implementation paths both before and after
capture; drift and overwriting output are denied.
It instantiates only the existing isolated PG/loopback fixture; no real provider
or private DB. Offline verification starts no fixtures:

```bash
PYTHONPATH=src .venv-pai/bin/python tools/run_daily_eval.py --verify /tmp/daily-synthetic-traces.json
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py --daily-traces /tmp/daily-synthetic-traces.json -q tests/test_daily_eval_manifest.py::test_manifest_freezes_twenty_native_cases_and_full_target
```

The latter verifies trace integrity and an explicit zero-skip pytest tier. It is
not full-spec/provider/operator acceptance. The canonical project verifier's
daily runner registers the new tests and retains its existing strict guard.
Use package-specific nodes during development; no full historical suite.
