# Current Session Handoff

Updated: 2026-09-20
Workstream: PA — full Personal AI Assistant, not an MVP
Branch: `docs/personal-assistant-blueprint-playbook-20260918`
Baseline: `f011d3b8641aab862f29b8e975ef2d5e647bc89c`
Last PA-02 code SHA: `779454705928e90a9ecf922ab0bdc3f11f4c17ab`
Playbook pin: `d570163ab17ec3b4245187c778f1e8d89af9690f`

## Authority and current boundary

The owner directed implementation through dependency-ready slices and accepted
PA-00, but that does not alter the formal PA design record. The paired design
in `docs/design/PA.md` / `docs/design/PA.design.json` remains mechanically
`review_required` because of the historic STOP_SHIP artifact. Do not hand-edit
Playbook artifacts or describe the design as formally approved.

PA-00 technical evidence is
`docs/verification/PA-00-technical-evidence-2026-09-18.md`. PA-01 is the
published contracts foundation. PA-02 is locally synthetic/offline verified at
the SHA above; its final evidence is
`docs/verification/PA-02-capability-policy-evidence-2026-09-18.md`.

PA-02 P0/P1 boundary findings are remediated and independently rechecked. The
final accumulated PA-00..PA-02 Deep Review is `ADVISORY`: two historical
compatibility dispatch facades retain a legacy default but have no active PA
production entrypoint. Preserve this P2 debt; do not portray it as resolved.

No production DB migration, job, timer, release action or full historical
pytest suite is authorized. Preserve the two untracked local files. A single
owner-authorized, time-bounded manual PA-safe Telegram polling attempt was
made on 2026-09-19 using the documented secret path; it skipped migrations,
was stopped cleanly, and the pre-existing service was restored. It produced no
test brief or human-review receipt, so it grants no continuing live authority.

## Current slice: PA-09 local durable watch contracts

PA-08 is locally complete and published; do not repeat its review. PA-09's
local contract is at `289269d` plus the final evidence/handoff commit. It adds
explicit-path SQLite watch subscriptions/jobs, exact private-owner
preview/confirm for creation and consent-bearing revision, independently scoped
watch collection/delivery grants, material-change fingerprints, source-bound
deadline stage recalculation, quiet/DST handling, leases/restart records,
receipts, fail-closed unknown-send reconciliation and idempotent feedback.
It deliberately has no default DB, scheduler, source collector, Telegram
client, provider, account, timer or deployment path.

The dedicated PA-09 tests cover version churn/reversal, source-deadline
forward/backward recalculation, quiet hours/DST, private ownership, revocation,
same-lease double send, pause/revision ordering, restart, unknown reconciliation
and duplicate/concurrent feedback. The required local tier passed at the final
code SHA: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py
focused-prm` — `470 passed in 93.81s`.

Fresh read-only `gpt-5.6-terra`/`high` slice reviews were run through the
pinned Role Runner. The final review of `289269d` resolves local code findings
but remains `STOP_SHIP` solely because PA-09 requires runtime/observable
delivery verification, while this owner-authorized slice explicitly forbids
that integration. Its report is
`docs/verification/PA-09-slice-deadline-289269d.md`. This is an open external
acceptance gate, not authority to enable a service or to claim watches arrive
reliably. The design remains mechanically `review_required`; no human/runtime
acceptance, release, delivery or provider authority is inferred.

The checkpoints below are historical dependency evidence. The owner's newer
quality amendment governs current local work; live/runtime gates remain.

PA-03 is locally tested at `081dded92b00bdaa822a6f6c0efbe8ae7ab86861` with
evidence at `docs/verification/PA-03-conversation-evidence-2026-09-19.md`.
Its initial Terra/high `slice_review` found three P1s; the scoped remediation
was independently rechecked at the same model/effort and returned `ADVISORY`.
Active ingress no longer uses legacy keyword state; model access is a typed
PA-02 reservation injected per private turn; and confirmation requires a
canonical equal private tuple. The new state is ephemeral (restart clears it),
object-bound, and fails closed for plain `yes` until PA-13 supplies
authoritative proposal/version loading and execution reconciliation. The model
receives only current direct user text, never archive/history/old response
context.

PA-03 has no formal acceptance claim. Keep its three advisory follow-ups open:
inactive legacy helper ownership, response-reference/version binding for archive
refinement, and a narrow dialogue-disable switch before authorized runtime.
PA-04 has locally tested remediation and evidence at
`docs/verification/PA-04-archive-synthesis-evidence-2026-09-19.md`. It binds
the selected local archive contract to bounded support spans, carries only a
typed paired PA-02 OpenAI text/context reservation, verifies citations,
relation order and negation polarity, and records safe retrieval/generation
measurements. The owner-requested Astra/high review found initial P1s; three
fresh Terra/high P1 remediations then converged to the final fresh Terra/high
`ADVISORY` review on `c4f828c`. Do not call PA-04 formally accepted: the
mechanical design status remains `review_required` due to the historic
STOP_SHIP artifact, and the final review grants no human acceptance, runtime
authorization or release approval. Keep the following advisory debt visible:
pre-reserved pair abandonment on exceptional/skipped application paths; an
active `run_bot` group/non-private non-invocation regression; offline holdouts
are application wiring rather than FTS-quality recall; and `ResearchResult`
remains deferred behind the established `AssistantResult.payload` DTO.

PA-05 implementation is locally verified at `7aeb66e`; its evidence is
`docs/verification/PA-05-controlled-web-evidence-2026-09-19.md`. It adds an
on-demand grant-gated public search/fetch/evidence route without widening the
legacy UTD allowlist: a separate minimized query is digest-bound to typed
PA-02 public scopes, and the default application has no web adapter. Fixture
tests cover source-only evidence, stale/partial/conflicting coverage,
query-substitution refusal, SSRF/redirect/DNS guards and injected source text;
they are not live-provider evidence. PA-05 remains unaccepted in the task
registry and does not change the mechanical `review_required` design state.

PA-06 may proceed on this local dependency checkpoint. No production DB, live
account/provider, credential, live job, timer or deployment is authorized.
The owner explicitly authorized one narrow 2026-09-19 scope amendment:
`tools/test_tiers.py` may register the dedicated PA-06 holdout suite in
`focused-prm`. This does not change the mechanical design `review_required`
status or authorize Redis, durable workers/jobs, a database, credentials or
live-provider activity.
Accumulate the next Deep Review at the declared PA-04..PA-06 boundary; do not
schedule a new review earlier absent an immediate safety trigger.

For each slice: add focused positive/negative tests, run the smallest relevant
existing tier, record evidence that distinguishes fixtures from integrations,
make a scoped commit and push. Use a fresh independent read-only reviewer for
P0/P1 rechecks; batch Deep Review at the declared phase boundaries unless an
immediate safety boundary changes. Reviewer launch records requested model and
effort; lack of reviewer telemetry is a limitation, never approval.

Useful initial checks:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
python3 tools/playbook.py --check-pin
python3 tools/check_personal_assistant_plan.py
```

The full programme remains Chat, real AI Search, beautiful weekly Briefs,
Watch and confirmed Act across PA-00..PA-18. Continue safe independent work;
stop only at a real human/security/credential/live-action gate.
