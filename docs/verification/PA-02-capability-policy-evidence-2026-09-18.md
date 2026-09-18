# PA-02 capability policy evidence — 2026-09-18

Status: locally verified PA-02 implementation, pending the required accumulated
PA-00..PA-02 Deep Review and any applicable human acceptance. This receipt does
not change the preserved mechanical `review_required` design state, record a
formal Playbook approval, enable an account/provider/job, or claim a live or
release result.

## Authority and boundaries

The active owner instruction explicitly directs PA-01 and the wider programme
to continue after design approval while preserving the historic STOP_SHIP-derived
Playbook state and forbidding manual `.playbook-artifacts` edits. The normal
Feature Workflow remains mechanically blocked at `needs_input`; no artifact was
hand-edited. The owner also directed that no new reviewer run now; the required
Deep Review is accumulated at the PA-00..PA-02 boundary.

The implementation is offline and default-deny. It reads no credentials or
grants from environment, database or account state; a provider key and existing
feature toggle are technical adapter prerequisites only, never authorization.
No production database, account, provider request, Telegram request, service,
timer, archive content or `.env` was accessed or changed. The two pre-existing
untracked local files remain untouched.

## Test-first result and implemented boundary

The intended pre-implementation red case was:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_permissions.py tests/test_assistant_egress.py
# 2 collection errors: ModuleNotFoundError: No module named 'prm.capabilities'
```

The resulting implementation adds an in-memory, metadata-only
`CapabilityRegistry` with revision-bound grants; exact owner/resource/
operation/data-class/purpose/provider matching; validity/revoke/fallback denial;
and a bounded one-use operation reservation. Reservations are conservatively
spent before the adapter request, including on an adapter error/unknown outcome,
so retry needs a new valid decision rather than reusing a prior authorization.

Anthropic text/vision, the isolated OpenAI adapter, PRM archive synthesis, and
voice now deny before client/network access without their matching reservation.
OpenAI archive context needs a distinct `private_archive` grant and is omitted
without it. Telegram voice download needs its own read grant in addition to the
OpenAI transcription grant. The active bot has no grant source yet, so an actual
voice request fails closed before Telegram/OpenAI network I/O; mocked transport
tests do not prove a live bot path.

The UI helper reports capability/resource/operation/data/provider scope and
explicitly says that a provider key is not consent. PA-16 still owns measured
monetary/model routing budgets, and PA-13 still owns durable external-action
reconciliation; neither is claimed here.

## Commands and results

Environment: Python `3.10.12`; `PYTHONPATH=src` and
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` for pytest commands.

```text
python3 -m py_compile src/prm/capabilities.py src/prm/synthesis.py \
  src/llm/client.py src/llm/openai_provider.py src/bot/voice.py
# passed

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_permissions.py tests/test_assistant_egress.py \
  tests/test_llm_client.py tests/test_openai_provider.py \
  tests/test_voice_transcription.py tests/test_prm_synthesis.py
# 28 passed in 12.10s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py fast-contract
# 405 passed in 123.56s (0:02:03)

python3 tools/check_personal_assistant_plan.py
# PA plan: 19 consistent slices; schemas, references, dependencies and context limits passed.
# Design state: review_required; no product, human-approval or runtime claim.

git diff --check
# no output; passed
```

The prohibited full historical pytest suite was not run. No reviewer was
started; no model/provider was called by these fixtures.

## Remaining gates and next command

The scoped implementation commit is
`2c51c19ebbe450c10466c215cd22cc71d21b5bfb`
(`feat(pa02): enforce capability-bound egress`) and was pushed to
`origin/docs/personal-assistant-blueprint-playbook-20260918`. Its 17 files are
the policy code, exact adapter integrations, tests/tier wiring, PA-02 design,
handoff and this evidence; neither pre-existing untracked local file was staged.

Do not mark PA-02 complete until its accumulated foundation Deep Review and any
required human acceptance are recorded. The next implementation slice is PA-03:
`python3 tools/feature_workflow.py --root . plan --task PA-03`. Its
plain-language confirmation remains separate from PA-00's callback safety and
PA-02's authorization boundary.
