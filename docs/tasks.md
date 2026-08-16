# Active Task Graph

Status: active
Last updated: 2026-08-16
Baseline: `5dfd38660b7d8d24998b4dcdf801c419c1dc8f7c`
Archive ref: archive-pre-prm-retrofit-2026-08-16
Active ref: refactor-prm-repository-retrofit

Historical PBR, PRM, IRX, PRM-UX, PRM-MAT and PRM-QA task records are preserved in `docs/archive/pre_retrofit_2026-08-16/tasks.pre-retrofit.md` and Git history. Only the current retrofit queue remains active here.

## Dependency graph

```text
RFX-0 -> RFX-1 -> RFX-2 -> RFX-3 -> RFX-4
RFX-2 -> RFX-5
RFX-3/RFX-4/RFX-5 -> RFX-6 -> RFX-7
RFX-7 -> RFX-8 -> RFX-9 -> RFX-10
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
  - id: AC-1
    description: "An archive branch points to the exact pre-retrofit commit."
    verify: "git rev-parse archive/pre-prm-retrofit-2026-08-16"
  - id: AC-2
    description: "The retrofit plan identifies active boundaries and deletion rules."
    verify: "test -f docs/retrofit/RFX_REPOSITORY_RETROFIT.md"

Files:
  - docs/retrofit/RFX_REPOSITORY_RETROFIT.md

### RFX-1: Consolidate Active Documentation

Owner:      codex
Phase:      retrofit
Type:       none
Depends-On: RFX-0
Status:     implemented

Objective: |
  Replace historical encyclopedic handoffs with one current architecture, one active task queue, one concise Codex handoff and one current evidence index.

Acceptance-Criteria:
  - id: AC-1
    description: "Historical task, architecture, handoff and evidence documents are preserved under the pre-retrofit archive."
    verify: "test -f docs/archive/pre_retrofit_2026-08-16/tasks.pre-retrofit.md"
  - id: AC-2
    description: "Active documentation points to the PRM product and the RFX queue only."
    verify: "python tools/playbook_validate.py --root . --check tasks --check references"

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
  - id: AC-1
    description: "Research, brief and chat requests return one typed response contract."
    test: "tests/test_prm_application.py::test_application_returns_one_response_contract"
  - id: AC-2
    description: "An unnamed project-decision request returns clarification without retrieval-backed recommendation."
    test: "tests/test_prm_application.py::test_ambiguous_project_clarifies"

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
  - id: AC-1
    description: "Importing the active bot does not import report-era output modules."
    test: "tests/test_retrofit_boundaries.py::test_active_bot_import_boundary"
  - id: AC-2
    description: "Legacy command dispatch remains available only through explicit legacy mode."
    test: "tests/test_prm_bot_dispatch.py::test_runtime_mode_is_explicit"

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
  - id: AC-1
    description: "The PRM CLI exposes assistant, research and brief commands."
    test: "tests/test_prm_cli.py::test_cli_commands"
  - id: AC-2
    description: "The active systemd template starts the compact PRM CLI."
    verify: "grep -q -- '-m prm.cli assistant' systemd/telegram-prm-assistant.service"

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
  - id: AC-1
    description: "focused-prm excludes report-era renderer tests."
    test: "tests/test_retrofit_boundaries.py::test_focused_tier_excludes_report_era"
  - id: AC-2
    description: "legacy-compat is available for explicit compatibility work."
    verify: "python tools/test_tiers.py legacy-compat --print-only"

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
  - id: AC-1
    description: "No private or historical generated file under data/output is tracked except .gitkeep."
    verify: "git ls-files data/output"
  - id: AC-2
    description: "The .playbook-artifacts directory is not tracked."
    verify: "git ls-files .playbook-artifacts"

Files:
  - .gitignore
  - data/output/
  - .playbook-artifacts/

### RFX-7: Migrate Active Callers Behind Compatibility Adapters

Owner:      codex
Phase:      retrofit
Type:       none
Depends-On: RFX-6
Status:     implemented

Objective: |
  Ensure the active PRM package, Telegram service and Eval V2 do not import report-era renderers, manifests, Radar or Frontier modules; retain explicit compatibility entrypoints for historical commands.

Acceptance-Criteria:
  - id: AC-1
    description: "The active PRM import graph contains no report-era output module."
    test: "tests/test_retrofit_boundaries.py::test_active_prm_has_no_report_imports"
  - id: AC-2
    description: "Eval V2 calls the PRM application boundary."
    test: "tests/test_retrofit_boundaries.py::test_eval_v2_uses_application_boundary"

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
  - id: AC-1
    description: "At least 15 labelled operator interactions exist with workflow and project metadata."
    verify: "operator-approved private smoke receipt"

Files:
  - data/evals/private/

### RFX-9: Delete Dead Legacy Code And Tests

Owner:      codex
Phase:      cleanup
Type:       none
Depends-On: RFX-8
Status:     blocked

Objective: |
  Delete compatibility modules, commands and tests that have no active callers and no observed operator use, relying on the archive branch and Git history for recovery.

Acceptance-Criteria:
  - id: AC-1
    description: "Every deleted Python module has zero active imports and a named replacement."
    verify: "docs/retrofit/RFX_DEEP_REVIEW.md deletion table"
  - id: AC-2
    description: "Focused PRM and legacy-compat checks pass after each bounded deletion."
    verify: "python tools/test_tiers.py focused-prm and python tools/test_tiers.py legacy-compat"

Files:
  - src/
  - tests/

### RFX-10: Deep Review And Retrofit Completion

Owner:      codex
Phase:      review
Type:       compliance:evidence
Depends-On: RFX-7
Status:     in_progress

Objective: |
  Perform a fresh architecture, privacy, test-boundary and repository-truth review and record remaining debt without overstating operator value.

Acceptance-Criteria:
  - id: AC-1
    description: "The deep review records resolved findings, residual risks and exact verification evidence."
    verify: "test -f docs/retrofit/RFX_DEEP_REVIEW.md"

Files:
  - docs/retrofit/RFX_DEEP_REVIEW.md
  - docs/EVIDENCE_INDEX.md
  - docs/IMPLEMENTATION_JOURNAL.md
