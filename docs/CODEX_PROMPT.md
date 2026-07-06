# CODEX_PROMPT — Session Handoff
_v3.6 · 2026-07-06 · telegram-research-agent_

---

## Current State

- Memory unification and Roadmap v3 are complete.
- Active strategic pivot: the project should become an AI Knowledge
  Intelligence Desk. The main weekly artifact should be a human-readable HTML
  intelligence report built from Telegram knowledge atoms and temporal idea
  threads. MVP Radar and project recommendations remain downstream consumers,
  not the center of the product. Obsidian is a generated human-facing knowledge
  vault projection, not the runtime source of truth.
- Operational incident on 2026-07-06: `telegram-digest.timer` had been inactive
  since 2026-06-22, so weekly Research Brief/Implementation Ideas stopped
  running while ingest and MVP weekly continued. The timer was manually
  restarted and 2026-W28 artifacts were regenerated. Weekly delivery health
  checks now cover inactive timers, missing current-week reports after the
  scheduled window, and root-owned output files; SQLite usage-log contention
  remains the next P0 item.
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
  - Research Brief delivery now adds a reader-facing `Evidence & Source Mix`
    section and Telegram evidence line from local receipt evidence lookup,
    source-link counts, top channels, fallback state, and deterministic
    confidence wording.
  - Demand-to-MVP Radar now rewrites contradictory LLM `mvp-of-week` Decision
    Gate and Build-Worthy sections to deterministic gated truth; Markdown and
    JSON agree on the final recommendation.
  - Demand-to-MVP Radar now renders `mvp-of-week` as a Candidate Dossier with
    canonical `dossier_status`, decision, confidence, next action, missing
    evidence, next experiment, kill criteria, and explicit existing-project
    context. Telegram Research Agent delivery can display the canonical status.
  - Demand-to-MVP Radar now exposes selected-candidate source mix in Markdown
    and JSON, including readiness, missing credentials, Reddit API vs
    SERP-indexed Reddit status, and GitHub primary/repeated-variant role.
    Telegram Research Agent delivery includes the readiness label.
  - Demand-to-MVP Radar now has focused report-quality contract tests for the
    Candidate Dossier top block, required sections, source-mix card, missing
    evidence, kill criteria, existing-project context, and no contradictory
    build-ready claims when gates fail.
  - Weekly editorial memory now builds operator/system-authored
    keep/change/demote/test-next-week notes from artifact feedback, usefulness
    logs, report-quality findings, receipt health, and source down-rank
    explanations via `memory inspect-editorial-memory`; monthly
    `operator-report` summarizes weeks with editorial memory signals.
  - Pathway-ready live source intelligence is implemented as an optional sidecar
    contract: Telegram ingestion writes append-only source events, `live-source-index`
    builds deterministic snapshots, and `mvp-weekly --with-live-source-index`
    passes context-only live intelligence to Demand-to-MVP Radar.
  - `health-check` now reports weekly delivery status for
    `telegram-digest.timer`, current-week digest presence after the scheduled
    Monday window, and root-owned `data/output` files; `scripts/healthcheck.sh`
    invokes this Python health surface.
  - 2026-W24 artifact review showed that internal signal quality improved but
    reader-facing report quality is weak: no first-screen decision brief,
    buried trend summary, visible internal `Matches: ...` traces, contradictions
    between digest/study/project-insights outputs, and Radar gate contradiction.
- The current report-quality, Radar handoff, cost, artifact consistency,
  editorial memory, and initial Pathway live-source-intelligence task queue is
  implemented. Add the next roadmap item before starting new implementation
  work.
- VPS cognition vault:
  `/srv/codex-entropy/repos/product-3/engineering-cognition-vault`; use it as
  a downstream navigation layer, not as the source of truth. For AI source
  intelligence, prefer a dedicated `ai-intelligence-vault` or a clearly scoped
  generated namespace such as `_generated/ai-intelligence/`. Do not create one
  note per Telegram post.
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
- Weekly reports now have a reader-facing evidence/source-mix summary.
  Deterministic quality gates still log/report the current failure examples
  from `docs/report_quality_roadmap.md`.
- Demand-to-MVP Radar final-gate contradictions, Candidate Dossier shape,
  source-mix truth surface, and report-quality contract tests are fixed for
  `mvp-of-week`.
- Internal LLM cost guardrails now evaluate existing `llm_usage` rows without
  new model calls. `cost-stats` and monthly `operator-report` show weekly
  budget status, highest-cost category, spike warnings, and suggested actions.
- Weekly artifact consistency validation now covers Study Plan vs Research
  Brief signal counts, Project Insights vs Research Brief project section, MVP
  delivery build-readiness contradictions, and monthly operator-report
  consistency warnings.
- Weekly editorial memory is now persisted as local operator/system-authored
  Markdown sidecars under `data/output/editorial_memory/` when inspected
  explicitly, and is summarized by monthly `operator-report`.
- Pathway itself is not a required runtime dependency yet. The shipped boundary
  is a Pathway-ready JSONL event stream plus deterministic fallback snapshot;
  Radar treats the snapshot as context only, not decision-grade external
  evidence.
- The next roadmap is `docs/ai_knowledge_intelligence_roadmap.md`. Start with
  KIR tasks in `docs/tasks.md`.

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

Start with the first open KIR task in `docs/tasks.md`.

Current first task:

```text
KIR-002 — Make LLM usage recording non-blocking under SQLite contention
```

Do not start by prompt-tuning the old Research Brief. The strategic direction is:

```text
all Telegram posts -> knowledge atoms -> temporal idea threads ->
weekly AI intelligence HTML report -> generated Obsidian vault ->
personal read/try/build loop
```

Reference documents:

- `docs/tasks.md`
- `docs/next_development_roadmap.md`
- `docs/report_quality_roadmap.md`
- `docs/ai_knowledge_intelligence_roadmap.md`
- `docs/mvp_weekly_radar.md`
- `docs/COGNITION_MANIFEST.md`
- `docs/VPS_COGNITION_VAULT.md`
- `docs/IMPLEMENTATION_CONTRACT.md`
- `docs/architecture.md`

Radar cross-repo path for RADAR tasks:

```text
/srv/openclaw-you/workspace/Demand-to-MVP-Radar
```
