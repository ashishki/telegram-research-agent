# Mimo call protocol: Navigator source and actual verification

Date: 2026-10-06.
The owner asked to find the working Mimo invocation in Georgia Community Navigator.
That repository's main checkout is older; the working implementation is in
fix/dialogue-task-state-20260920 at commit 5f26418921246c3e24a967532225dfe3d274b1cb.

## Source inspected read-only

- evaluation/product/dialogue_eval.py, judge(), OpenCode Go branch.
- tools/opencode_judge_smoke.py.
- tools/calibrate_dialogue_judge.py.
- evaluation/product/dialogue_eval_budget.py.

No Navigator file, service or account was changed. No corpus, sessions, secret
values or private screenshots were read for this inspection.

The actual reference client sends separate system/user messages, a strict
json_schema response_format, its own user agent, a fresh UUID x-opencode-session,
and a 300 s judge timeout. The URL/model match the existing PA selection.
Our earlier helper sent one system message, json_object, a shared static session
ID and a shorter role timeout. Those are observed differences, not proof that
a particular difference caused either earlier HTTPError or timeout.

## Applied and tested

The shared Mimo helper now sends both roles, a fresh session identifier and the
native strict schema when supplied. The design backend supplies its real
verdict schema and defaults to bounded 300 s. Redirect/body-size denial,
observed-model/complete-verdict checks, P0/P1 rejection and no automatic retry
remain. The primary implementer model is unchanged. There is no Codex fallback.

Exact targeted command:
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_opencode_role_review.py tests/test_strategy_reviewer.py
Result: exit 0, 29 passed in 12.27 s.
The wire test checks both message roles, strict schema contents, distinct
32-character session IDs, 8000 output cap and 300 s timeout.
prepare-only still preserves every requirement and reports input below 200000
bytes. It does not read credentials or make a provider call.

## One actual diagnostic requested by the owner

Performed one bounded connectivity verification for the new explicit
find-the-working-Mimo-invocation request. Synthetic 102-byte input, 512 output
token cap, 120 s timeout, no retries, same selected endpoint/model and documented
key file used only for actual execution. This is a diagnostic scope; it does
not renew the exhausted initial two design-review calls.

Actual result: schema_ok. Observed model: mimo-v2.6-pro.
Usage: prompt_tokens 61, completion_tokens 51, total_tokens 112.
Raw prompt/response/error body and credential values were not printed or saved.
Safe result: .playbook-artifacts/opencode-connectivity/<run-id>/result.json.
valid_verdict=false: it proves authenticated connectivity and schema, not an
independent design review or permission to implement PAI-02.

There are now three actual Mimo requests: two failed design attempts on 07f2475
and this successful tiny diagnostic. Count failed/unknown attempts conservatively.
The follow-up overall 30/8-call budget question remains pending. Do not invent
a successful full-review verdict from the smoke or infer that cap from silence.
