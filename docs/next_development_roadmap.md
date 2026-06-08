# Next Development Roadmap

Status: active next-step roadmap
Last updated: 2026-06-08

## Purpose

This roadmap turns the remaining report-quality, operator-feedback, Radar
handoff, and internal guardrail ideas into AI-development tasks.

The product should stay a private operator research system until weekly briefs
repeatedly influence real decisions. The next work should improve reader
usefulness, report consistency, feedback quality, and Radar honesty without
adding a generic UI or a runtime dependency on Entropy Core.

Detailed report-quality task scope lives in
`docs/report_quality_roadmap.md`.

## Scope

In scope:

- Core-compatible receipt evidence checks for delivered Research Briefs.
- Schema compatibility checks for the Core-compatible receipt view.
- Product-local feedback improvements.
- Monthly operator reporting.
- Clearer source down-ranking explanations.
- Production validation of Telegram reaction and callback paths.
- Product-split readiness criteria for Telegram Channel Intelligence.
- Reader-facing Research Brief decision summary.
- Deterministic report-quality gates before delivery.
- Artifact-level Telegram feedback buttons.
- Internal LLM cost/guardrail dogfooding.
- Demand-to-MVP Radar candidate dossier and source-gate consistency.

Out of scope:

- Entropy Core as a runtime dependency.
- Public/customer UI.
- Generic Telegram summarization.
- AI-invented source trust or unexplained ranking changes.
- Public report dashboard before private weekly reports are consistently useful.
- Radar build-ready recommendations that are not supported by source mix gates.

## Current Baseline

Implemented:

- Local `research_brief_receipts` SQLite source of truth.
- Research Brief receipt creation during weekly digest generation.
- Delivery reference updates for Telegraph, Telegram, and fallback delivery.
- Deterministic receipt verification and operator review.
- `memory inspect-receipts` for local receipt inspection.
- `memory inspect-core-receipt` for Core-compatible receipt JSON.
- `src/proof_receipts.py` adapter and deterministic Core-compatible hash.
- Deterministic Core evidence lookup checks through
  `memory inspect-core-receipt --verify-evidence`.
- Core receipt schema compatibility tests and product-local boundary guards.
- Artifact-level feedback, monthly operator reporting, source down-rank
  explanations, product split gate, and OPS validation command surfaces.
- Artifact-level Telegram feedback buttons on Research Brief, Implementation
  Ideas, MVP weekly, and Study Plan notifications.
- Weekly audit notes include the Core-compatible hash when source evidence refs
  exist.
- Channel Intelligence groundwork: schema migrations, repeated-claim
  extraction, source observations, active-project links, narrative candidates,
  inspection CLI, and optional Markdown report.
- 2026-W24 review showed improved internal signal quality but weak
  reader-facing packaging: no decision brief, buried trend summary, visible
  internal matching traces, contradictions between Study Plan/Project Insights
  and digest facts, and a Radar report that both recommended
  `focused_experiment` and later downgraded the same candidate.

Active next task details:

- `docs/tasks.md` lists the active queue.
- `docs/report_quality_roadmap.md` contains the implementation handoff,
  acceptance criteria, touched-file guidance, and Radar repo paths.

## Phase 1 - Receipt Evidence Confidence

Goal: make Core-compatible receipts checkable, not just printable.

### ENT-CORE-1 - Core Evidence Lookup Checks

Status: implemented.

Implemented via `verify_core_research_brief_evidence_refs(...)` and
`memory inspect-core-receipt --verify-evidence`.

Implement a deterministic checker for the Core-compatible `evidence_refs`
returned by `build_core_research_brief_receipt(...)`.

Expected behavior:

- `signal_evidence_item:<id>` refs resolve to rows in `signal_evidence_items`.
- `telegram_source_link` refs are checked for valid Telegram post URL shape.
- Missing or stale refs produce a clear failure or `needs_review` result.
- The checker runs without an Entropy Core runtime.
- The checker can be called from CLI for delivered briefs.

Suggested surface:

- Add a helper near `proof_receipts.py` or a small product-local verifier module.
- Add `memory verify-core-receipt` or extend `inspect-core-receipt` with a
  verification field, whichever fits existing CLI patterns better.

Acceptance criteria:

- A receipt with valid evidence refs reports `passed`.
- A receipt with a missing `signal_evidence_item` reports `failed`.
- A receipt with malformed Telegram source URLs reports `failed`.
- A receipt with no Core-compatible evidence refs keeps using the existing
  adapter rejection path.
- Tests cover valid, missing-row, malformed-link, and no-evidence paths.

Verification command:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_research_brief_receipts tests.test_research_brief_receipt_cli
```

### ENT-CORE-2 - Core Receipt Schema Compatibility Checks

Status: implemented.

Implemented in `tests/test_core_research_brief_receipt.py` by pinning required
fields, field types, evidence-ref structure, schema version, and deterministic
hash behavior.

Add a small schema compatibility test for the Core-compatible receipt payload.

Expected behavior:

- Required top-level fields are pinned by tests.
- Field meanings stay stable across local receipt schema changes.
- Receipt hash remains deterministic for equivalent payloads.
- Backward-incompatible changes require an explicit schema version change.

Acceptance criteria:

- Tests fail if required Core fields disappear or change type.
- Tests document allowed optional fields.
- The schema check does not require external packages unless already present.

Verification command:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_research_brief_receipt_cli
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 tests/test_core_research_brief_receipt.py
```

### ENT-CORE-3 - Product-Local Boundary Guard

Status: implemented.

Implemented in `tests/test_core_boundaries.py`; Core remains derived proof
vocabulary and receipt storage/delivery/review/usefulness stay product-local.

Keep Entropy/Core as proof vocabulary only.

Rules for future AI agents:

- Do not move Telegram delivery, operator review, usefulness logs, source
  parsing, or digest generation into Entropy/Core modules.
- Do not require Entropy/Core runtime to run weekly digest generation.
- Keep `research_brief_receipts` as the local source of truth.
- Core-compatible views should be derived from local rows.

Acceptance criteria:

- Docs continue to state Core is optional vocabulary.
- Tests for digest generation do not instantiate or depend on an Entropy/Core
  runtime.

## Phase 2 - Feedback And Operator Reporting

Goal: improve the feedback loop from weekly reports to system tuning.

### FBK-1 - Artifact-Level Feedback

Status: implemented.

Implemented via `artifact_feedback_logs`, `log-artifact-feedback`, and
`memory inspect-artifact-feedback`.

Add feedback that targets specific brief sections or artifacts, beyond the
weekly usefulness log.

Expected behavior:

- Operator can mark a specific section, item, artifact, or evidence group as
  useful, weak, noisy, or decision-impacting.
- Feedback links back to `week_label`, artifact path or digest row, and optional
  source evidence refs.
- Existing `weekly_usefulness_logs` remains valid.

Acceptance criteria:

- Existing weekly usefulness flow still works.
- New feedback can be inspected from CLI.
- Feedback does not become model-authored source trust by itself.

### RPT-1 - Monthly Operator Report

Status: implemented.

Implemented via `operator-report --month YYYY-MM`.

Add a monthly report summarizing system quality and usage.

Include:

- Reaction sync counts and useful/noisy reaction trends.
- Inline decision button counts.
- Weekly usefulness summaries.
- LLM cost and token trends.
- Empty/low-signal weeks from Research Brief receipts.
- Delivery fallback count.

Acceptance criteria:

- CLI command renders a monthly Markdown or text report.
- Report uses existing local tables and gracefully handles missing data.
- Tests cover a month with mixed feedback, costs, low-signal flags, and
  fallback delivery.

## Phase 3 - Source Trust Transparency

Goal: make source ranking and down-ranking inspectable.

### TRUST-1 - Source Down-Rank Explanations

Status: implemented.

Implemented via `memory explain-source-downrank`.

Surface why a channel/source is repeatedly down-ranked.

Possible observed reasons:

- Many posts scored as noise.
- Few or no operator-positive reactions.
- Weak or missing source links.
- Repeated claims later marked failed, weak, or not useful.
- Low project relevance across recent windows.

Acceptance criteria:

- Source trust explanations are based on observed local data only.
- CLI inspection can show top down-ranked sources and reason counts.
- No model-generated trust claim is stored as fact without observed backing.

## Phase 4 - Production Validation

Goal: prove the deployed Telegram loops work with live Telegram behavior.

### OPS-1 - Validate Reaction Sync Against Live Telegram Channels

Status: implemented validation surface; live success depends on an observed
Telegram reaction event.

Implemented via `ops-validate reaction-sync`. The command reports `passed` when
local `reaction_sync_state` contains recent Telegram reaction evidence and
`needs_live_event` when no recent live event is present.

Confirm current user reactions are visible through Telethon in production.

Acceptance criteria:

- A known reaction on a source post is imported as feedback/tag state.
- Logs or CLI output show the sync path and affected post.
- Failure modes are documented if Telegram visibility is limited.

### OPS-2 - Validate Inline Button Callbacks In Deployed Bot Polling

Status: implemented validation surface; live success depends on an observed
Telegram callback event.

Implemented via `ops-validate callbacks`. The command checks that callback
updates are enabled in bot polling and reports `passed` when recent
`telegram_button` decisions exist.

Confirm inline callback dispatch works in the deployed bot process.

Acceptance criteria:

- A live inline button press reaches the callback handler.
- The decision is recorded in `decision_journal`.
- Bot polling logs show callback updates are enabled.

## Phase 5 - Product Split Readiness

Goal: decide whether Telegram Channel Intelligence deserves a productized split.

### PROD-1 - Product Split Decision Gate

Status: implemented.

Implemented via `product-split-gate`, which returns `go` only when the local
evidence threshold is met; otherwise it returns `no_go`.

Do not split into a product workspace until the private tool shows repeated
operator value.

Suggested evidence threshold:

- At least four useful weekly reports in a recent rolling window.
- At least two operator decisions linked to report evidence.
- Source trust or repeated-claim intelligence changes what the operator reads or
  builds.
- Core receipt/evidence checks are stable enough to audit delivered briefs.

Acceptance criteria:

- A documented go/no-go decision exists before any product split.
- If the decision is "go", create a separate product plan instead of mixing
  public product UI into this private assistant.

## Phase 6 - Reader-Facing Report Quality

Goal: turn working evidence infrastructure into useful operator-facing
artifacts.

Detailed tasks: `docs/report_quality_roadmap.md`.

### RQ-2 - Report Quality Gates Before Delivery

Status: implemented.

Add deterministic report-quality validation before weekly artifacts are treated
as clean.

Must catch:

- `Matches: ...` internal traces in user-facing takeaways.
- missing Decision Brief section.
- buried or missing change summary.
- Study Plan claiming no Telegram signals when digest/evidence rows show
  signals.
- Project Insights claiming no insights while the digest contains project
  insights.
- overlong reports without a short decision layer.

### RQ-1 - Weekly Decision Brief Header

Status: implemented.

The Research Brief and Telegram notification must start with a compact summary:

- evaluated window and post count;
- signal funnel;
- change versus previous week;
- top actions;
- evidence/confidence status;
- source mix summary.

### RQ-3 - Artifact Feedback Buttons

Status: implemented.

Implemented as low-friction inline feedback buttons for Research Brief,
Implementation Ideas, MVP weekly, and Study Plan notifications. Buttons write
to `artifact_feedback_logs` and feed monthly/operator reporting; existing
per-idea Implementation Ideas decision buttons are preserved.

### RQ-4 - Reader-Facing Evidence And Source Mix Summary

Status: open.

Expose proof-receipt/evidence lookup status in plain language inside the weekly
Research Brief and Telegram notification.

### RQ-5 - Weekly Artifact Consistency Contract

Status: open.

Ensure weekly artifacts agree on the same run facts: post count, signal counts,
project insight state, receipt status, and MVP recommendation.

## Phase 7 - Radar Candidate Honesty

Goal: make Demand-to-MVP Radar output an honest candidate dossier instead of an
overconfident "MVP of the Week" story.

Radar repo path:

```text
/srv/openclaw-you/workspace/Demand-to-MVP-Radar
```

Detailed tasks: `docs/report_quality_roadmap.md`.

### RADAR-2 - Single Final Gate And Contradiction Guard

Status: open.

Deterministic gates in Radar must override LLM report text. Markdown and JSON
must agree on one final recommendation/status.

Primary Radar file:

```text
/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/mvp_weekly.py
```

### RADAR-1 - Candidate Dossier Output

Status: open.

Change weekly Radar output to a Candidate Dossier with a canonical status:
`build`, `focused_experiment`, `investigate`, or `reject`.

### RADAR-3 - Source Mix Truth Surface

Status: open.

Show selected-candidate source mix, missing credentials, Reddit/GitHub
limitations, and whether external evidence truly corroborates the Telegram
seed.

### RADAR-4 - Radar Report Quality Test Suite

Status: open.

Add tests for candidate dossier contract, no contradictory gates, source mix
card, missing evidence, kill criteria, and existing-project context.

## Phase 8 - Internal Cost Guardrails

Goal: dogfood the `LLM Cost & Guardrail Budget Sentinel` idea inside the
private system before treating it as a separate product.

### COST-1 - Internal LLM Cost And Guardrail Sentinel

Status: open.

Use existing `llm_usage` rows to expose budget thresholds, cost spikes,
highest-cost categories, and suggested downgrade/defer actions in `cost-stats`
and `operator-report`.

### MEM-1 - Weekly Editorial Memory

Status: open.

Persist weekly report-quality learnings from feedback and quality findings so
future report generation can improve from local state rather than chat history.

## AI-Development Rules For This Roadmap

- Read `docs/CODEX_PROMPT.md`, `docs/PROJECT_PLAN.md`,
  `docs/tasks.md`, `docs/report_quality_roadmap.md`, and this roadmap before
  implementation.
- Start from the highest-priority open task in `docs/tasks.md`.
- Define touched files, acceptance criteria, and verification command before
  code edits.
- Prefer local deterministic checks before adding model calls.
- Add focused tests for every behavior change.
- Update docs only when command surface, architecture boundaries, or task state
  changes.
- Do not reimplement existing receipt builders, storage helpers, or receipt CLI.
