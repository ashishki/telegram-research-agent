# PAI progress — current evidence

Updated: 2026-10-06
Branch: docs/personal-assistant-blueprint-playbook-20260918
Published code/tool checkpoint: a5cd3d2a2ea1b5152035ed5ed6d39f4e8e15033c.
Initial source: 8faee4232cb30e6b6f39cfbd974c151846f79da6.
Full programme remains unfinished; owner resumed the existing goal. Formal PA/PAI states are preserved; engineering
status below does not grant independent, human or runtime acceptance.

Current card: phase-B review, then PAI-07. PAI-02 locally verified under owner proceed instruction ADR-014.
Formal design states remain unchanged. Previous design-only stop no longer blocks local code.

Historical design preparation checkpoint: PAI-01. Draft/brief/planning are prepared and authorized.
Original complete product review returned STOP_SHIP; its two P1 findings were
independently resolved by a scoped PASS. Foundation program STOP_SHIP on a6a7d00 identified trust/no-skip gaps now fixed
locally; independent tooling/phase rechecks and complete design remain pending.
Owner authorized 30 total calls, 16000-token output and 900-second design deadlines.
Nineteen calls are consumed before the separate tooling audit.

| ID / PA-Refs | Engineering status | Code | Wiring | Tests | Review | Live | Human acceptance | Blocker / next |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PAI-00 / PA-00, PA-01, PA-18 | local_verified | instruction/tool/test and bounded Mimo design backend diff | current entrypoints inventoried; no product runtime added | focused-prm 620 pass; latest bridge/role/guard/plan/strategy suite 92 pass | phase-A independent review pending | none | none | PAI-01 brief/planning/review/design gate |
| PAI-01 / PA-01, PA-02, PA-09, PA-13, PA-16, PA-17 | in_progress | draft paired design + proposed ADR-013 | proposed topology only | pinned schema/mapping pass | two original product P1 independently resolved by scoped PASS; full review missing | none | none | brief/planning funded; complete independent reviews/exact design approval pending |
| PAI-02 / PA-01, PA-17 | local_verified | PostgreSQL target/UOW/versioned objects/migration | actual CLI, separate-process DB and dump/restore | 31 passed in 9.55 s; zero skips | phase-B pending | no production/account | none claimed | next PAI-03 |
| PAI-03 / PA-02, PA-16 | local_verified | shared PostgreSQL grants/counters/windows/operation ledger | existing transport-group helper plus guarded adapter call | 86 passed in 11.43 s; zero skips | phase-B pending | synthetic only | none claimed | next PAI-04 |
| PAI-04 / PA-00, PA-13 | local_verified | PostgreSQL proposals/confirmations/attempt receipts | execute_action dispatches explicit durable backend | 36 passed in 32.02 s; zero skips | phase-B pending | fake provider only | none claimed | next PAI-05 |
| PAI-05 / PA-03, PA-07, PA-14 | local_verified | serialized PostgreSQL navigation and immutable response refs | existing ConversationStore interface plus actual application injection | 26 passed in 9.03 s; zero skips | phase-B pending | synthetic only | none claimed | next PAI-06 |
| PAI-06 / PA-06, PA-09, PA-17 | local_verified | PostgreSQL fenced queue/checkpoints | actual separate process compute worker | 45 passed in 22.50 s; floor 652 passed | phase-B review next | no service enabled | none claimed | review then PAI-07 |
| PAI-07 / PA-03, PA-06, PA-09 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-05, PAI-06; PAI-01 design gate |
| PAI-08 / PA-09, PA-12 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-06, PAI-07; PAI-01 design gate |
| PAI-09 / PA-02, PA-09, PA-13 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-04, PAI-07, PAI-08; PAI-01 design gate |
| PAI-10 / PA-03, PA-16 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-03, PAI-05, PAI-07, PAI-09; PAI-01 design gate |
| PAI-11 / PA-04 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-10; PAI-01 design gate |
| PAI-12 / PA-05, PA-06 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-10, PAI-11; PAI-01 design gate |
| PAI-13 / PA-06 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-06, PAI-11, PAI-12; PAI-01 design gate |
| PAI-14 / PA-07, PA-09 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-05, PAI-08, PAI-09, PAI-11, PAI-13; PAI-01 design gate |
| PAI-15 / PA-08 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-07, PAI-14; PAI-01 design gate |
| PAI-16 / PA-02, PA-10, PA-11, PA-17 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-03, PAI-07; PAI-01 design gate |
| PAI-17 / PA-10 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-10, PAI-14, PAI-16; PAI-01 design gate |
| PAI-18 / PA-11 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-10, PAI-16; PAI-01 design gate |
| PAI-19 / PA-12 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-08, PAI-14, PAI-17, PAI-18; PAI-01 design gate |
| PAI-20 / PA-13 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-04, PAI-09, PAI-17, PAI-18; PAI-01 design gate |
| PAI-21 / PA-14 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-05, PAI-14, PAI-17; PAI-01 design gate |
| PAI-22 / PA-15 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-10, PAI-15, PAI-21; PAI-01 design gate |
| PAI-23 / PA-16 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-03, PAI-13, PAI-15, PAI-20, PAI-22; PAI-01 design gate |
| PAI-24 / PA-17 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-09, PAI-16, PAI-21, PAI-22, PAI-23; PAI-01 design gate |
| PAI-25 / PA-00, PA-17 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-02, PAI-04, PAI-05, PAI-08, PAI-21, PAI-24; PAI-01 design gate |
| PAI-26 / PA-18 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-15, PAI-19, PAI-20, PAI-22, PAI-23, PAI-24, PAI-25; PAI-01 design gate |
| PAI-27 / PA-02, PA-05, PA-09, PA-10, PA-11, PA-12, PA-13, PA-15, PA-16, PA-18 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-26; separate live/institution/budget/deploy scope |
| PAI-28 / PA-17, PA-18 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-25, PAI-27; separate live/institution/budget/deploy scope |
| PAI-29 / PA-18 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-28; separate live/institution/budget/deploy scope |
| PAI-30 / PA-16, PA-17 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-23, PAI-24, PAI-26; measured condition + new ADR |
| PAI-31 / PA-04, PA-17 | planned | existing PA contracts to reuse; no new PAI code | integration/restart/concurrency not demonstrated for PAI | new acceptance not run | none for new scope | none for new scope | none | PAI-11, PAI-25, PAI-26; measured condition + new ADR |

## Observed evidence and resume

Application has model/web/GitHub injection seams, not complete default runtime
composition. Conversation/policy/action state remains partly local; watch_jobs
has explicit-path SQLite. PAI-02..26 remain unimplemented.

Original complete product review on 04c4efa: STOP_SHIP. Both P1s fixed and
independently rechecked on e262f27: scoped PASS (not full acceptance).
Full/phase calls at 300 s and 8000-token output encountered timeout/truncation;
failed/unknown requests count toward the budget. Navigator smoke was successful
with 112 tokens and cannot replace review. Complete requests on 1136863/a5cd3d2/4901d56 failed with HTTP 500/ValueError/incomplete SSE;
no verdict. Tiny SSE diagnostic passed with 116 tokens. Corrected SSE framing
guards and safe error diagnostics precede the next complete request.
Exact historic attempts and outcomes: PAI-01-durable-design.md.

Verification: focused-prm 620 passed; latest deadline/role/strategy/checker suite
92 passed in 16.40 s; strict guard self-check 13 cases, zero skips/failures. Structural checks preserve 51 missing design approvals and
28 absent future acceptance suites. CI/provider/visual/usefulness/release are
distinct evidence, not inferred from these tests.

Existing owner decisions: exact project brief, Mimo reviewer, designed_slices,
30 total calls and design/recheck output/deadline amendments. Do not re-request.
Exact paired-feature human approval remains necessary after complete reviews.
Next: obtain independent critical-source tooling audit, then collect all four
program and product phase reviews on frozen source,
aggregate only complete coverage; resolve P0/P1, prepare exact approval package, then PAI-02.

## Owner proceed and PAI-02 implementation

Owner requested moving beyond bureaucracy into implementation; ADR-014 records
local scope, without fabricated design/live/release acceptance. PAI-02 receipt:
PAI-02-storage.md. Actual acceptance: 31 passed in 9.55 s, zero skips/failures.
Changes: src/prm/storage/{__init__,postgres,testing,__main__}.py, new real
PostgreSQL tests, pinned driver, ignored isolated venv and current instructions.
No production DB/service/timer/private account changed. Twenty of 30 model
requests consumed; tooling #20 ended length at 16000, no valid verdict.
Next card PAI-03: persist shared grants, budgets and reservation lifecycle.

PAI-03 locally verified: 86 passed in 11.43 s. Exact command and limits in
PAI-03-durable-policy.md. New default application wiring remains PAI-07 work.
Next PAI-04; no new paid model calls (20/30 consumed).

PAI-04 acceptance: 36 passed in 32.02 s, zero skips/failures. Receipt
PAI-04-durable-actions.md; phase-B review pending; next PAI-05.

PAI-05: 26 passed in 9.03 s; receipt PAI-05-durable-conversation.md.
Next PAI-06 queue/worker. Developer model consumption remains 20/30.

PAI-06 locally verified: 45 passed in 22.50 s; phase-B focused-prm 652
passed in 110.62 s. Receipt PAI-06-workers.md. All PAI-02..06 now have actual
local behavior; default runtime/ingress composition remains PAI-07.
Next independent accumulated Mimo review; twenty of 30 calls consumed.

Phase-B Mimo call #21 on a601c80 returned invalid_identity_or_completion; no
valid verdict/report and no approval implied. Calls consumed: 21/30. Under
owner ADR-014 proceed with local implementation; review remains pending,
without another upfront reviewer-framework loop. Next PAI-07.
# 2026-10-06 PAI-07 implementation checkpoint

PAI-07 local_verified: transaction inbox/enqueue, replay-safe polling, explicit
worker/application composition, owner-bound status/result/cancel and voice
intake. 51 cases passed, zero skips, in 39.76s. Receipt:
docs/verification/PAI-07-ingress.md. Independent review/human/live acceptance
remain pending. Next: PAI-08. No additional Mimo calls (21/30 consumed).
# 2026-10-06 PAI-08 implementation checkpoint

PAI-08 local_verified: confirmed PostgreSQL schedules/occurrences, fenced
one-shot scheduler, current-policy collection worker, material-change/deadline
handling and private ingress controls. 119 cases passed, zero skips, in 38.30s.
Receipt: docs/verification/PAI-08-scheduler.md. Final delivery quota/attempts and
reconciliation are PAI-09 next; independent phase-B/C reviews and human/live
acceptance remain pending. Mimo remains 21/30 calls consumed.
# 2026-10-06 PAI-09 implementation checkpoint

PAI-09 local code/tests verified: common final policy, durable send attempts/
receipts/quotas, scoped provider reconciliation and unknown UI. 112 dependency
cases passed in 91.89s; current delivery file 12 passed in 22.61s, zero skips.
Receipt: docs/verification/PAI-09-delivery.md. Preserved/fixed connection-loss
failure. Phase-C regression/review running; next PAI-10 after actual findings.
No formal/human/live approval; Mimo count before phase-C call remains 21/30.
# 2026-10-06 phase-C verification and review accounting

Code HEAD b267854: focused-prm 652 passed in 135.52s. PAI-07/08/09 individual
and dependency acceptance commands passed as recorded in their receipts.
Mimo call #22 on aed2431..b267854 failed before HTTP response with
RemoteDisconnected; no observed identity/usage/verdict. Evidence:
docs/verification/PAI-phase-c-review-failure.json. Separate smaller scope call
#23 on 5b4347d..b267854 returned requested/observed mimo-v2.6-pro with
finish_reason=length, prompt=12348/completion=8000 and no valid verdict.
Evidence: docs/verification/PAI-delivery-review-incomplete.json.
Total 23/30 consumed including
failures; no automatic retries or substitution. Independent B/C and human/live
acceptance remain pending. Next implementation card PAI-10.
# 2026-10-07 implementation-only owner steering

ADR-015: implementation first, tests/reviews afterwards. No new test run,
validator, dependency installation, Mimo call, live account, service/timer or
deployment in this pass. New code is implementation_unverified.

Commits d4d45a2 and 19477b2 add explicit runtime/model/archive/web/research/
Brief/reader, connection/source/action, memory/media, cost/cache and operation/
restore/delta components plus prepared suites. Subsequent integration connects
source services, typed delivery, Watch, transcription/vision and CLI processes.
Receipt: docs/verification/PAI-implementation-pass-20261007.md.
Draft access/cutover/pilot packages: PAI-27/28/29; conditional infrastructure
triggers unmeasured. The complete programme and 69-case evidence obligations
remain unfinished; do not mark planned slices accepted or manufacture PASS.
Continue implementation gaps before the postponed validation phase. Mimo 23/30.

# 2026-10-07 local follow-through implementation

Previously recorded Brief/calendar/academic, completion/Watch, derived-delete,
artifact restore, complete domain transfer and individually named 69-case gaps
now have implementation and prepared cases. Additional composition connects
/deep, confirmed Watch creation, selected body read, exact action version/digest,
source-origin propagation, mixed/part delivery and whole-task usage.
Status: implementation_unverified. No tests, validators, reviewer calls,
providers, services, migrations or dependencies were executed/activated here.
Next phase: pai-complete, actual fixes, focused checks and independent review.
Full programme acceptance and PAI-27..29 live/human gates remain outstanding.
Receipt: PAI-implementation-pass-20261007.md. Mimo remains 23/30.

# 2026-10-07 deferred verification started by owner

Owner: “делай, разрешаю” after the implementation handoff. Verification and
independent review are now authorized under the existing local scope and call cap.
Initial pai-complete: 20 failed, 204 passed, 796.86 s; no PASS claimed. Shared
causes: academic row-lock privilege, misplaced synthetic citations, cache key
string encoding, stale origin tags on controls, and missing object/Brief aliases.
Fix SHA: 6ac7eca. Full corrected rerun is running. Focused-prm: 652 passed in
175.91 s; subsequent Brief/conversation regression: 37 passed in 19.89 s.
Retrofit boundaries: 150 passed in 14.36 s. Formal Playbook readiness still
reports 51 TASK_DESIGN_APPROVAL_REQUIRED errors; approval is not forged.
Mimo calls #24 (phase D) and #25 (phase E) requested as fresh read-only
processes on 6ac7eca, 8000 output / 300 s; receipts capture actual outcomes.
Calls consumed/reserved including failures: 25/30. No product/live approval.

# 2026-10-07 independent findings and bounded review closure

Review #24 D and #25 E exhausted/incompletely returned under 8000/300; #26
with thinking disabled exhausted visible output; #27 focused native-render
recheck returned an invalid verdict. No valid approval is inferred from them.
Strict JSON-schema requests then produced actual independent reports: #28
FIX_P1_FIRST (three findings), #29 FIX_P1_FIRST (two findings), #30 FIX_P1_FIRST
(one medium-confidence finding). Requested/observed model mimo-v2.6-pro;
standard reviews use explicitly recorded thinking_disabled/observed zero
reasoning, not a governed Deep Review or Role Runner receipt.

Implementer fixes: f073148 logical-task fences, preparation-error semantics and
monotone import/deletion; 761ffd2 definitive response-error classification and
idempotent settlement. #29 independently read the first three fixes; #30
stated that the two further fixes appear correct. Final source SHA 761ffd2;
5c5e7db adds executable counterexamples and response to the remaining finding.
The remaining P1 stays open for independent resolution.

Current observations: whole PAI tier on 3d837bc: 230 passed in 766.41 s;
latest whole tier on 761ffd2 is still running. Current focused-prm: 652 passed
in 107.54 s. Latest changed model/budget/scope tier: 33 passed in 75.57 s;
remaining-finding counterexamples: 2 passed in 9.16 s. No skips or fabricated
PASS. Reviewed SHA/scopes/outcomes in PAI-critical-boundaries-recheck-28/29/30.json.

Mimo consumption is 30/30 including failures. No call #31, model substitution,
paid product-provider experiment, live account or deployment was attempted.
Fresh independent closure requires a scoped budget extension. Formal design,
full phase/role, live/visual usefulness and owner acceptance remain separate.

# 2026-10-07 final local validation

Final source 761ffd2: pai-complete 233 passed in 706.20 s, zero skips/failures;
all 69 names/ten scenarios enforced. Latest focused-prm 652 passed in 107.54 s.
5c5e7db adds two separately passing counterexamples; no source change.
Evidence: PAI-verification-20261007.md / PAI-validation-20261007.json.
Remaining Mimo #30 P1 and accumulated role/phase/human/live gates stay open.
Next proposed bounded review packets are prepared; 30/30 calls exhausted.

# 2026-10-07 owner-authorized review continuation

Owner: “разрешаю, делай дотконца” in response to the explicit proposal to
extend the total review cap from 30 to 33. At this checkpoint 30/33 calls
are consumed, including prior failures. Proceed sequentially: remaining P1
recheck, connection/source review, then one actual-finding recheck only if
needed. Same OpenCode Go / mimo-v2.6-pro, thinking disabled, strict JSON,
16000 output / 900 s, public code and synthetic evidence only. No automatic
retry/model substitution. No design acceptance, live access, production or
release authority is inferred. Prepared packet hashes and playbook pin verified.

First continuation command exited 2 before provider I/O: no configured
OPENCODE_API_KEY/OPENCODE_API_KEY_FILE. No call #31 receipt or reservation
was created; consumption remains 30/33. Owner was asked for the existing
credential-file path. No credential scan, model swap or paid retry occurred.
Exact non-invocation evidence: PAI-review-continuation-20261007.json.
Existing passing broad tests were not repeated; P1 remains independently open.

Review #31 reserved/attempted, 31/33 consumed including failures.
Purpose: remaining_P1_recheck; source HEAD e492ca6674a051bb88828ea38602acfcb40c12f6. No automatic retry.

# 2026-10-07 review 31 and media-boundary response

Owner directed key lookup to Georgia-Community-Navigator. The selected
credential worked at the authorized OpenCode Go endpoint; actual observed
model mimo-v2.6-pro, thinking disabled. Review #31 independently resolves
the two #30 allegations, then finds one new media P1 and one vision-bound P2.
Source at review: e492ca6. Receipt: PAI-review-continuation-31.json.
Local fixes and actual evidence: PAI-review-31-response.md (12 media cases
passed in 56.23 s; 7 cost/model/settlement regressions passed in 32.03 s;
zero skips/failures). Independent closure of the new findings remains open.
Consumption: 31/33 including failures. Next #32 connection/source review;
#33 only for actual-finding recheck. No other provider, live account, service,
production or human acceptance was used/inferred.

Review #32 reserved/attempted, 32/33 consumed including failures.
Purpose: remaining_connection_source_review; source HEAD 832f9f39fb5eae34d9df8f7db2a104c47ce77127. No automatic retry.

# 2026-10-07 review 32 candidate and final bounded fix pass

Call #32 (832f9f3) observed mimo-v2.6-pro, thinking disabled, complete JSON;
verdict contradicted P0 severities and was rejected by the existing consistency
check. Exact candidate preserved, no independent PASS synthesized. Consumption
32/33 including invalid responses. PAI-review-32-response.md records concrete
fixes, the initial 1 failed/6 passed (body selection AttributeError), corrected
19 passed, 5 refresh/cleanup passed, 38 policy/action/media regressions passed,
and 6 final Graph guard cases passed, all zero skips on successful runs.
The actual-finding packet includes explicit hash-bound source excerpts under
the 200000-byte input bound. Next: one fresh call #33 for #31/#32 findings;
no #34, automatic retry or model substitution. No live/private/product-provider
call, service, timer or production migration was executed.
