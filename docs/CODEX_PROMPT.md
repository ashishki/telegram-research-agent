# CODEX_PROMPT - Compact Session Handoff

Version: 4.1
Date: 2026-07-10
State: PGI-001 implemented locally and verified; PGI-002 is next but should be
started as a separate PR-sized slice

## Current Product Direction

`telegram-research-agent` is no longer a Telegram digest project. It is becoming
a private Personal AI Decision & Learning Intelligence System:

```text
source observations -> evidence -> claims -> atoms -> threads ->
Brief / Atlas / Hermes / Project Intelligence / Learning Intelligence ->
decisions -> experiments -> outcomes -> feedback/evaluation
```

Canonical roadmap:

```text
docs/portfolio_grade_intelligence_roadmap.md
```

Canonical active backlog:

```text
docs/tasks.md
```

Next implementation task:

```text
PGI-002 - Operator Context, Feedback Provenance And Explainable Ranking
```

## Verified Baseline

- Knowledge Atom storage/extraction exists and has focused tests.
- Idea Thread storage/momentum exists and has focused tests.
- Weekly AI visual report/workbook contract exists, but the workbook is now a
  historical/legacy surface rather than the target main product surface.
- Split Weekly Intelligence Brief and Knowledge Atlas artifacts exist, but they
  are `partial` relative to the target decision cockpit and navigable Atlas.
- Canonical intelligence sidecar contract `tra-intelligence-contract.v1` is now
  implemented locally for workbook/Brief/Atlas projections with sanitized eval
  fixtures.
- Hermes/PI facade, tools, chat, and intent routing exist as a read-only,
  bounded foundation; product dogfood/evals remain incomplete.
- Feedback intake and action-status helpers exist; provenance, corrections,
  effect windows, and ranking explanations remain incomplete.
- Strategy Reviewer exists as advisory-only and must not mutate code/config.
- Market/business context for Radar exists and is `context_only`.
- Sibling `Demand-to-MVP-Radar` repo exists at
  `/srv/openclaw-you/workspace/Demand-to-MVP-Radar`; RVE query planning,
  matched external evidence, adapters, and gate tests are implemented there.
  Live weekly validation still needs dogfood.
- GitHub connector returned no open PRs or open issues for either repo on
  2026-07-10.

## Active Task Graph

Primary sequence:

```text
PGI-001 -> PGI-002 -> PGI-003 -> PGI-004 -> PGI-005 -> PGI-006 -> PGI-007 -> PGI-008
```

Parallel Radar sequence:

```text
RADAR-PGI-001 -> RADAR-PGI-002 -> RADAR-PGI-003
```

Do not restart from KIR/HPI/RVE historical queues. Those are mapped in
`docs/tasks.md`.

## PGI-001 Completion

Status: completed locally on 2026-07-10.

Implemented:

- `tra-intelligence-contract.v1` constants, builder, and validator in
  `src/output/ai_report_contract.py`.
- Explicit SourceObservation, EvidenceItem, Claim, KnowledgeAtom, IdeaThread,
  Decision, Experiment, Outcome, and projection-boundary fields in sidecars.
- Weekly Brief and Knowledge Atlas sidecars now include `contract_version`,
  `intelligence_contract`, and rendered HTML meta tags for contract parity.
- Retrieval adds `canonical_claim` and `canonical_evidence` items while legacy
  workbook readers remain compatible.
- Hermes facade strong-signal fallback can read canonical claims when
  `claim_cards` are absent.
- Opportunity seeds and market context seed rows carry
  `tra-radar-intelligence-contract.v1` plus
  `intelligence_contract_version=tra-intelligence-contract.v1`.
- Context-only Radar evidence remains unable to satisfy demand/build gates.
- Sanitized fixtures were added under
  `tests/fixtures/intelligence_contract/`.

Files changed for PGI-001:

- `src/output/ai_report_contract.py`
- `src/output/weekly_intelligence_brief.py`
- `src/output/knowledge_atlas_report.py`
- `src/output/intelligence_retrieval_items.py`
- `src/output/opportunity_seed_export.py`
- `src/output/market_context_lens.py`
- `src/assistant/pi_facade.py`
- `tests/test_ai_report_contract.py`
- `tests/test_split_intelligence_reports.py`
- `tests/test_intelligence_retrieval_items.py`
- `tests/test_opportunity_seed_export.py`
- `tests/fixtures/intelligence_contract/`

Verification passed:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ai_report_contract.py tests/test_split_intelligence_reports.py tests/test_intelligence_retrieval_items.py tests/test_opportunity_seed_export.py
PYTHONPATH=src python3 -m pytest tests/test_ai_visual_report.py tests/test_pi_facade.py tests/test_pi_tools.py
git diff --check
```

Review notes:

- Correctness: unsupported decision-grade claims and context-only gate misuse
  fail contract validation.
- Provenance/evidence safety: decision-grade evidence requires source
  observation refs, verified quote/excerpt, non-weak tier, and non-context-only
  status.
- Sidecar/rendered parity: Brief/Atlas HTML meta tags match sidecar contract
  versions.
- Backward compatibility: old workbook/split fixtures still read through legacy
  readers; new canonical retrieval items are additive.
- Privacy/secrets: fixtures are sanitized; no `.env`, secrets, private
  generated reports, migrations, LLM runs, or full backfills were added.
- Hermes/Radar: Hermes remains read-only; Radar context-only records still do
  not satisfy demand gates.

## PGI-002 Handoff

Goal: add operator context, feedback provenance, and explainable ranking without
weakening the PGI-001 evidence contract.

Likely files:

- `src/db/ai_report_feedback.py`
- `src/output/personalize.py`
- `src/output/ai_intelligence_report.py`
- `src/output/weekly_intelligence_brief.py`
- `src/assistant/pi_facade.py`
- `tests/test_ai_report_feedback.py`
- `tests/test_ai_intelligence_report.py`
- `tests/test_pi_facade.py`

Verification target:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ai_report_feedback.py tests/test_ai_intelligence_report.py tests/test_pi_facade.py tests/test_action_status.py
```

Stop before PGI-002 implementation if the slice requires a DB migration plus
renderer/ranking/Hermes changes in one pass; split it into append-only feedback
provenance first.

## Non-Negotiable Rules

- Do not run full archive backfill unless a task explicitly scopes it.
- Do not run expensive LLM jobs for ordinary verification.
- Do not implement raw Telegram firehose RAG by default.
- Do not add assistant mutation tools.
- Do not let Hermes run Codex or edit YAML/profile/projects/scoring.
- Do not treat no feedback as negative.
- Do not treat market/business Telegram context as external demand evidence.
- Do not hide Radar missing/stale/evidence-gap states.
- Do not commit private generated reports, raw exports, secrets, or `.env`.

## Key Docs

- `docs/portfolio_grade_intelligence_roadmap.md`
- `docs/tasks.md`
- `docs/intelligence_evaluation_framework.md`
- `docs/portfolio_evidence_plan.md`
- `docs/mvp_radar_integration_contract.md`
- `docs/operator_ai_systems_learning_roadmap.md`
- `docs/operator_workflow.md`
- `docs/hermes_pi_assistant_roadmap.md`
- `docs/ai_knowledge_intelligence_roadmap.md`
- `docs/ai_intelligence_workbook_roadmap.md`
- `docs/mvp_weekly_radar.md`

## Current Repository Caveat

`docs/artifacts/ai-decision-intelligence-2026-W28/manual-quality-eval-2026-07-07.md`
is untracked in the working tree at the time of this handoff. Treat it as
operator/private review material unless the operator explicitly asks to commit
or sanitize it.
