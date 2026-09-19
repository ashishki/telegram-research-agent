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

No production DB migration, job, timer, release action or full historical
pytest suite is authorized. Preserve the two untracked local files. A single
owner-authorized, time-bounded manual PA-safe Telegram polling attempt was
made on 2026-09-19 using the documented secret path; it skipped migrations,
was stopped cleanly, and the pre-existing service was restored. It produced no
test brief or human-review receipt, so it grants no continuing live authority.

## Current slice: PA-08 private report views and exports

PA-07 is complete as a local dependency checkpoint. Its final Terra/high
recheck at `065033c` found no further local P0/P1; do not repeat that review.
The open provider/runtime, private Telegram/mobile and owner-content acceptance
gate is still an acceptance/release boundary, not authority to start a service
or collect live evidence.

PA-08 projects one immutable, owner-scoped `BriefDocument` into static HTML,
PDF and Markdown. Each artifact carries the exact `brief_id`, version, content
digest and ordered source URLs from the stored object; rendering must not
retrieve, generate facts, persist an export, send it, create a public link, or
call a provider. HTML has a restrictive CSP and no executable/tracking
resources. Its mobile/dark/print CSS preserves the editorial hierarchy, caveat,
source timeline and coverage table; a chart is omitted because this document
has no comparable measurement that could justify one.

The local reader uses PA-07's exact persisted owner/version lookup. It issues
an opaque process-local handle for at most 20 minutes, then rechecks the
canonical private tuple and stored content digest before every render. Restart,
wrong owner, altered version/digest, expiry, malformed format and deleted or
tampered history all fail closed. A sharing request stops at an exact rendered
content and recipient-label preview with `preview_only_no_delivery`; there is
no delivery implementation in this slice.

The preferred local PDF backend is the declared WeasyPrint dependency with an
external-resource-denying fetcher. The current environment's WeasyPrint/pydyf
pair imports but fails before a PDF is created, so the renderer falls back only
to an in-memory Unicode PDF projection with an embedded local font. It does
not use a network or change dependencies. Record the backend limitation in the
PA-08 evidence; actual rendered PDF/mobile owner inspection remains a required
external acceptance gate.

Run `tests/test_assistant_report_exports.py` and
`tests/test_assistant_report_access.py`, then `python tools/test_tiers.py
fast-contract`. Record the exact scoped commit, all commands/results, and a
fresh independent Terra/high PA-08 slice review in
`docs/verification/PA-08-report-export-evidence-2026-09-19.md`. The design
remains mechanically `review_required`; no human approval is inferred.

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
