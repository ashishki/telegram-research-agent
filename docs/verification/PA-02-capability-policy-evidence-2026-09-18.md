# PA-02 capability policy evidence — 2026-09-18

Status: Astra slice review found P1 boundary defects in the first PA-02 commit;
the scoped remediation below is locally verified and awaits a fresh Terra
recheck. This receipt does not change the preserved mechanical
`review_required` design state, record a formal Playbook approval, enable an
account/provider/job, or claim a live or release result.

## Authority and boundaries

The active owner instruction explicitly directs PA-01 and the wider programme
to continue after design approval while preserving the historic STOP_SHIP-derived
Playbook state and forbidding manual `.playbook-artifacts` edits. The normal
Feature Workflow remains mechanically blocked at `needs_input`; no artifact was
hand-edited. The owner subsequently requested an Astra/high review, fixes, and
a fresh Terra/high recheck at the accumulated PA-00..PA-02 boundary.

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
and a bounded one-use operation reservation. A reservation retains its exact
owner, optional connection, resource, grant ID and revision and revalidates the
current registry at consumption. Reservations are conservatively spent before a
transport request, including on an adapter error/unknown outcome; automatic
client/SDK retry is disabled, so retry needs explicit reconciliation and a new
valid decision rather than reuse of prior authorization.

Anthropic text/vision, the isolated OpenAI adapter, PRM archive synthesis, and
voice now deny before client/network access without their matching reservation.
OpenAI archive context needs a distinct `private_archive` grant and is omitted
without it. Telegram voice download needs its own read grant in addition to the
OpenAI transcription grant; `getFile` and raw file download each consume a
separate read reservation. The active bot has no grant source yet, so an actual
voice request fails closed before Telegram/OpenAI network I/O; mocked transport
tests do not prove a live bot path.

The pure scope formatter reports capability/resource/operation/data/provider
scope and explicitly says that a provider key is not consent. It has no active
operator-facing grant source or permission screen yet, so it is not evidence of
a live UI flow. PA-16 still owns measured monetary/model routing budgets, and
PA-13 still owns durable external-action reconciliation; neither is claimed
here.

## Independent Astra slice review and scoped remediation

Role Runner completed a fresh read-only `slice_review` for PA-02 at
`24a2d86c8c633282f7b77ce875865497bd084077`:

```text
python3 tools/run_codex_role.py run --root . --task PA-02 --feature-id PA \
  --slice-id PA-02 --role slice_review --model gpt-6-astra \
  --reasoning-effort high --timeout-seconds 900 \
  --run-id 20260918Tastra6h-pa02-slice
# validated; SLICE_REVIEW: STOP_SHIP
```

The Runner records `gpt-6-astra` / `high`, CLI `codex-cli 0.154.0`, read-only
sandbox, exit `0`, 49 valid JSONL events and no reviewer workspace drift. It is
hash-linked under `.playbook-artifacts/runs/20260918Tastra6h-pa02-slice/`; the
report hash is `78f1080ca58b5cbb527d342385ad5e869425186f0ddb86c4b8782a8314bf42eb`.
The reviewer report itself notes that it did not independently observe a model
identity; the Runner provenance is execution evidence, not human approval or a
replacement for the required Terra recheck.

Its four P1 findings were remediated in the scoped change:

- reservations now revalidate revoke, expiry and revision at transport
  consumption;
- decisions retain and adapters compare owner, connection and resource with the
  actual adapter operation;
- Anthropic/OpenAI SDK retries and the client retry loop are disabled for a
  granted request, so an unknown outcome stops after one transport attempt;
- voice preflights transcription without consuming it, then consumes it once at
  the transcription HTTP call, while its two Telegram transport calls each use
  their own read reservation.

The P2 note about an operator-facing scope/revocation path remains open and is
not represented as completed product UI.

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
# 40 passed in 21.03s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py fast-contract
# 415 passed in 189.36s (0:03:09)

python3 tools/check_personal_assistant_plan.py
# PA plan: 19 consistent slices; schemas, references, dependencies and context limits passed.
# Design state: review_required; no product, human-approval or runtime claim.

git diff --check
# no output; passed
```

The prohibited full historical pytest suite was not run. The Astra reviewer was
read-only; no model/provider was called by these fixtures.

## Remaining gates and next command

The original scoped implementation commit is
`2c51c19ebbe450c10466c215cd22cc71d21b5bfb`
(`feat(pa02): enforce capability-bound egress`) and was pushed to
`origin/docs/personal-assistant-blueprint-playbook-20260918`. Its 17 files are
the policy code, exact adapter integrations, tests/tier wiring, PA-02 design,
handoff and this evidence; neither pre-existing untracked local file was staged.

The scoped remediation commit is
`7019000a503f47ee6f31cbbb79c653514961c8aa`
(`fix(pa02): close capability egress review findings`). It changes only PA-02
policy/adapters, their synthetic tests and the PA-02 design; it is not a live
grant store, production migration, provider request or permission-screen claim.

Record the scoped remediation commit and publication SHA after this evidence is
committed. Do not mark PA-02 complete until a fresh Terra/high recheck confirms
the changed scope and any required human acceptance is recorded. PA-03 remains
the next dependency-ready implementation slice only after that recheck; its
plain-language confirmation remains separate from PA-00's callback safety and
PA-02's authorization boundary.
