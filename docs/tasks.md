# Active Task Graph

Status: active
Last updated: 2026-08-28
Baseline: `5dfd38660b7d8d24998b4dcdf801c419c1dc8f7c`
Archive ref: origin/archive/pre-prm-retrofit-2026-08-16
Active ref: master

Historical PBR, PRM, IRX, PRM-UX, PRM-MAT and PRM-QA task records are preserved in `docs/archive/pre_retrofit_2026-08-16/tasks.pre-retrofit.md` and Git history. Only the current retrofit queue remains active here.

## Dependency graph

```text
RFX-0 -> RFX-1 -> RFX-2 -> RFX-3 -> RFX-4
RFX-2 -> RFX-5
RFX-3/RFX-4/RFX-5 -> RFX-6 -> RFX-7
RFX-7 -> RFX-8 -> RFX-9
RFX-7 -> RFX-10 -> UTD-P0
UTD-P0 -> UTD-1 / UTD-2 / UTD-3
UTD-1 / UTD-2 / UTD-3 -> UTD-4 -> UTD-5 -> UTD-6 -> UTD-7
```

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
Status:     planned

Objective: |
  Define one confirmation-gated UTD profile and typed watch proposal inside the
  existing PRM Telegram bot. The profile must express the operator's programme,
  academic/career goals, AI/engineering interests, eligible audiences, spouse
  and family context, notification limits, timezone, and review/expiry date
  without silently creating durable preferences or external monitoring.

Acceptance-Criteria:
  - "The bot can show a human-readable draft of its UTD scope before any save:
    sources, filters, positive/negative terms, programme/career relevance,
    spouse/family eligibility, America/Chicago timezone, cadence, daily cap,
    expiry and pause/mute choices."
  - "A profile or watch is persisted only through the existing exact
    confirmation flow; unconfirmed chat text and a single feedback click do not
    mutate the profile."
  - "The active UI remains one bot: UTD ASK/WATCH complements archive AI
    research and does not create a second Telegram bot or a report timer."

Verification:
  - focused tests for proposal rendering, exact confirmation, expiry, pause,
    mute, spouse/family eligibility and no-write cancellation
  - privacy review confirms no programme/family details enter public fixtures,
    ordinary logs or provider prompts

Files:
  - src/assistant/pi_memory.py
  - src/assistant/prm_post_answer_actions.py
  - src/bot/prm_handlers.py
  - tests/

### UTD-2: Sanitized Primary-source Contract Capture

Owner:      human operator
Phase:      evidence
Type:       eval:gate privacy
Depends-On: UTD-P0
Status:     planned

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

Files:
  - tests/fixtures/external_watch/
  - evals/external_watch/manifest.v1.json
  - docs/external_watch_p0_readiness.md

### UTD-3: Operator Evaluation Labels And Relevance Policy

Owner:      human operator + codex
Phase:      evaluation
Type:       eval:gate
Depends-On: UTD-P0
Status:     planned

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

Files:
  - evals/external_watch/
  - docs/adr/ADR-008-confirmed-external-watch.md

### UTD-4: Source-bounded Shadow Collector

Owner:      codex
Phase:      implementation
Type:       tool:call eval:gate
Depends-On: UTD-1, UTD-2, UTD-3
Status:     blocked_pending_operator_approval

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

Files:
  - src/external_watch/
  - systemd/telegram-utd-watch-shadow.service
  - systemd/telegram-utd-watch-shadow.timer
  - tests/

### UTD-5: Shadow Quality Review And Notification Gate

Owner:      human operator + codex
Phase:      validation
Type:       eval:gate
Depends-On: UTD-4
Status:     blocked_pending_shadow_evidence

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

Files:
  - data/evals/private/
  - docs/audit/

### UTD-6: Unified Bot ASK And Confirmed Low-volume WATCH

Owner:      codex + human operator
Phase:      controlled-delivery
Type:       agent:harness privacy
Depends-On: UTD-5
Status:     blocked_pending_delivery_approval

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
  - explicit operator delivery approval; this is not PRM-19 dogfood unless
    separately approved as such

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
Status:     blocked_pending_live_feedback

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
