# Review Policy — PA / PAI

Updated: 2026-10-08. Pin: d570163ab17ec3b4245187c778f1e8d89af9690f.

## Authority and provenance

The current implementer uses the active session model/reasoning mode with no
programme override. It never reviews its own work. Independent reviewers are
fresh and read-only, do not fix/commit/push, and cannot grant human acceptance.
The owner’s [2026-09-23 amendment](CODEX_PROMPT.before-pai-20261006.md#owner-amendment-2026-09-23--solution-first-non-codex-judge)
selects a non-Codex reviewer via OpenCode Go, default mimo-v2.6-pro, and batches
review at phase boundaries. It supersedes the older Terra/high prescription in
AGENTS/adoption/prompts. This is reviewer selection, not a new paid-call budget
or permission to send private data. The 2026-10-06 Sol prompt explicitly keeps
paid model calls behind scoped authority. The owner approved the exact brief and two initial Mimo reviews; both attempts
failed without verdict. A later owner request authorized one tiny diagnostic,
which confirmed Mimo connectivity/schema. The owner resumed the goal and authorized the recommended total 30-call cap
for local PAI-00..26. Actual call consumption, including failures/diagnostics, is recorded in
docs/verification/PAI-progress.md; read the current count before each request. The owner
approved design/recheck output up to 16000 tokens and deadlines up to 900 s.
Defaults remain 8000/300; no automatic retries or model substitution.
Per-call bounds/private-source exclusions persist; no credential availability scans.

Owner amendments on 2026-10-07 extended the count to 33; on 2026-10-08 the
owner explicitly authorized “разврешаю увеличивать по потребности”. Necessary
review/recheck budget increases in the existing local PAI scope are now
authorized on an ongoing basis. Allocate/log each fresh bounded request, count
failed/inconsistent responses too, and do not restart per-call permission loops.
Provider/model/data exclusions remain unchanged. The owner separately directed
review-key lookup to Georgia-Community-Navigator; that reviewed key location is
now known, without permission to scan other credentials or send private data.
The existing observed thinking-disabled mode is available explicitly in the
native OpenCode route; record requested mode separately from actual telemetry.
These amendments grant neither product-provider spending nor human design,
live account, background runtime, production or release authority.

## Roles, runners and receipt compatibility

| Role | Required route/evidence | Current integration |
| --- | --- | --- |
| Product/program design; slice; maintainability | Pinned Role Runner, independent process, hash-bound role receipt | local --provider opencode-go backend supports product/program design records; native Codex receipt schema stays separate; slice/maintainability extension pending |
| Accumulated Deep Review | Fresh non-Codex process, exact SHA/diff and hash, frozen findings | tools/mimo_code_review.py reviews a committed Git range; advisory JSON/Markdown, not a governed role receipt |
| Test Critic; privacy/security | Fresh independent read-only reviewer, bounded inputs, identity and findings | Non-Codex governed role adapter is pending; no self-review substitution |
| Text/content/visual judges | Explicit provider scope/budget and deterministic dataset/render provenance | Existing judge tools are advisory; neither safety nor release approval |

Do not label a Mimo verdict as a successful Role Runner execution or synthesize
runner telemetry/approval fields. Rendering a role prompt is preparation only.
The owner retained Mimo on 2026-10-06. The local Role Runner now routes
explicit --provider opencode-go to tools/opencode_role_review.py for product/
program design roles. It checks the real pinned task/feature/planning gate,
bounded input, one explicit budgeted call, observed model/complete JSON,
P0/P1 verdict consistency and document/HEAD drift before publication.
The caller is a fresh separate Python process; the model has no tools or writes.

Evidence uses assistant.opencode_design_review.v1, records actual provider,
requested/observed model/effort, SHA and input/report hashes, and publishes via
the genuine pinned write_design_review_record consumer with reviewer_binding
opencode_go:<result-path>. Synthetic tests confirm that the pinned parser
accepts that generic design record and rejects stale hashes. These are not
codex_role_run traces; no Codex events or human approval fields are produced.
Independent backend risk review remains pending; authorized public/synthetic
bootstrap calls do not accept the backend or the feature design.

Current pinned feature_workflow review would manufacture a codex_exec binding
when it sees a report at its default report path. Therefore the OpenCode backend
keeps reports in its distinct immutable run directory and writes generic
design records directly through the pinned consumer. Do not copy them to the
default Codex report path or refresh them through that old projection. The
approve workflow reads the hash-bound generic records via the real consumer.
No upstream pin or approval checker was altered to accommodate this route.
Slice/maintainability and other non-Codex roles remain future scoped extension,
not silently supported. No-provider run is denied instead of falling back to
Codex. Legacy verify/help remains available for historical receipt inspection.

## Review cadence and risk

PAI phase boundaries: A=00..01, B=02..06, C=07..09, D=10..15,
E=16..20, F=21..26, G=27..29. Required reviews examine accumulated changes and
specific acceptance evidence; do not launch all reviewers for every small patch.
Immediate review applies before exercising new egress, OAuth/secrets, retention,
confirmation/writes, scheduling or recovery boundaries. Resolve P0/P1 and obtain
an independent recheck before dependent work. Preserve unreviewed limitations.
Historical PA phase receipts remain references to their exact SHA, not approval
of a new PAI design. Existing legacy/domain gates remain when that surface changes.

Product/program design review precedes hash-bound human design approval.
High-risk slice acceptance, account/institution grants, paid egress, background
jobs, production migration/deploy and release are separate decisions. Missing
review remains pending; local synthetic passes never fill that gap.

## Evidence

Record requested/observed provider/model/effort (unknown when unavailable), runner
version, reviewed commit and diff/input hashes, command and exit, findings and
recheck. Distinguish acceptance tests, regressions, fixtures, real provider I/O,
actual rendered views and human usefulness. Full historical pytest is prohibited.
No private corpus, account payload or credentials in reviewer packets or Git.

## Enforced independent tooling gate

Owner-authorized PAI-00 maintenance is reviewed separately with --tooling-review.
The critical source list includes policy, bridge/runner/transport/checker,
finalizer, strict acceptance runner and their tests. New design requests and
record aggregation require a genuine independent tooling PASS/ADVISORY bound to
unchanged hashes. Missing, altered, partial, STOP_SHIP or contradictory evidence
blocks before credentials/provider calls. Historical bootstrap reports and
synthetic diagnostics cannot unlock this gate. Any critical-source/policy change
requires fresh independent re-audit before design receipts are consumed.
This technical gate never grants human design, live or release authority.

The supported approval route is tools/playbook.py and its repository proxies.
Direct upstream imports/execution by a privileged operator are outside this
route; local hashes do not supply signed or append-only evidence. Universal
enforcement inside arbitrary direct kit consumers needs the separately reviewed
upstream hook/pin proposal in verification/PAI-upstream-gate-proposal.md.
PAI role acceptance requires all four genuine phase parts through the complete
aggregator; a single full-design request cannot publish a PAI role record.
Scoped strict test runs report scoped verification only; full-spec acceptance
requires --require-spec-matrix, as bound in the pai-complete tier.
