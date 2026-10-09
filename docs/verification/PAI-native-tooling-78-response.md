# Native GLM tooling audit78 — incomplete; explicit max prepared

2026-10-09. Reviewed SHA1719bb7c06eaa1dc9d6ddfb2d7390c4535984f0c in the
assigned branch. The session now permits Git writes/network; previous environment
restrictions remain historical evidence, not current blockers. Scoped GLM cutover
was committed after all five source hashes matched the135-pass evidence.

Actual command:

```bash
.venv-pai/bin/python tools/run_codex_role.py run --provider opencode-go --model glm-5.3 --root . --task PAI-00 --feature-id PAI --role program_design_review --tooling-review --allow-provider-egress --call-cap 1 --output-token-cap 16000 --timeout-seconds 900 --key-file /srv/openclaw-you/workspace/Georgia-Community-Navigator/secrets/openrouter_api_key
```

Exit2,238.047s. Actual provider-reported model glm-5.3, finish_reason=length;
usage43859 input/16000 completion/59859 total tokens. Requested effort not_requested;
observed effort unknown, cost unknown. No complete verdict/report/design record.
Actual failure and hashes are referenced in PAI-review-continuation-78.json.
78 calls consumed including failures; no automatic retry or model fallback.
Prior Mimo STOPs remain unchanged. Neither truncated response nor implementer
interpretation supplies independent acceptance.

The owner then rejected the proposed low mode: “нет, делай макс, неп роблема”.
Local transport/CLI now support explicit reasoning_effort=max only for GLM.
Receipts distinguish requested effort from unverified actual effort. Low/high and
Mimo/max combinations fail before credentials; no GLM disabled-thinking field.
See [Z.ai's GLM-5.3 parameter documentation](https://docs.z.ai/guides/llm/glm-5.3).
The [OpenCode Go endpoint documentation](https://docs.opencode.ai/docs/go/) lists
the same Chat Completions endpoint; forwarding of reasoning_effort is unverified.

Larger GLM output caps64000/128000 are prepared with a separate owner-authority
guard; current maximum remains16000 pending the numerical choice. Larger streams
remain bounded64MiB wire/64KiB event/1MiB final text; reasoning text is discarded,
not logged or treated as a verdict. Mimo's bound remains16000. Request-time900s,
input200000 bytes, single call and source exclusions remain unchanged.

Scoped verification:

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_opencode_role_review.py tests/test_pai_acceptance_guard.py tests/test_playbook_bridge.py tests/test_pai_plan.py
```

Initial new-mode tests:3 failed/137 passed in7.71s. The three negative transport
assertions accidentally called setup_run's synthetic provider; capture the real
transport before installing that fixture. Guards/assertions unchanged. Corrected
max-only140 passed8.48s; expanded cap/stream/authority147 passed7.85s. These are
synthetic scoped tests, not current independent tooling or provider acceptance.
Exact logs/hashes/final preparation are recorded in PAI-validation-20261009-max.json.

Next: record the actual output-limit answer, commit exact inputs, then one fresh
native tooling audit79 with explicit max and that bounded cap. Future eight design
parts80..87 remain uninvoked until genuine accepted current tooling evidence; all
four parts per role must use one unchanged HEAD/design, then the pinned finalizer.
Human exact design, other governed role adapters, live/private/product-provider,
production/services/timers/release remain separate open gates.
