# Active Task Graph

Status: active
Last updated: 2026-09-17
Baseline: `5dfd38660b7d8d24998b4dcdf801c419c1dc8f7c`
Archive ref: origin/archive/pre-prm-retrofit-2026-08-16
Active ref: master

Historical PBR, PRM, IRX, PRM-UX, PRM-MAT and PRM-QA task records are preserved in `docs/archive/pre_retrofit_2026-08-16/tasks.pre-retrofit.md` and Git history. The PRM-SN implementation queue is registered below; existing RFX/UTD records and statuses remain preserved.

## Current Stop Point

The owner requested registration of the personal search/news plan on 2026-09-17.
The launch prompt assigns one end-to-end goal over all twelve PRM-SN tasks and
DR-1 through DR-5, starting at the first unfinished task (currently PRM-SN-1A).
Use `docs/prompts/prm_search_news_implementer.md`; after engineering gates,
continue within that goal without asking for each next card. This documentation
change does not itself start implementation, review, a pilot or runtime jobs.
See ADR-009,
`docs/PRM_SEARCH_NEWS_PLAN.md` and `docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md`.

The PRM-SN lane preserves one bot and treats UTD as a specific watch scope.
The 2026-09-03 UTD receipt records timer enablement pending profile confirmation;
current service/profile state was not observed in the 2026-09-17 audit. Existing
UTD permissions and task statuses are unchanged. PRM-19/20 and live rollout
still require their separate approvals and evidence. The historical RFX-only
feature freeze does not block an explicitly assigned bounded PRM-SN task.

## Personal Search And News dependencies

```text
PRM-SN-1A -> PRM-SN-1B -> PRM-SN-1C -> PRM-SN-DR-1
  -> PRM-SN-2A -> PRM-SN-2B -> PRM-SN-2C -> PRM-SN-DR-2
  -> PRM-SN-3A -> PRM-SN-3B -> PRM-SN-DR-3
  -> PRM-SN-4A -> PRM-SN-4B -> PRM-SN-DR-4
  -> PRM-SN-5A -> PRM-SN-5B -> PRM-SN-DR-5
  -> separately approved manual pilot -> PRM-SN-DR-PILOT
  -> separately approved expanded rollout
```

Immediate deep reviews for changed safety boundaries apply inside these phases.
A task critic is not a completed phase review. No gate is marked passed here.

## Dependency graph

```text
RFX-0 -> RFX-1 -> RFX-2 -> RFX-3 -> RFX-4
RFX-2 -> RFX-5
RFX-3/RFX-4/RFX-5 -> RFX-6 -> RFX-7
RFX-7 -> RFX-8 -> RFX-9
RFX-7 -> RFX-10 -> UTD-P0
UTD-P0 -> UTD-1 / UTD-2 / UTD-3
UTD-1 / UTD-2 / UTD-3 -> UTD-DR-1 -> UTD-4 -> UTD-5 -> UTD-DR-2 -> UTD-6 -> UTD-7 -> UTD-DR-3
```

## Personal Search And News task records

### PRM-SN-1A: Final Citation Integrity And Verification Completeness

Owner:      codex
Phase:      search-news-answer
Type:       rag:generation eval:gate
Depends-On: none
Status:     implemented
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2

Objective: |
  Bind visible final-answer citations to the selected evidence and make incomplete verification explicit before publication.

Acceptance-Criteria:
  - "Wrong or absent URLs cannot receive an invented citation-precision pass; lexical matching never silently replaces the visible source."
  - "Short factual text and unverified tail content yield explicit incomplete handling and a useful source-attributed fallback."
  - "Paired useful answers, boundaries and recommendations remain usable; publish actual before/after outputs and do not claim semantic accuracy is solved."

Verification:
  - After I/O preflight, run with fake providers/Telegram and disposable DBs: PYTHONPATH=src python3 -m pytest tests/test_claim_ledger.py tests/test_prm_synthesis.py tests/test_prm_application.py tests/test_prm_intent_archive_contract.py -q
  - Record before/after outputs, meaningful new regression assertions, limitations and rollback; no live measurement claim.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md

Files:
  - src/assistant/claim_ledger.py
  - src/prm/synthesis.py
  - src/prm/application.py

Notes: |
  Detailed scope and rollback are in PRM_SEARCH_NEWS_PLAN. Listing this task does not assign it.
  Focused critic findings roll into the phase gate; immediate safety triggers apply before dependency progress.

### PRM-SN-1B: Key Claim Support And Safe Publication

Owner:      codex
Phase:      search-news-answer
Type:       rag:generation eval:gate
Depends-On: PRM-SN-1A
Status:     implemented
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2

Objective: |
  Reject unsupported key numbers, dates, units, negations, actors and quotations while preserving useful supported answers.

Acceptance-Criteria:
  - "Synthetic critical mutations do not publish as verified facts, including mutations with the correct source URL."
  - "Source facts, inference and recommendations have explicit evidence scope; lexical overlap is not semantic entailment."
  - "Report false accepts and false refusals on paired positives; uncertain free paraphrases use a useful attributed fallback, not an invented semantic verifier."

Verification:
  - After I/O preflight, run with fake providers/Telegram and disposable DBs: PYTHONPATH=src python3 -m pytest tests/test_claim_ledger.py tests/test_prm_synthesis.py tests/test_prm_application.py -q
  - Record before/after outputs, meaningful new regression assertions, limitations and rollback; no live measurement claim.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md

Files:
  - src/assistant/claim_ledger.py
  - src/prm/synthesis.py
  - src/prm/application.py

Notes: |
  Detailed scope and rollback are in PRM_SEARCH_NEWS_PLAN. Listing this task does not assign it.
  Focused critic findings roll into the phase gate; immediate safety triggers apply before dependency progress.

### PRM-SN-1C: Direct Answers And Mixed-query Partial Results

Owner:      codex
Phase:      search-news-answer
Type:       rag:generation eval:gate
Depends-On: PRM-SN-1B
Status:     implemented
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2

Objective: |
  Return a compact useful first answer and preserve archive findings when current external verification is unavailable.

Acceptance-Criteria:
  - "Archive-scoped applicability now does not trigger web or an implicit project."
  - "Mixed archive/current request retains the supported local answer and the precise external gap; dispatch never iterates missing action_codes."
  - "Final Telegram text has nearby sources and useful follow-up, checked end-to-end with a fake sender."

Verification:
  - After I/O preflight, run with fake providers/Telegram and disposable DBs: PYTHONPATH=src python3 -m pytest tests/test_prm_application.py tests/test_prm_bot_dispatch.py tests/test_prm_intent_archive_contract.py -q
  - Record before/after outputs, meaningful new regression assertions, limitations and rollback; no live measurement claim.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md

Files:
  - src/prm/application.py
  - src/prm/presentation.py
  - src/bot/prm_handlers.py

Notes: |
  Detailed scope and rollback are in PRM_SEARCH_NEWS_PLAN. Listing this task does not assign it.
  Focused critic findings roll into the phase gate; immediate safety triggers apply before dependency progress.

### PRM-SN-DR-1: Phase 1 Deep Review

Owner:      read-only reviewer + human operator
Phase:      deep-review
Type:       compliance:evidence eval:gate
Depends-On: PRM-SN-1A, PRM-SN-1B, PRM-SN-1C
Status:     implemented
Risk-Level: high
Critic-Required: required
Correction-Budget: 2

Objective: |
  Review the accumulated phase diff: Final answers, claim support, citation integrity, completeness and useful mixed responses.

Acceptance-Criteria:
  - "Fresh read-only Codex exec requests gpt-5.6-terra/high; exact command, reviewed SHA/diff and observed model/effort evidence are recorded."
  - "P0/P1 and mandatory evidence gaps are corrected and re-verified before the dependent phase; useful positive cases and final user output are inspected."
  - "The verdict is limited to demonstrated engineering scope; independent human labels, runtime, pilot and release gates are not fabricated or self-approved."

Verification:
  - Follow docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md; inspect accumulated phase tests and perform only justified safe re-verification.
  - Record sanitised review, fixes, remaining risks and final diff identity under docs/audit/; do not create a placeholder PASS receipt.

Context-Refs:
  - docs/REVIEW_POLICY.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md

Files:
  - docs/audit/
  - docs/tasks.md

Notes: |
  Under the assigned end-to-end goal, a passed engineering review opens the next
  local phase without another permission request. It never permits production.
  For DR-5, a manual pilot still requires separate approval of the concrete packet.

### PRM-SN-2A: Typed Volatile Follow-up Context

Owner:      codex
Phase:      search-news-dialogue
Type:       agent:harness eval:gate privacy
Depends-On: PRM-SN-DR-1
Status:     implemented
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2

Objective: |
  Keep topic, evidence item selection and filters in explicit temporary state, with real date-window updates.

Acceptance-Criteria:
  - "Topic A then new B then more continues B; direct-only and last-week filters actually apply."
  - "Expired or restarted sessions honestly request missing context and do not create durable memory."
  - "Period boundaries, empty windows and timezone/DST behavior have deterministic fixture checks."

Verification:
  - After I/O preflight, run with fake providers/Telegram and disposable DBs: PYTHONPATH=src python3 -m pytest tests/test_prm_bot_dispatch.py tests/test_memory_research.py -q
  - Record before/after outputs, meaningful new regression assertions, limitations and rollback; no live measurement claim.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md

Files:
  - src/bot/prm_handlers.py
  - src/assistant/memory_research.py
  - src/prm/contracts.py

Notes: |
  Detailed scope and rollback are in PRM_SEARCH_NEWS_PLAN. Listing this task does not assign it.
  Focused critic findings roll into the phase gate; immediate safety triggers apply before dependency progress.

### PRM-SN-2B: Exact Item Save Preview And Confirmation

Owner:      codex
Phase:      search-news-dialogue
Type:       agent:harness eval:gate privacy
Depends-On: PRM-SN-2A
Status:     implemented
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2

Objective: |
  Resolve save the second item against the exact answer version and show the full proposed object and effect before confirmation.

Acceptance-Criteria:
  - "Confirm/cancel/repeat/expiry/cross-chat/old-version behavior preserves ownership and creates at most one intended canonical object."
  - "Saved topic wording never promises an executable subscription; proposal and receipt retention are explicit."
  - "Changed confirmation or persistent-write semantics receive immediate review before dependent work."

Verification:
  - After I/O preflight, run with fake providers/Telegram and disposable DBs: PYTHONPATH=src python3 -m pytest tests/test_prm_post_answer_actions.py tests/test_prm_bot_dispatch.py -q
  - Record before/after outputs, meaningful new regression assertions, limitations and rollback; no live measurement claim.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md

Files:
  - src/assistant/prm_post_answer_actions.py
  - src/assistant/pi_memory.py
  - src/bot/prm_handlers.py

Notes: |
  Detailed scope and rollback are in PRM_SEARCH_NEWS_PLAN. Listing this task does not assign it.
  Focused critic findings roll into the phase gate; immediate safety triggers apply before dependency progress.

### PRM-SN-2C: Archive Refresh And Index Health Visibility

Owner:      codex
Phase:      search-news-dialogue
Type:       agent:harness eval:gate privacy
Depends-On: PRM-SN-2B
Status:     implemented
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2

Objective: |
  Expose last refresh success, attempt, partial/error and archive/index coverage without executing a refresh from status.

Acceptance-Criteria:
  - "Healthy no-new-data, stale data, partial refresh and source failure are distinguishable in user-visible status."
  - "Reading status never starts ingestion, migrations or index building; timestamps represent actual coverage, not status request time."
  - "New derived receipt persistence, if required, is fixture-only and receives immediate schema/retention review."

Verification:
  - After I/O preflight, run with fake providers/Telegram and disposable DBs: PYTHONPATH=src python3 -m pytest tests/test_prm_refresh_receipt.py -q
  - Record before/after outputs, meaningful new regression assertions, limitations and rollback; no live measurement claim.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md

Files:
  - src/assistant/prm_refresh_receipt.py
  - src/bot/legacy_handlers.py
  - src/main.py

Notes: |
  Detailed scope and rollback are in PRM_SEARCH_NEWS_PLAN. Listing this task does not assign it.
  Focused critic findings roll into the phase gate; immediate safety triggers apply before dependency progress.

### PRM-SN-DR-2: Phase 2 Deep Review

Owner:      read-only reviewer + human operator
Phase:      deep-review
Type:       compliance:evidence eval:gate
Depends-On: PRM-SN-2A, PRM-SN-2B, PRM-SN-2C
Status:     implemented
Risk-Level: high
Critic-Required: required
Correction-Budget: 2

Objective: |
  Review the accumulated phase diff: Dialogue isolation, date filters, exact confirmation, callbacks and archive health.

Acceptance-Criteria:
  - "Fresh read-only Codex exec requests gpt-5.6-terra/high; exact command, reviewed SHA/diff and observed model/effort evidence are recorded."
  - "P0/P1 and mandatory evidence gaps are corrected and re-verified before the dependent phase; useful positive cases and final user output are inspected."
  - "The verdict is limited to demonstrated engineering scope; independent human labels, runtime, pilot and release gates are not fabricated or self-approved."

Verification:
  - Follow docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md; inspect accumulated phase tests and perform only justified safe re-verification.
  - Record sanitised review, fixes, remaining risks and final diff identity under docs/audit/; do not create a placeholder PASS receipt.

Context-Refs:
  - docs/REVIEW_POLICY.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md

Files:
  - docs/audit/
  - docs/tasks.md

Notes: |
  Under the assigned end-to-end goal, a passed engineering review opens the next
  local phase without another permission request. It never permits production.
  For DR-5, a manual pilot still requires separate approval of the concrete packet.

### PRM-SN-3A: Request Plan And Separate Search Permissions

Owner:      codex
Phase:      search-news-verification
Type:       agent:harness eval:gate privacy
Depends-On: PRM-SN-DR-2
Status:     implemented
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2

Objective: |
  Model archive, public verification and private-context permissions separately in a bounded request plan.

Acceptance-Criteria:
  - "Archive now stays local; current price requires current evidence; mixed tasks retain independent useful parts."
  - "Public query construction removes private archive/profile context and has executable call/time/cost limits."
  - "Consent-preview and egress-boundary changes receive immediate review; no actual mode is enabled."

Verification:
  - After I/O preflight, run with fake providers/Telegram and disposable DBs: PYTHONPATH=src python3 -m pytest tests/test_prm_intent_archive_contract.py tests/test_primary_source_verification.py -q
  - Record before/after outputs, meaningful new regression assertions, limitations and rollback; no live measurement claim.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md

Files:
  - src/prm/routing.py
  - src/prm/application.py
  - src/assistant/primary_source_verification.py

Notes: |
  Detailed scope and rollback are in PRM_SEARCH_NEWS_PLAN. Listing this task does not assign it.
  Focused critic findings roll into the phase gate; immediate safety triggers apply before dependency progress.

### PRM-SN-3B: Primary-source Verification In The Answer Path

Owner:      codex
Phase:      search-news-verification
Type:       agent:harness eval:gate privacy
Depends-On: PRM-SN-3A
Status:     implemented
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2

Objective: |
  Connect bounded discovery and primary-source reading to versioned evidence and the final-answer publication contract.

Acceptance-Criteria:
  - "Search snippets remain candidates; one sufficient authoritative primary source can support the answer."
  - "Provenance and dates, conflicting/unavailable pages, injection, unsafe URLs/redirects and budget exhaustion are checked with fake transport."
  - "No private-context leakage or live provider call; partial answers and disabled capability rollback are usable."

Verification:
  - After I/O preflight, run with fake providers/Telegram and disposable DBs: PYTHONPATH=src python3 -m pytest tests/test_primary_source_verification.py tests/test_external_watch_fetch_safety.py tests/test_prm_application.py -q
  - Record before/after outputs, meaningful new regression assertions, limitations and rollback; no live measurement claim.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md

Files:
  - src/assistant/primary_source_verification.py
  - src/prm/application.py
  - src/llm/openai_provider.py

Notes: |
  Detailed scope and rollback are in PRM_SEARCH_NEWS_PLAN. Listing this task does not assign it.
  Focused critic findings roll into the phase gate; immediate safety triggers apply before dependency progress.

### PRM-SN-DR-3: Phase 3 Deep Review

Owner:      read-only reviewer + human operator
Phase:      deep-review
Type:       compliance:evidence eval:gate
Depends-On: PRM-SN-3A, PRM-SN-3B
Status:     implemented
Risk-Level: high
Critic-Required: required
Correction-Budget: 2

Objective: |
  Review the accumulated phase diff: Primary-source verification, public/private egress separation and enforced budgets.

Acceptance-Criteria:
  - "Fresh read-only Codex exec requests gpt-5.6-terra/high; exact command, reviewed SHA/diff and observed model/effort evidence are recorded."
  - "P0/P1 and mandatory evidence gaps are corrected and re-verified before the dependent phase; useful positive cases and final user output are inspected."
  - "The verdict is limited to demonstrated engineering scope; independent human labels, runtime, pilot and release gates are not fabricated or self-approved."

Verification:
  - Follow docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md; inspect accumulated phase tests and perform only justified safe re-verification.
  - Record sanitised review, fixes, remaining risks and final diff identity under docs/audit/; do not create a placeholder PASS receipt.

Context-Refs:
  - docs/REVIEW_POLICY.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md

Files:
  - docs/audit/
  - docs/tasks.md

Notes: |
  Under the assigned end-to-end goal, a passed engineering review opens the next
  local phase without another permission request. It never permits production.
  For DR-5, a manual pilot still requires separate approval of the concrete packet.

### PRM-SN-4A: Shared Topics And Versioned News Events

Owner:      codex
Phase:      search-news-editions
Type:       agent:harness eval:gate privacy
Depends-On: PRM-SN-DR-3
Status:     implemented
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2

Objective: |
  Define general topics and edition windows with event identity and material updates; retain UTD as one source adapter scope.

Acceptance-Criteria:
  - "Publication, event, update, fetch and check times remain distinct; repost families do not become independent new events."
  - "Cosmetic changes, disappearance from a bounded window and genuine corrections have different outcomes."
  - "Topic creation starts no collector; any derived schema/retention change has immediate review and no production migration."

Verification:
  - After I/O preflight, run with fake providers/Telegram and disposable DBs: PYTHONPATH=src python3 -m pytest tests/test_external_watch_shadow.py tests/test_external_watch_selection.py -q
  - Record before/after outputs, meaningful new regression assertions, limitations and rollback; no live measurement claim.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md

Files:
  - src/external_watch/adapters.py
  - src/external_watch/store.py
  - src/external_watch/selection.py

Notes: |
  Detailed scope and rollback are in PRM_SEARCH_NEWS_PLAN. Listing this task does not assign it.
  Focused critic findings roll into the phase gate; immediate safety triggers apply before dependency progress.

### PRM-SN-4B: Useful On-demand Topic Digest

Owner:      codex
Phase:      search-news-editions
Type:       agent:harness eval:gate privacy
Depends-On: PRM-SN-4A
Status:     implemented
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2

Objective: |
  Produce a useful compact multi-section edition before any subscription, with changes since the prior delivered edition.

Acceptance-Criteria:
  - "Each event appears once; significance is labelled analysis, sources support facts, and irrelevant filler is omitted."
  - "Healthy no-news and failed-source coverage are distinguishable; an old repost is never presented as new."
  - "The actual plain-text Telegram renderer respects message limits and supports detail requests; no automatic job or notification is created."

Verification:
  - After I/O preflight, run with fake providers/Telegram and disposable DBs: PYTHONPATH=src python3 -m pytest tests/test_prm_application.py tests/test_external_watch_selection.py tests/test_external_watch_delivery.py -q
  - Record before/after outputs, meaningful new regression assertions, limitations and rollback; no live measurement claim.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md

Files:
  - src/prm/application.py
  - src/prm/presentation.py
  - src/external_watch/selection.py
  - src/external_watch/delivery.py

Notes: |
  Detailed scope and rollback are in PRM_SEARCH_NEWS_PLAN. Listing this task does not assign it.
  Focused critic findings roll into the phase gate; immediate safety triggers apply before dependency progress.

### PRM-SN-DR-4: Phase 4 Deep Review

Owner:      read-only reviewer + human operator
Phase:      deep-review
Type:       compliance:evidence eval:gate
Depends-On: PRM-SN-4A, PRM-SN-4B
Status:     implemented
Risk-Level: high
Critic-Required: required
Correction-Budget: 2

Objective: |
  Review the accumulated phase diff: Useful on-demand editions, event novelty, corrections and actual Telegram rendering.

Acceptance-Criteria:
  - "Fresh read-only Codex exec requests gpt-5.6-terra/high; exact command, reviewed SHA/diff and observed model/effort evidence are recorded."
  - "P0/P1 and mandatory evidence gaps are corrected and re-verified before the dependent phase; useful positive cases and final user output are inspected."
  - "The verdict is limited to demonstrated engineering scope; independent human labels, runtime, pilot and release gates are not fabricated or self-approved."

Verification:
  - Follow docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md; inspect accumulated phase tests and perform only justified safe re-verification.
  - Record sanitised review, fixes, remaining risks and final diff identity under docs/audit/; do not create a placeholder PASS receipt.

Context-Refs:
  - docs/REVIEW_POLICY.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md

Files:
  - docs/audit/
  - docs/tasks.md

Notes: |
  Under the assigned end-to-end goal, a passed engineering review opens the next
  local phase without another permission request. It never permits production.
  For DR-5, a manual pilot still requires separate approval of the concrete packet.

### PRM-SN-5A: Transactional Delivery Outbox And Unknown Sends

Owner:      codex
Phase:      search-news-subscriptions
Type:       agent:harness eval:gate privacy
Depends-On: PRM-SN-DR-4
Status:     implemented
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2

Objective: |
  Persist pending work atomically with source changes and reserve delivery/quota with bounded attempts and explicit unknown results.

Acceptance-Criteria:
  - "Race, timeout before/after acceptance, crash/restart, daily caps and partial sends neither silently lose pending work nor cause a local reservation double-send."
  - "Known failures retry within policy; ambiguous Telegram acceptance remains unknown and is not blindly resent or called exactly-once."
  - "Immediate schema/write/delivery review precedes dependent work; rollback pauses sends and retains compatible receipts."

Verification:
  - After I/O preflight, run with fake providers/Telegram and disposable DBs: PYTHONPATH=src python3 -m pytest tests/test_external_watch_shadow.py tests/test_external_watch_delivery.py -q
  - Record before/after outputs, meaningful new regression assertions, limitations and rollback; no live measurement claim.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md

Files:
  - src/external_watch/store.py
  - src/external_watch/live.py
  - src/external_watch/delivery.py

Notes: |
  Detailed scope and rollback are in PRM_SEARCH_NEWS_PLAN. Listing this task does not assign it.
  Focused critic findings roll into the phase gate; immediate safety triggers apply before dependency progress.

### PRM-SN-5B: Confirmed Subscription And Bounded Pilot Packet

Owner:      codex
Phase:      search-news-subscriptions
Type:       agent:harness eval:gate privacy
Depends-On: PRM-SN-5A
Status:     implemented
Risk-Level: high
Critic-Required: required
Runtime-Verification: not_required
Correction-Budget: 2

Objective: |
  Provide exact subscription preview, scheduling controls and a concrete pilot packet without enabling runtime.

Acceptance-Criteria:
  - "Preview includes topics, exclusions, sources, language/depth, period, timezone, schedule, cap, quiet hours, expiry, pause/mute/unsubscribe and the real activation effect."
  - "Unconfirmed, expired or cancelled subscriptions cannot poll/send; kill controls and consent are rechecked before collection and delivery."
  - "DST, unsubscribe during queued send, disabled runtime and rollback are fixture-tested; a specific SHA/source/budget/duration pilot packet is prepared, not launched."

Verification:
  - After I/O preflight, run with fake providers/Telegram and disposable DBs: PYTHONPATH=src python3 -m pytest tests/test_external_watch_profile.py tests/test_external_watch_delivery.py tests/test_prm_utd_callbacks.py -q
  - Record before/after outputs, meaningful new regression assertions, limitations and rollback; no live measurement claim.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md

Files:
  - src/external_watch/profile.py
  - src/external_watch/live.py
  - src/external_watch/delivery.py
  - src/assistant/utd_profile_schema.py
  - src/bot/callbacks.py

Notes: |
  Detailed scope and rollback are in PRM_SEARCH_NEWS_PLAN. Listing this task does not assign it.
  Focused critic findings roll into the phase gate; immediate safety triggers apply before dependency progress.

### PRM-SN-DR-5: Phase 5 Deep Review

Owner:      read-only reviewer + human operator
Phase:      deep-review
Type:       compliance:evidence eval:gate
Depends-On: PRM-SN-5A, PRM-SN-5B
Status:     implemented
Risk-Level: high
Critic-Required: required
Correction-Budget: 2

Objective: |
  Review the accumulated phase diff: Subscription effect, outbox/quota/unknown delivery, controls and rollback.

Acceptance-Criteria:
  - "Fresh read-only Codex exec requests gpt-5.6-terra/high; exact command, reviewed SHA/diff and observed model/effort evidence are recorded."
  - "P0/P1 and mandatory evidence gaps are corrected and re-verified before the dependent phase; useful positive cases and final user output are inspected."
  - "The verdict is limited to demonstrated engineering scope; independent human labels, runtime, pilot and release gates are not fabricated or self-approved."

Verification:
  - Follow docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md; inspect accumulated phase tests and perform only justified safe re-verification.
  - Record sanitised review, fixes, remaining risks and final diff identity under docs/audit/; do not create a placeholder PASS receipt.

Context-Refs:
  - docs/REVIEW_POLICY.md
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/PRM_SEARCH_NEWS_PLAN.md
  - docs/PRM_SEARCH_NEWS_EVAL.md

Files:
  - docs/audit/
  - docs/tasks.md

Notes: |
  Under the assigned end-to-end goal, a passed engineering review opens the next
  local phase without another permission request. It never permits production.
  For DR-5, a manual pilot still requires separate approval of the concrete packet.

### PRM-SN-DR-PILOT: Observed Pilot Evidence Review

Owner:      human operator + read-only reviewer
Phase:      live-evidence-review
Type:       compliance:evidence eval:gate privacy
Depends-On: PRM-SN-DR-5
Status:     blocked_pending_approved_pilot_evidence
Risk-Level: high
Critic-Required: required
Runtime-Verification: required

Objective: |
  Assess actual separately approved pilot evidence before any expanded rollout.

Acceptance-Criteria:
  - "Explicit pilot scope/start permission and real operator observations exist; fixtures and LLM labels do not substitute for them."
  - "Usefulness, notification noise/duplicates, source health, latency, full cost per successful result, receipts and rollback are evaluated with denominators."
  - "The fresh Terra/high reviewer records provenance, corrections and limits; expanded sources/caps/autonomy and release remain separate human decisions."

Verification:
  - Review the approved pilot packet, minimised actual receipts and owner labels under the privacy scope; record absent evidence instead of inventing it.

Context-Refs:
  - docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md
  - docs/PRM_SEARCH_NEWS_EVAL.md

Files:
  - docs/audit/
  - docs/tasks.md

## Preserved RFX And UTD records

### RFX-0: Freeze Baseline And Inventory

Owner:      codex
Phase:      retrofit
Type:       compliance:evidence
Depends-On: none
Status:     implemented

Objective: |
  Preserve the pre-retrofit repository state and record active, compatibility, generated and historical paths before structural changes.

Acceptance-Criteria:
  - "The archive branch points to the exact pre-retrofit commit and the retrofit plan records deletion rules."

Verification:
  - git rev-parse archive/pre-prm-retrofit-2026-08-16

Files:
  - docs/retrofit/RFX_REPOSITORY_RETROFIT.md

### RFX-1: Consolidate Active Documentation

Owner:      codex
Phase:      retrofit
Type:       compliance:evidence
Depends-On: RFX-0
Status:     implemented

Objective: |
  Replace historical encyclopedic handoffs with one current architecture, one active task queue, one concise Codex handoff and one current evidence index.

Acceptance-Criteria:
  - "Historical task, architecture, handoff and evidence documents are preserved while active documentation points to the PRM product and RFX queue."

Verification:
  - python tools/playbook_validate.py --root . --check tasks --check references

Files:
  - README.md
  - docs/README.md
  - docs/ARCHITECTURE.md
  - docs/tasks.md
  - docs/CODEX_PROMPT.md
  - docs/EVIDENCE_INDEX.md
  - docs/IMPLEMENTATION_JOURNAL.md

### RFX-2: Introduce PRM Application Boundary

Owner:      codex
Phase:      retrofit
Type:       rag:query rag:generation agent:harness
Depends-On: RFX-1
Status:     implemented

Objective: |
  Introduce one typed application service used by Telegram, CLI and Eval V2 without changing retrieval or evidence semantics.

Acceptance-Criteria:
  - "Research, brief and chat requests return one typed response contract, while unnamed project-decision requests clarify before retrieval-backed recommendation."

Verification:
  - PYTHONPATH=src python -m pytest tests/test_prm_application.py -q

Files:
  - src/prm/contracts.py
  - src/prm/application.py
  - src/prm/routing.py
  - src/prm/presentation.py
  - tests/test_prm_application.py

### RFX-3: Split Active Telegram Runtime From Legacy Handlers

Owner:      codex
Phase:      retrofit
Type:       tool:call agent:harness
Depends-On: RFX-2
Status:     implemented

Objective: |
  Route the active PRM bot through a focused command module while retaining the previous handler implementation behind a lazy compatibility facade.

Acceptance-Criteria:
  - "The active bot avoids report-era imports and legacy command dispatch remains available only through explicit legacy mode."

Verification:
  - PYTHONPATH=src python -m pytest tests/test_prm_bot_dispatch.py tests/test_retrofit_boundaries.py -q

Files:
  - src/bot/runtime.py
  - src/bot/prm_handlers.py
  - src/bot/handlers.py
  - src/bot/legacy_handlers.py
  - src/bot/bot.py

### RFX-4: Add Compact PRM CLI And Update Runtime Template

Owner:      codex
Phase:      retrofit
Type:       tool:schema
Depends-On: RFX-3
Status:     implemented

Objective: |
  Make the active assistant, research and brief commands available through a compact PRM CLI while leaving the historical CLI as compatibility-only.

Acceptance-Criteria:
  - "The PRM CLI exposes assistant, research, brief and chat commands, and the active systemd template starts the compact CLI."

Verification:
  - PYTHONPATH=src python -m pytest tests/test_prm_cli.py -q

Files:
  - src/prm/cli.py
  - systemd/telegram-prm-assistant.service
  - tests/test_prm_cli.py

### RFX-5: Separate Active And Compatibility Test Tiers

Owner:      codex
Phase:      retrofit
Type:       eval:gate
Depends-On: RFX-2
Status:     implemented

Objective: |
  Keep the normal PRM loop focused on the current request-to-answer path and isolate report-era compatibility checks.

Acceptance-Criteria:
  - "focused-prm excludes report-era renderer tests and legacy-compat is available for explicit compatibility work."

Verification:
  - python tools/test_tiers.py retrofit-boundaries

Files:
  - tools/test_tiers.py
  - tests/test_retrofit_boundaries.py

### RFX-6: Remove Tracked Generated Artifacts

Owner:      codex
Phase:      retrofit
Type:       compliance:evidence
Depends-On: RFX-3, RFX-4, RFX-5
Status:     implemented

Objective: |
  Remove generated operational outputs and Playbook execution artifacts from the active branch while retaining gitignored directories and reproducible public evidence.

Acceptance-Criteria:
  - "No private or historical generated file under data/output is tracked except .gitkeep, and .playbook-artifacts is untracked."

Verification:
  - git ls-files data/output .playbook-artifacts

Files:
  - .gitignore
  - data/output/
  - .playbook-artifacts/

### RFX-7: Migrate Active Callers Behind Compatibility Adapters

Owner:      codex
Phase:      retrofit
Type:       agent:harness
Depends-On: RFX-6
Status:     implemented

Objective: |
  Ensure the active PRM package, Telegram service and Eval V2 do not import report-era renderers, manifests, Radar or Frontier modules; retain explicit compatibility entrypoints for historical commands.

Acceptance-Criteria:
  - "The active PRM import graph excludes report-era output modules and Eval V2 calls the PRM application boundary."

Verification:
  - PYTHONPATH=src python -m pytest tests/test_retrofit_boundaries.py -q

Files:
  - src/prm/
  - src/bot/
  - tools/prm_qa_eval_v2.py

### RFX-8: Controlled Operator Smoke Review

Owner:      human
Phase:      validation
Type:       eval:gate
Depends-On: RFX-7
Status:     planned

Objective: |
  Run 15-20 natural questions against the retrofitted runtime and label usefulness, partial value or miss before destructive product-surface removal.

Acceptance-Criteria:
  - "At least 15 labelled operator interactions exist with workflow and project metadata."

Verification:
  - operator-approved private smoke receipt

Files:
  - data/evals/private/

### RFX-9: Delete Dead Legacy Code And Tests

Owner:      codex
Phase:      cleanup
Type:       compliance:evidence
Depends-On: RFX-8
Status:     blocked

Objective: |
  Delete compatibility modules, commands and tests that have no active callers and no observed operator use, relying on the archive branch and Git history for recovery.

Acceptance-Criteria:
  - "Every deleted Python module has zero active imports, a named replacement and green focused PRM plus legacy compatibility checks."

Verification:
  - python3 tools/test_tiers.py focused-prm

Files:
  - src/
  - tests/

### RFX-10: Deep Review And Retrofit Completion

Owner:      codex
Phase:      review
Type:       compliance:evidence
Depends-On: RFX-7
Status:     implemented_with_residual_human_gate

Objective: |
  Perform a fresh architecture, privacy, test-boundary and repository-truth review and record remaining debt without overstating operator value.

Acceptance-Criteria:
  - "The deep review records resolved findings, residual risks and exact verification evidence."

Verification:
  - test -f docs/retrofit/RFX_DEEP_REVIEW.md

Files:
  - docs/retrofit/RFX_DEEP_REVIEW.md
  - docs/EVIDENCE_INDEX.md
  - docs/IMPLEMENTATION_JOURNAL.md

### UTD-P0: External Watch Readiness

Owner:      codex + human operator
Phase:      preparation
Type:       compliance:evidence
Depends-On: RFX-10
Status:     implemented_with_residual_human_gate

Objective: |
  Specify a confirmed, source-bounded external-watch capability and prepare a
  privacy-safe fixture/evaluation intake without starting a collector.

Acceptance-Criteria:
  - "ADR-008, a validated 50-slot 35/15 evaluation inventory, and a documented
    real-source intake process exist; no fixture inventory is represented as
    shadow-ready or launch-ready before operator evidence."

Verification:
  - python3 tools/validate_external_watch_eval.py --manifest evals/external_watch/manifest.v1.json --json
  - PYTHONPATH=src python3 -m pytest tests/test_external_watch_eval_manifest.py -q

Files:
  - docs/adr/ADR-008-confirmed-external-watch.md
  - docs/external_watch_p0_readiness.md
  - evals/external_watch/manifest.v1.json
  - tools/validate_external_watch_eval.py

### UTD-1: Personal University Profile And Watch Proposal UX

Owner:      codex + human operator
Phase:      product-contract
Type:       tool:schema privacy
Depends-On: UTD-P0
Status:     implemented_with_residual_human_gate

Objective: |
  Define one confirmation-gated UTD profile and typed watch proposal inside the
  existing PRM Telegram bot. The profile expresses programme, academic/career
  goals, AI/engineering interests, eligible audiences, spouse/family context,
  notification limits, timezone, and review/expiry without silently enabling
  durable preferences beyond exact confirmation or external monitoring.

Acceptance-Criteria:
  - "The bot shows a human-readable draft and watch preview before save with
    source families, positive/negative filters, programme/career relevance,
    spouse/family eligibility, America/Chicago timezone, cadence, daily cap,
    expiry and pause/mute choices."
  - "Canonical profile/watch intent is persisted only through the existing exact
    confirmation flow; cancelled and expired draft payloads are scrubbed."
  - "The active UI remains one bot: UTD ASK/WATCH complements archive AI
    research; explicit archive wording retains the existing PRM archive route."
  - "The isolated OpenAI adapter remains local-first/default-deny and requires
    separate explicit gates for provider egress and archive-context egress."

Verification:
  - PYTHONPATH=src python3 -m pytest tests/test_utd_profile.py tests/test_utd_ux_fixtures.py tests/test_prm_utd_dispatch.py tests/test_prm_utd_callbacks.py tests/test_openai_provider.py -q
  - python3 tools/test_tiers.py focused-prm
  - docs/audit/UTD-1_FOCUSED_SAFETY_REVIEW.md

Notes: |
  UTD-1 remains the confirmed one-bot profile/watch contract. Subsequent work has
  added sanitized live source evidence and a bounded shadow collector without
  changing UTD-1 confirmation semantics, production DB boundaries or Telegram
  delivery. Human evaluation labels remain a later quality gate.

Files:
  - src/assistant/utd_profile.py
  - src/assistant/utd_profile_schema.py
  - src/assistant/utd_profile_store.py
  - src/assistant/pi_memory.py
  - src/bot/prm_handlers.py
  - src/bot/callbacks.py
  - src/bot/bot.py
  - src/llm/openai_provider.py
  - tests/test_utd_profile.py
  - tests/test_utd_ux_fixtures.py
  - tests/test_prm_utd_dispatch.py
  - tests/test_prm_utd_callbacks.py
  - tests/test_openai_provider.py
  - tests/fixtures/utd_ux_cases.json
  - docs/audit/UTD-1_FOCUSED_SAFETY_REVIEW.md

### UTD-2: Sanitized Primary-source Contract Capture

Owner:      human operator
Phase:      evidence
Type:       eval:gate privacy
Depends-On: UTD-P0
Status:     implemented

Objective: |
  Capture the minimum real UTD source evidence needed to implement source-
  specific adapters without guessing IDs, recurrence/cancellation semantics,
  filters, cache headers, or eligibility rules.

Acceptance-Criteria:
  - "Sanitized Localist Calendar JSON proves event and instance identity,
    recurrence, status, updated time, pagination, relevant filter IDs/names and
    observed response headers."
  - "Sanitized ISSO and Basic Needs HTML prove the stable primary content
    region, canonical URL and material deadline/resource fields."
  - "Samples contain no credentials, cookies, email addresses, student records,
    personal names, private Telegram data or unrelated page content."

Verification:
  - private operator capture receipt; minimized public fixtures only after
    manual sanitation and manifest validation

Notes: |
  Real sanitized Calendar/Localist, ISSO and Basic Needs source-contract fixtures
  were captured on 2026-08-28 and validated. The manifest now records
  live_source_samples_verified=true; launch_ready remains false.

Files:
  - tests/fixtures/external_watch/
  - evals/external_watch/manifest.v1.json
  - docs/external_watch_p0_readiness.md
  - docs/audit/UTD-2_REAL_SOURCE_CAPTURE_2026-08-28.md

### UTD-3: Operator Evaluation Labels And Relevance Policy

Owner:      human operator + codex
Phase:      evaluation
Type:       eval:gate
Depends-On: UTD-P0
Status:     implemented_with_residual_human_gate

Objective: |
  Turn the 50-case inventory into a reviewed, source-grounded evaluation set
  for the operator's UTD goals: programme/academic deadlines, AI/engineering
  learning, career opportunities, ISSO/admin risk, benefits/basic needs, and
  spouse/family eligible events.

Acceptance-Criteria:
  - "All 50 cases have operator-reviewed notify, ignore or ambiguous labels,
    expected material changed fields and safe fixture references; 15 holdout
    cases are not used to tune policy."
  - "High-urgency false positives, unsupported benefit/savings claims,
    ineligible spouse/family alerts, duplicates, past events and stale-source
    failures have explicit negative controls."
  - "The initial policy defines urgent override, daily digest, max five items
    per day, seven-day duplicate cooldown, expiry and source mute behavior."

Verification:
  - python3 tools/validate_external_watch_eval.py --manifest evals/external_watch/manifest.v1.json --json
  - private operator sign-off on labels and high-urgency cases

Notes: |
  Deterministic relevance, negative controls, capped shadow selection and all-50
  proposed policy outcomes are implemented. All 50 review_status values remain
  pending_operator because model-authored proposals do not substitute for the
  human operator's notify/ignore/ambiguous judgments.

Files:
  - evals/external_watch/
  - docs/adr/ADR-008-confirmed-external-watch.md
  - src/external_watch/relevance.py
  - src/external_watch/selection.py
  - tools/utd_policy_eval.py

### UTD-4: Source-bounded Shadow Collector

Owner:      codex
Phase:      implementation
Type:       tool:call eval:gate
Depends-On: UTD-DR-1
Status:     implemented_with_residual_human_gate

Objective: |
  Implement a separate, feature-flagged, source-allowlisted UTD sidecar
  collector for Calendar, ISSO and Basic Needs. It detects material changes
  relevant to confirmed profile/watch scopes but sends no Telegram message.

Acceptance-Criteria:
  - "The collector reads only confirmed, active and unexpired scope; preserves
    source identity and recurrence; detects new, updated, cancelled and
    reinstated items idempotently."
  - "Sidecar SQLite is gitignored and derived; the canonical Telegram/PRM DB is
    read-only and untouched. Fetch failure/429/schema drift marks source health
    and never becomes a deletion/change."
  - "No LLM calls, provider egress, browser automation, credential storage,
    general crawler, report generation, Telegram send, production migration or
    dogfood activity occurs."

Verification:
  - adapter golden tests; SSRF/redirect/size/type/429/DST tests; sidecar
    idempotency and restore tests; all 50 eval cases scored locally
  - explicit operator approval recorded before any real source polling

Notes: |
  Operator-approved bounded real-source probes succeeded without production DB
  use or Telegram delivery. Final live snapshot: 102 source items, 32 relevant
  changes, five capped shadow candidates (three urgent), followed by zero
  changes/candidates on the second identical poll. The systemd timer is a
  disabled template and has not been enabled. UTD-5 quality metrics remain
  blocked on genuine human labels.

Files:
  - src/external_watch/
  - systemd/telegram-utd-watch-shadow.service
  - systemd/telegram-utd-watch-shadow.timer
  - tests/
  - docs/audit/UTD-4_SHADOW_PROBE_RESULT_2026-08-28.md

### UTD-5: Shadow Quality Review And Notification Gate

Owner:      human operator + codex
Phase:      validation
Type:       eval:gate
Depends-On: UTD-4
Status:     blocked_pending_human_quality_labels

Objective: |
  Review two to three weeks of shadow observations before any notification is
  sent. Optimise for relevance and safety, not for item volume.

Acceptance-Criteria:
  - "Blind-fixture notification precision is at least 90%, important-case
    recall at least 80%, high-urgency false positives zero, source-link
    correctness 100%, duplicate rate below 2%, and unauthorized actions zero."
  - "Operator review confirms family/spouse eligibility, programme relevance,
    deadlines, benefit claims and mute/digest policy are understandable."
  - "The review records source health, stale runs, parse failures, candidates,
    duplicates blocked and predicted notifications without raw payloads."

Verification:
  - private shadow metrics receipt and operator approval for limited delivery

Notes: |
  Bounded technical shadow evidence now exists: the final live probe saw 102
  source items, 32 relevant changes and five capped predicted candidates, then
  zero changes/candidates on an identical second poll. This does not establish
  precision/recall or delivery readiness; those require genuine human labels.

Files:
  - data/evals/private/
  - docs/audit/

### UTD-6: Unified Bot ASK And Confirmed Low-volume WATCH

Owner:      codex + human operator
Phase:      controlled-delivery
Type:       agent:harness privacy
Depends-On: UTD-DR-2
Status:     implemented_live_timer_enabled_pending_profile_confirmation

Objective: |
  Deliver UTD answers and low-volume notifications through the existing PRM
  Telegram bot, with one visible assistant identity and clear sources/reasons.

Acceptance-Criteria:
  - "UTD ASK answers cite fresh primary evidence or fail closed; archive AI
    research behavior remains unchanged."
  - "Only confirmed watches can notify. Urgent source-supported cancellation or
    deadline alerts may send immediately; all other items use at most one daily
    digest of three to five items, capped at five per day."
  - "Every alert explains why it matches the confirmed programme, career,
    interest, benefit or spouse/family scope; it offers useful/not useful,
    less/more like this, mute and pause controls without one-click permanent
    profile changes."
  - "Delivery uses idempotency receipts, bounded retry and a kill switch. No
    auto-apply, registration, booking, purchase or mutation of university
    systems is available."

Verification:
  - end-to-end tests for proposal/confirm/pause/mute/expire, stale evidence,
    duplicate retry, source-link audit and kill switch
  - explicit operator delivery approval recorded on 2026-09-03; timer is
    enabled but fail-closes until the operator confirms the UTD profile
  - this is not PRM-19 dogfood unless separately approved as such

Files:
  - src/prm/
  - src/bot/prm_handlers.py
  - src/external_watch/
  - tests/

### UTD-7: Personal Relevance Calibration

Owner:      human operator + codex
Phase:      iteration
Type:       eval:gate
Depends-On: UTD-6
Status:     implemented_pending_live_feedback

Objective: |
  Improve the confirmed UTD scope from repeated, explicit feedback while
  preserving operator control and avoiding silent preference learning.

Acceptance-Criteria:
  - "Feedback is aggregated by source/category/reason and proposes, rather than
    applies, changes to interests, negative terms, audience eligibility,
    cadence or caps."
  - "After two to four weeks of controlled delivery, useful or partially useful
    feedback is at least 80%, duplicates remain below 2%, and no unauthorized
    profile or external action is recorded."

Verification:
  - privacy-safe aggregate feedback receipt and explicit confirmation of every
    durable profile/watch adjustment

Files:
  - data/evals/private/
  - docs/audit/

### UTD-DR-1: Profile, Source And Relevance Deep Review

Owner:      codex + human operator
Phase:      deep-review
Type:       compliance:evidence
Depends-On: UTD-1, UTD-2, UTD-3
Status:     planned

Objective: |
  Review the whole profile/source/evaluation phase before any collector exists.
  Confirm that one-bot UTD UX is understandable and that source/relevance scope
  is evidence-backed rather than inferred from generic university assumptions.

Acceptance-Criteria:
  - "The review records profile/watch preview UX, programme/career/family and
    spouse eligibility controls, source-contract evidence, 50-case labels,
    privacy findings, unresolved approvals and corrections."
  - "The review confirms no collector, polling, notification, provider egress
    or second bot was introduced during the preparation phase."

Verification:
  - docs/audit/UTD_DEEP_REVIEW_1_<date>.md
  - focused UX/confirmation tests and evaluation-manifest validation

Files:
  - docs/audit/
  - docs/REVIEW_POLICY.md

### UTD-DR-2: Shadow Collector And Delivery UX Deep Review

Owner:      codex + human operator
Phase:      deep-review
Type:       compliance:evidence
Depends-On: UTD-4, UTD-5
Status:     blocked_pending_shadow_evidence

Objective: |
  Review the complete shadow phase before Telegram delivery. Treat relevance,
  alert burden and clarity as product-quality gates equal to fetch correctness.

Acceptance-Criteria:
  - "The review verifies source safety, stale/failure behavior, idempotency,
    precision/recall, urgency/duplicate caps, kill switch and no-send shadow
    boundary."
  - "The review walks through sanitized ASK, WATCH and notification-preview
    flows for programme, career, benefits and spouse/family scenarios; unclear
    or noisy flows are corrected before delivery approval."

Verification:
  - docs/audit/UTD_DEEP_REVIEW_2_<date>.md
  - private shadow receipt and operator delivery decision

Files:
  - docs/audit/
  - data/evals/private/

### UTD-DR-3: Controlled Delivery And Calibration Deep Review

Owner:      codex + human operator
Phase:      deep-review
Type:       compliance:evidence
Depends-On: UTD-6, UTD-7
Status:     blocked_pending_live_feedback

Objective: |
  Review controlled delivery only after enough real feedback exists. Decide
  whether to keep, narrow, expand or pause sources and notification policies;
  do not convert usage into a dogfood/release claim automatically.

Acceptance-Criteria:
  - "The review records usefulness, duplicate/noise burden, mute/pause use,
    spouse/family eligibility accuracy, source health, privacy and all proposed
    profile changes."
  - "Any expansion of source families, delivery caps, autonomy, retention or
    dogfood status remains a separate explicit operator decision."

Verification:
  - docs/audit/UTD_DEEP_REVIEW_3_<date>.md
  - private aggregate feedback receipt

Files:
  - docs/audit/
  - data/evals/private/
