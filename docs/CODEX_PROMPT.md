# Current Session Handoff

Updated: 2026-09-19
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

No production DB, live Telegram polling, account/provider access, job, timer,
credential, `.env` or release action has been used or is authorized. Preserve
the two untracked local files. Do not run the full historical pytest suite.

## Current slice: PA-07 local BriefDocument handoff

PA-07 is locally implemented through `c1cd081` (with preceding scoped commits
`1f5a75a`, `a1f8001`, `de32184`, `447af21`, `d553f3b`, `44d2195`, `264bc5f`,
`d2163a1`, `f146925`, `dfa135f`, `ff6329e`, `fa1cc10`, `9603c28` and
`d9a684f`). It provides an immutable, inspectable source-backed
`BriefDocument`, a selected IANA-zone half-open period, coverage/deduplication/
conflict/importance-versus-urgency evidence, bounded visible report history,
and deterministic Telegram/report follow-ups. A request window is bound before
local archive candidate selection and rechecked afterwards. The Telegram full
view is reached by a one-time reply-keyboard text control that resolves only
against the current visible in-process report object.

The dispatcher keeps that visible report object in a bounded process-local
store across immediate commands; a process restart clears the projection and
prevents normal-language reconstruction of the old brief.

The owner explicitly amended this narrow PA-07 boundary on 2026-09-19 to
remediate two independent P1 findings: add owner-scoped, bounded immutable
BriefDocument history through the existing local SQLite schema path, and
register the two PA-07 suites in `focused-prm`. Visible conversation bindings
remain ephemeral: a new topic or process restart cannot resolve a normal
language follow-up without its current visible response. Durable lookup,
listing, writes and deletion each consume the canonical authenticated private
tuple plus exact `(brief_id, version)` where applicable, never a cross-chat or
latest-report catalogue. History is capped owner-wide, not only per report
identity. The migration is additive and is exercised only on a temporary test
database; do not access or migrate a production database.

This amendment does not authorize a durable job, worker, Redis, schedule,
export, live provider/account/credential action, Telegram polling or any
PA-08/PA-09 implementation. The direct PA-07 suites and `focused-prm` remain
required evidence.

The evidence record is
`docs/verification/PA-07-brief-document-evidence-2026-09-19.md`. Fresh
read-only Terra 5.6/high reviews found and drove the scoped remediations. The
latest recheck, `20260919T110742Z-slice_review-d305cf5c` against `ba84cd3`,
found no further code defect but returned `STOP_SHIP` for external acceptance
gates: actual authorized private Telegram/mobile rendering inspection and
human content review. Its read-only sandbox could not create pytest temporary
files; the exact current code was instead run successfully in the writable
workspace and recorded in the evidence. Do not claim that either external gate
is satisfied, or begin PA-08/PA-09. The design remains mechanically
`review_required`.

PA-06's local checkpoint below is historical context for PA-07's dependency;
do not treat it as an instruction to start PA-08 or PA-09.

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
