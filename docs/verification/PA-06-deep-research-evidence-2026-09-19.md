# PA-06 bounded deep-research evidence

Date: 2026-09-19
Branch: `docs/personal-assistant-blueprint-playbook-20260918`
Implementation commits under review: `5b8b53b`, `3b5189b`, `cd47dde`,
`4ae05a2`, `af24451`

## Scope and authority

PA-06 remains a local, offline implementation boundary. It uses no production
database, credential, live account/provider, live job, timer, Redis instance,
durable queue or deployment. The local worker is a short-lived Linux/fork
process supervisor only; PA-09 remains responsible for durable jobs and
restart recovery.

The owner explicitly authorized the following narrow scope amendment on
2026-09-19 after a Terra/high P1 finding: `tools/test_tiers.py` may register
the existing dedicated `tests/test_assistant_research.py` suite in the required
`focused-prm` tier. The amendment adds no runtime authority and does not alter
the mechanical design status, which remains `review_required` because of the
historic STOP_SHIP artifact.

## Implemented boundary

- A finite `ResearchPlan` coordinates one local archive query, independently
  scoped public research tasks, an optional read-only GitHub identity read, and
  at most one local-only gap expansion.
- Public and GitHub work consume sealed parent-side PA-02 scopes before the
  worker receives its start signal. Unknown tariff or exhausted cost budget
  prevents provider transport.
- Deadline/cancel kills in-flight worker processes. A post-authorization
  outcome is deliberately not retried from a checkpoint, because egress may
  already have happened. A pre-start cancellation can resume only with the
  same process-signed receipt and matching plan/source scope.
- Checkpoints HMAC-bind the plan, archive-query fingerprint, public grant and
  resource/revision scopes, GitHub repository/grant scope, and completed step
  data. Forged or mismatched checkpoints are rejected before a reader/provider
  call; the active application returns a safe partial boundary instead of
  exposing supplied facts.
- User-facing research keeps verified facts, labelled non-fact inferences and
  conditional project recommendations separate. A factual claim verifier plus
  a typed-category contract controls publication; failure renders only the
  established evidence-only fallback.

## Focused verification

Commands run against the working tree containing the registered PA-06 suite:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_assistant_research.py
# 17 passed in 3.19s

TMPDIR=<mktemp> PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 381 passed in 86.17s
```

The dedicated offline holdouts cover permitted-source aggregation, local-only
gap expansion, public provider failure, unpriced/over-budget pre-transport
refusal, repository identity mismatch, repository instruction rejection,
hard timeout/cancel process termination, unsupported-platform default-deny,
checkpoint forgery/scope/data tampering, same-process pre-start resume, and
the active application's evidence-only fallback. Fixture passes do not prove
live provider integration, provider billing, operator usefulness, durable
restart recovery or actual GitHub/public-web access.

## Independent-review history and remaining gate

Fresh read-only Terra 5.6/high `slice_review` runs found and drove remediations
at `5b8b53b` (run `20260919T041940Z-slice_review-250eb5c4`), `3b5189b`
(`20260919T043132Z-slice_review-76ac9a53`), `4ae05a2`
(`20260919T064845Z-slice_review-c008021f`), and `af24451`
(`20260919T070458Z-slice_review-93af1062`). The last report's P1 was the
missing mandatory-tier registration; it is the subject of the authorized
amendment and commands above. A fresh Terra/high recheck is still required on
the commit that adds this registration and evidence. No human acceptance,
release approval or live-runtime authorization is claimed by this receipt.

Next command:

```text
python3 tools/run_codex_role.py run --root . --task PA-06 --feature-id PA \
  --slice-id PA-06 --role slice_review --model gpt-5.6-terra \
  --reasoning-effort high --timeout-seconds 1800 --no-publish
```
