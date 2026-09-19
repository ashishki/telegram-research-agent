# PA-06 bounded deep-research evidence

Date: 2026-09-19
Branch: `docs/personal-assistant-blueprint-playbook-20260918`
Implementation commits under review: `5b8b53b`, `3b5189b`, `cd47dde`,
`4ae05a2`, `af24451`, `7740a3b`, `f9089ca2197205b3838bc10db92c5691c1fdb4a1`,
`120395790fcd728c98d482def304ffe15f42b5e2`

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
- `DeepResearchRequest` is the explicit active-application ingress that builds
  that plan from the current request plus bounded archive/public/GitHub fields.
  Plain chat does not construct it and therefore cannot become an agent loop.
- Public and GitHub work consume sealed parent-side PA-02 scopes before the
  worker receives its start signal. Unknown, non-finite or exhausted tariff
  data prevents provider transport and leaves cost receipts JSON-finite.
- Deadline/cancel kills in-flight worker processes. A post-authorization
  outcome is deliberately not retried from a checkpoint, because egress may
  already have happened. A pre-start cancellation can resume only with the
  same process-signed receipt and matching plan/source scope.
- Checkpoints HMAC-bind the plan, archive-query fingerprint, public grant and
  resource/revision scopes, GitHub repository/grant scope, and completed step
  data. Forged or mismatched checkpoints are rejected before a reader/provider
  call; the active application returns a safe partial boundary instead of
  exposing supplied facts.
- The current inbound query is normalized and fingerprint-matched to the plan
  before checkpoint validation, archive reading, tariff lookup, cost
  reservation, authorization preflight or provider calls. A different request
  receives a typed `request_context_mismatch` partial refusal with no source or
  reservation use.
- User-facing research keeps verified facts, labelled non-fact inferences and
  conditional project recommendations separate. A factual claim verifier plus
  a typed-category contract controls publication; failure renders only the
  established evidence-only fallback.
- A requested project label is preserved only as `unverified_user_input` and
  never appears in the recommendation statement. The recommendation is a
  conditional suggestion tied to checked `repository@commit`, two cited facts
  and human confirmation; it is not a verified local project descriptor.

## Focused verification

Commands run against the working tree containing the registered PA-06 suite:
Tested implementation SHA: `120395790fcd728c98d482def304ffe15f42b5e2`.

```text
python3 -m pytest -q tests/test_assistant_research.py
# 26 passed in 5.39s

python3 tools/test_tiers.py focused-prm
# 390 passed in 128.70s
```

The dedicated offline holdouts cover permitted-source aggregation, local-only
gap expansion, public provider failure, unpriced/over-budget pre-transport
refusal, repository identity mismatch, repository instruction rejection,
hard timeout/cancel process termination, unsupported-platform default-deny,
checkpoint forgery/scope/data tampering, same-process pre-start resume, and
the active application's evidence-only fallback. Fixture passes do not prove
live provider integration, provider billing, operator usefulness, durable
restart recovery or actual GitHub/public-web access.

The added three-value holdout supplies `NaN`, positive infinity and negative
infinity as a public-provider quote under a zero budget. Each is recorded as
`unknown_price`, makes zero provider calls, abandons every sealed public
authorization before worker preflight, and leaves both consumed cost and the
tariff list finite/empty. `ResearchBudget` also rejects each non-finite
maximum, so a caller cannot construct an unbounded ledger with such a limit.

## Independent-review history and remaining gate

Fresh read-only Terra 5.6/high `slice_review` runs found and drove remediations
at `5b8b53b` (run `20260919T041940Z-slice_review-250eb5c4`), `3b5189b`
(`20260919T043132Z-slice_review-76ac9a53`), `4ae05a2`
(`20260919T064845Z-slice_review-c008021f`), `af24451`
(`20260919T070458Z-slice_review-93af1062`) and `0f61711`
(`20260919T071634Z-slice_review-ef4a9e48`). The last report's P1 was a plan
being usable for a different inbound request; the request-fingerprint refusal
and its initial/resume/application zero-call holdouts above remediate it. A
second P1 found at `7740a3b` (run
`20260919T072409Z-slice_review-4e47cf5b`) was missing active plan
construction; `DeepResearchRequest` and the unverified-label restriction above
remediate it. The fresh runner `20260919T073445Z-slice_review-68afc9dc`
reviewed `197bd1ce50b8c7fcde7e59832627f2def6ff5e86`, requested and observed
`gpt-5.6-terra` / `high` in a validated read-only run, and returned
`STOP_SHIP` P1 for non-finite cost quotes (report SHA-256
`7246ab18b7f78a0dbe7b5c2d8236f8ea724acf26a29926db28e27ce0f1db5a70`).
Commit `120395790fcd728c98d482def304ffe15f42b5e2` remediates that P1 with the
three adversarial quote values and non-finite budget-limit holdouts above. A
fresh Terra/high recheck is still required on that exact commit. No human
acceptance, release approval or live-runtime authorization is claimed by this
receipt.

Next command:

```text
python3 tools/run_codex_role.py run --root . --task PA-06 --feature-id PA \
  --slice-id PA-06 --role slice_review --model gpt-5.6-terra \
  --reasoning-effort high --timeout-seconds 1800 --no-publish
```
