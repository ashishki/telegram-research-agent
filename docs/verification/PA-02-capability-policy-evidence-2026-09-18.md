# PA-02 capability-policy evidence — 2026-09-19

Status: locally verified, synthetic/offline PA-02 implementation through
`779454705928e90a9ecf922ab0bdc3f11f4c17ab`. This receipt supersedes the
earlier provisional PA-02 counts and review handoffs. It does **not** change
the PA design's mechanical `review_required` state, record formal Playbook or
human approval, enable an account/provider/job, or claim a live/release result.

## Implemented local boundary

- A metadata-only, in-memory capability registry matches exact owner,
  connection, capability, resource, operation, data class, purpose, provider,
  active revision and one-use budget before PA-02 transport. Constructor-bypassed
  or duck-typed policy/request objects, truthy non-boolean fallback values, and
  boolean grant revisions fail closed; registry copies seal caller-held grant,
  provider-policy and reservation-request data from later mutation.
- Anthropic permits only `user_provided` input before client construction.
  OpenAI rejects a caller-supplied transport client and unconditionally omits
  private archive context pending PA-04 repository-selected provenance.
- Telegram voice permits only exact fixed `getFile` and byte-download URLs
  (origin/path/query/method/token/file binding), rejects redirects and
  mismatched returned `file_id`, and retains downloaded bytes only in memory.
- PA result delivery is an exact short-lived private reply envelope. `run_bot()`
  defaults to the PA-safe runtime; historical legacy polling is opt-in by an
  explicit `legacy` mode. Active PA text/voice/callback paths use the delivery
  boundary and default-deny UTD/legacy callback mutations.

The registry is intentionally not a durable grant source. There is no
operator-issued grant UI, provider integration proof, runtime credential use,
production database mutation, live Telegram polling, job enablement or release
claim in this slice.

## Final verification

All commands below used the writable implementation environment, Python
`3.10.12`, `PYTHONPATH=src` and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` where shown.
Fixtures contain synthetic identifiers only.

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_assistant_grant_codec.py tests/test_assistant_permissions.py \
  tests/test_assistant_egress.py tests/test_llm_client.py \
  tests/test_openai_provider.py tests/test_voice_transcription.py \
  tests/test_prm_synthesis.py tests/test_prm_utd_dispatch.py \
  tests/test_prm_bot_dispatch.py tests/test_callbacks.py
# 181 passed in 46.38s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py fast-contract
# 503 passed in 130.88s (0:02:10)

python3 tools/check_personal_assistant_plan.py
# PA plan: 19 consistent slices; schemas, references, dependencies and context limits passed.
# Design state: review_required; no product, human-approval or runtime claim.

python3 tools/playbook.py --check-pin
# Playbook pin verified; no model, hook or application runtime enabled.

python3 -m json.tool docs/design/PA.design.json >/dev/null
git diff --check
# passed; no output
```

The prohibited full historical pytest suite was not run. Read-only reviewers
could not create a temporary directory, so their pytest attempts are recorded
as an environment limitation rather than passing test evidence; their focused
no-write probes and source audits are not substitutes for the writable results
above.

## Independent review and remediation record

The initial requested Astra/high slice review was fresh/read-only via the
Playbook Role Runner at `24a2d86`; it returned `STOP_SHIP` and found four P1
egress defects. Its artifact hash is
`78f1080ca58b5cbb527d342385ad5e869425186f0ddb86c4b8782a8314bf42eb`.
The runner recorded `gpt-6-astra` / `high`; its report did not independently
attest model telemetry. Remediations continued through the scoped PA-02 chain,
ending at `7794547`.

Fresh direct read-only reviewer launches requested `gpt-5.6-terra` / `high`;
the launcher displayed that model/effort. Review reports state where model
telemetry was not independently exposed. The reports remain local reviewer
evidence, not approval:

| Reviewed SHA / scope | Result | Local report SHA-256 |
| --- | --- | --- |
| `f884a30` Telegram exact file binding | PASS | `c4c62b9c2a1f9a4dc54182a462a8f7c8fa7769e42eaf71c60ffa86ddd01e9914` |
| `f884a30` accumulated PA-00..PA-02 | STOP: fallback type bypass | `de8c74a90af73a9e0f4dc5dc3a3114a47fc5db618d98e49d8b7d60428e795a62` |
| `740557f` fallback flags | STOP: duck-typed ingress | `1771e7490aa6c51dca168ed6a3c5861fac01156324aad7a18b59081694de4d76` |
| `ed8bacb` registry ingress | STOP: caller-held mutation | `040093db2cfecb87e0bcad97a3fa72ac83fa04da6016241cac8481dbf56dec44` |
| `5ed2476` sealed inputs | STOP: boolean revision | `f1f27e719601564d7c7a3be8a1ce77ccfe6fa64974563a1674b19bc40748f2b2` |
| `b839fb5` revision remediation | ADVISORY, no P0/P1 | `86dc3ad0303e8ccee62a6f740154d623bb611cde02c097c943dfde73b42ae05b` |
| `7794547` safe `run_bot` default | ADVISORY, no P0/P1 | `26279794f2e22fdce4f0b4394bc3b825646c0aa30176e40f8dd2ac522a535583` |
| `7794547` final accumulated PA-00..PA-02 | ADVISORY, no P0/P1 | `157e963831e842a74786073bf407baf9a1f4f63fc9cba9cb1cada5eabb690dc2` |

The final accumulated review records one P2 compatibility debt: the two
historical `dispatch_command` facades retain a `legacy` default, but no active
PA production entrypoint reaches that omission. A future compatibility cleanup
should require a mode or default those facades to `prm_assistant`; it is not
represented as fixed here.

## Remaining gates and programme handoff

- Formal feature-design state remains `review_required`; owner direction and
  PA-00 acceptance do not overwrite that mechanical record.
- Private archive egress stays denied until PA-04 selected-evidence provenance.
- Durable voice/delivery unknown-outcome idempotency and reconciliation are not
  provided by PA-02. No automatic retry is enabled; PA-13/PA-15 own the durable
  action/media lifecycle.
- Real provider/account/Telegram integration, operator usefulness and release
  evidence remain separate external/human gates.

PA-03 is dependency-ready. It must implement the complete conversational-state
and plain-language confirmation slice under its own tests/evidence, without
reclassifying PA-00's callback safety or PA-02's policy boundary as product
acceptance. The two pre-existing untracked local files were not staged.
