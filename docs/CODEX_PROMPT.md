# CODEX_PROMPT — Session Handoff
_v3.4 · 2026-06-08 · telegram-research-agent_

---

## Current State

- Memory unification and Roadmap v3 are complete.
- Recent shipped changes:
  - Telegram reaction sync imports source-post reactions as tags/feedback.
  - Implementation Ideas now send inline feedback cards and record decisions in `decision_journal`.
  - Bot polling callback dispatch has an integration-style unit test around `bot.run_bot`.
  - Implementation Ideas require concrete Telegram source-post links or render an insufficient-evidence note.
  - Weekly Research Brief usefulness can be recorded through `log-usefulness` into `weekly_usefulness_logs`.
  - Empty/low-signal digest health alerts are included in delivery notifications and trended in `score-stats` from Research Brief receipts.
  - README and active docs are aligned with the current delivery/feedback behavior.
  - Telegram Channel Intelligence design, schema migrations, deterministic repeated-claim extraction, canonical source-observation refresh, active-project intelligence links, narrative candidate refresh, inspection CLI, and optional Markdown report surface are captured in `docs/telegram_channel_intelligence.md`.
  - Research Brief receipt schema, storage helpers, generation-time receipt creation, delivery ref updates, deterministic verification checks, CLI inspection, operator review, and optional operator-only audit notes are implemented via `research_brief_receipts`.
  - `src/config/projects.yaml` has current project context for active repos.
  - README/docs were cleaned; historical material moved under `docs/archive/`.
  - Core schema compatibility tests, product-local Core boundary guards,
    artifact-level feedback, monthly operator report, source down-rank
    explanations, OPS validation surfaces, and the product split gate are
    implemented.
  - Deterministic report-quality gates now catch user-visible internal
    `Matches: ...` traces, missing/buried summary structure, Study Plan/digest
    contradictions, Project Insights contradictions, evidence/source-confidence
    issues, and overlong unsummarized artifacts. Critical findings are logged
    and included in Research Brief delivery notifications without blocking
    delivery; `operator-report` surfaces monthly report-quality findings.
  - Reader-facing Research Brief now starts with a deterministic Decision Brief,
    Actions This Week, and early What Changed summary; Telegram notification
    includes a compact post -> strong/watch/noise -> actions funnel.
  - Artifact-level Telegram feedback buttons now attach to Research Brief,
    Implementation Ideas, MVP weekly, and Study Plan delivery notifications and
    record rows in `artifact_feedback_logs`.
  - 2026-W24 artifact review showed that internal signal quality improved but
    reader-facing report quality is weak: no first-screen decision brief,
    buried trend summary, visible internal `Matches: ...` traces, contradictions
    between digest/study/project-insights outputs, and Radar gate contradiction.
- Active implementation tasks are now report quality and Radar handoff in
  `docs/tasks.md` and `docs/report_quality_roadmap.md`.
- VPS cognition vault: `/srv/codex-entropy/repos/product-3/engineering-cognition-vault`; use it as a downstream navigation layer, not as the source of truth.
- In this environment, `pytest` may be unavailable; verified fallback is `PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest ...`.
- Orchestrator-to-Codex execution path: write prompt to file, then `codex exec -s workspace-write < /tmp/prompt.md`

---

## What Exists

- Telegram ingestion, normalization, scoring, and topic assignment
- project relevance, personalization, and weekly report generation
- explicit feedback and tagging
- operator-authored weekly usefulness logs
- derived `channel_memory` and `project_context_snapshots`
- `signal_evidence_items` and `decision_journal` tables (unified memory)
- implementation-idea triage and rejection memory
- implementation-idea evidence guard for missing/non-Telegram source-post URLs
- scope-first retrieval helpers
- autonomous signal discovery via preference judge (category + confidence gate)

---

## Known Open Issues

- Live validation still needed for Telegram reaction visibility through Telethon.
- Live validation still needed for inline callback handling in the deployed bot process.
- Low-signal weeks now produce alerts and `score-stats` reports recent empty/low-signal receipt trends.
- June operator feedback is sparse: recent monthly report showed zero reaction
  sync actions, zero weekly usefulness logs, and zero artifact feedback rows.
  Low-friction artifact feedback buttons are now shipped; live operator use is
  still needed before the system can learn taste from artifact-level feedback.
- Weekly reports still need a fuller reader-facing evidence/source-mix summary.
  Deterministic quality gates now log/report the current failure examples from
  `docs/report_quality_roadmap.md`.
- Demand-to-MVP Radar must not deliver a report that says a candidate is both
  `focused_experiment` and downgraded by source mix gates.

---

## Active Architecture State

The weekly pipeline now has:
- project context snapshots (GitHub-derived)
- channel memory
- decision journal
- evidence items
- preference judge with generous inclusion policy

---

## Exact Next Execution Step

Start with `RQ-4 - Reader-Facing Evidence And Source Mix Summary` from
`docs/tasks.md`.
Use `docs/report_quality_roadmap.md` for detailed task scope, acceptance
criteria, touched-file guidance, and verification commands.

Before implementation, define scope, touched files, acceptance criteria, and verification command.

Reference documents:

- `docs/tasks.md`
- `docs/next_development_roadmap.md`
- `docs/report_quality_roadmap.md`
- `docs/mvp_weekly_radar.md`
- `docs/COGNITION_MANIFEST.md`
- `docs/VPS_COGNITION_VAULT.md`
- `docs/IMPLEMENTATION_CONTRACT.md`
- `docs/architecture.md`

Radar cross-repo path for RADAR tasks:

```text
/srv/openclaw-you/workspace/Demand-to-MVP-Radar
```
