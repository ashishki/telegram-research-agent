# Active Task Graph

Status: active
Last updated: 2026-08-16
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
