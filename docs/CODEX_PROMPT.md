# CODEX_PROMPT — Session Handoff
_v3.8 · 2026-07-08 · telegram-research-agent_

---

## Current State

- Memory unification and Roadmap v3 are complete.
- Active strategic pivot: the project should become an AI Knowledge
  Intelligence Desk. The main weekly artifact should be a human-readable HTML
  intelligence report built from Telegram knowledge atoms and temporal idea
  threads. MVP Radar and project recommendations remain downstream consumers,
  not the center of the product. Obsidian is a generated human-facing knowledge
  vault projection, not the runtime source of truth.
- Current development state after the 2026-W28 artifact audit: KIR plumbing and
  the Weekly AI Intelligence Workbook queue KIR-Q0..KIR-Q13 are implemented.
  The next active roadmap is HPI: Hermes / Personal Intelligence Assistant /
  Dogfood. End-to-end KIR context and the Russian final-HTML report requirement
  live in `docs/ai_knowledge_intelligence_roadmap.md`.
- Weekly AI Intelligence Workbook queue KIR-Q0..KIR-Q13 is implemented:
  docs-first planning, Radar KIR provenance/gating, reaction and voice
  feedback, feedback-driven ranking, workbook HTML, deep explanations,
  diagrams, project implementation, MVP Radar section, Strategy Reviewer,
  claim-card hardening, and bounded Obsidian projection.
- HPI-0 is documented, and HPI-1..HPI-8 plus the first Hermes usability slice
  are implemented. Hermes is a Telegram-facing bounded chat/concierge/router,
  not source of truth. Plain text, `/chat`, `/hermes`, and `/ask` route through
  intent classification and a read-only PI tool loop over curated intelligence
  retrieval items, not raw Telegram RAG. Voice input uses OpenAI audio
  transcription when `OPENAI_API_KEY` is configured, then routes as chat,
  feedback, or reminder. Feedback still requires confirmation-gated
  `/feedback_voice` / `/feedback_confirm`. Operator reminders are delivered as
  one daily check-in with `сделал` / `не сделал` buttons. Strategy Reviewer
  remains advisory. Four-week dogfood validates real convenience/usefulness
  before adding complex features.
- HPI-11, HPI-12, HPI-13, HPI-14, and HPI-9-lite are implemented. Telegram plain-text messages no longer
  show MarkdownV2 backslash artifacts when `parse_mode=None`, `/help` starts
  with normal private-assistant guidance, reminders parse/display/run in
  `Asia/Tbilisi`, and feedback drafts use the Opus-class
  `feedback_intake_strategist` path with deterministic fallback while memory
  writes remain confirmation-gated. MVP Radar now receives a bounded
  market/business analyst context pack from curated atoms/threads as context
  only, with raw fallback for channels not yet extracted and gate audits for
  empty or weak weeks. `ai-split-report` now emits separate Knowledge Atlas
  and Weekly Intelligence Brief HTML/JSON artifacts from one curated context
  load. HPI-9-lite adds a curated-only retrieval decision and prototype:
  deterministic ranking plus transient SQLite FTS over filtered curated
  `IntelligenceRetrievalItem` objects. Vector retrieval and raw Telegram RAG
  remain deferred. Do not run a full-year archive pass yet.
- Operational incident on 2026-07-06: `telegram-digest.timer` had been inactive
  since 2026-06-22, so weekly Research Brief/Implementation Ideas stopped
  running while ingest and MVP weekly continued. The timer was manually
  restarted and 2026-W28 artifacts were regenerated. Weekly delivery health
  checks now cover inactive timers, missing current-week reports after the
  scheduled window, and root-owned output files. SQLite usage logging is now a
  best-effort, short-timeout autocommit insert that quietly skips under lock
  contention so report generation is not delayed.
- Recent shipped changes:
  - Telegram reaction sync treats any visible personal source-post reaction as
    `operator_marked_interesting` feedback plus an `interesting` tag; aggregate
    reaction counts are not personal feedback.
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
  - `llm_usage` recording no longer waits behind SQLite write contention:
    usage writes use a 50 ms busy timeout, autocommit, explicit connection
    closing, and quiet lock skips.
  - Knowledge Atom persistence is in place: `knowledge_extraction_batches`
    and `knowledge_atoms` migrations plus `db.knowledge_atoms` helpers for
    batch tracking, stable atom keys, source citations, confidence/novelty/
    utility/relevance scores, and staleness status.
  - `knowledge-extract --weeks N --model cheap` performs bounded batched
    Knowledge Atom extraction from normalized posts with JSON validation,
    idempotent completed-batch skips, failed-batch recording, source URL
    derivation, and `memory inspect-knowledge-atoms`.
  - `idea-threads` refreshes deterministic temporal Idea Threads from
    Knowledge Atoms with 7/30/90 day momentum, source-channel counts,
    active/stale/superseded/hype-only status handling, source-atom relations,
    and `memory inspect-idea-threads` timeline inspection.
  - `ai-intelligence-report` generates a standalone weekly HTML AI
    Intelligence report from compressed Idea Thread / Knowledge Atom context,
    writes a JSON sidecar, includes source map, appendix, read/try actions,
    and blocks internal `Matches:` traces before writing invalid output.
  - `ai-visual-report` generates the stakeholder-facing interactive
    `AI Decision Intelligence` HTML artifact. It writes a JSON sidecar, starts
    with a Decision Brief, puts top actions on the first screen, shows
    conservative Project Implication leads only when evidence is specific enough,
    renders the knowledge-flow diagram through Archify when `ARCHIFY_ROOT` or a
    local skill install is available, falls back to a deterministic diagram when
    it is not, and can send the HTML file to a Telegram chat/channel with
    `--deliver --chat-id ...`.
  - `obsidian-export` projects the same AI Intelligence layer into generated
    Obsidian Markdown notes for weekly intelligence, idea threads,
    tools/models, practices, channels, read queue, try/build, experiments,
    project watch, feedback summary, and Strategy Reviewer with stable slugs,
    frontmatter, generated markers, source references, HTML report section
    links, scoped namespace support, and hand-authored note protection.
  - AI Intelligence feedback is persisted via `ai_report_feedback_events`,
    recorded with `log-ai-report-feedback`, inspected with
    `memory inspect-ai-report-feedback`, and fed back into the next HTML report
    as personalization context, missed-post eval examples, thread/atom
    downranking, and a quality-gated personal learning loop with read/try/
    experiment/skill-gap/reflection slots.
  - MVP Radar, Implementation Ideas, and Project Insights now consume the
    curated knowledge layer: Radar seeds can come from market/workflow
    Knowledge Threads with source atom provenance, MVP weekly reports the
    knowledge-thread seed context, Implementation Ideas gates stale
    engineering/workflow threads before calling the LLM, and Project Insights
    can use project-relevant Knowledge Threads instead of raw keyword-only
    matches.
  - 2026-W24 artifact review showed that internal signal quality improved but
    reader-facing report quality is weak: no first-screen decision brief,
    buried trend summary, visible internal `Matches: ...` traces, contradictions
    between digest/study/project-insights outputs, and Radar gate contradiction.
- The current report-quality, Radar handoff, cost, artifact consistency,
  editorial memory, initial Pathway live-source-intelligence task queue,
  KIR-Q0..KIR-Q13 queue and HPI-1..HPI-8 dogfood foundation are implemented.
  Do not add random features. Start from the HPI queue in `docs/tasks.md`;
  the next step is dogfood measurement, not HPI-9 vector retrieval.
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
- The implemented workbook roadmap is `docs/ai_intelligence_workbook_roadmap.md`,
  with supporting context in `docs/ai_knowledge_intelligence_roadmap.md`.
  Further work should start from HPI in `docs/tasks.md`, not from already
  completed KIR-Q0..KIR-Q13 items.

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

KIR-Q0..KIR-Q13 under `KIR-Q: AI Intelligence Quality / Workbook / Feedback /
Radar Contract` are implemented. HPI is now the active post-KIR roadmap:

```text
HPI: Hermes / Personal Intelligence Assistant / Dogfood
```

HPI-0 documents the roadmap and dogfood plan. HPI-1 through HPI-8 plus the
first usability slice have added the read-only facade, deterministic curated
retrieval projection, bounded PI tool catalog, Hermes Telegram concierge
commands and bounded chat, confirmation-gated feedback, managed voice
transcription with chat/feedback/reminder intent routing, daily operator
reminders with done/not-done callbacks, Strategy Reviewer Telegram delivery,
action status projection, and compact dogfood review artifact helpers.

The exact next task is dogfood measurement over the implemented PI/Hermes
workflow, because HPI-9-lite has already decided and prototyped curated-only
retrieval without vector/raw-post RAG:

```text
Dogfood PI/Hermes Curated Intelligence Workflow
```

Do this next:

- run the weekly split report / Hermes / feedback / action-status loop on real
  operator questions;
- record concrete retrieval misses, wrong priorities, useful answers, actions
  completed, and friction;
- use `docs/curated_semantic_retrieval.md` as the retrieval decision record;
- do not index raw Telegram firehose posts;
- keep all assistant tools read-only.

Do not implement raw Telegram firehose RAG. Do not run the annual/full archive
pass yet. Do not implement assistant mutation tools. Do not let Telegram
commands edit code/config/profile/projects or write feedback directly. Hermes
remains a concierge/router, not source of truth. PI Assistant must use curated
retrieval; vector retrieval requires concrete dogfood misses against the
current curated deterministic+FTS layer.

Open/future items outside completed Q0..Q13 remain:

```text
KIR-Q-008 - Regeneration And Manual Quality Eval
  standard loop verified; forced frontier regeneration needs LLM_API_KEY or ANTHROPIC_API_KEY

KIR-Q-009 - Referee, Thread Audit, Monthly Changed Beliefs
  planned only after 3-4 stable weekly runs
```

Do not start by prompt-tuning the old Research Brief. The strategic direction is:

```text
all Telegram posts -> knowledge atoms -> temporal idea threads ->
Weekly AI Intelligence Workbook HTML -> generated Obsidian projection ->
read / try / build / feedback loop -> Strategy Reviewer -> Codex-ready tasks
```

The completed P0/P1/P2 implementation direction was:

```text
KIR-backed Radar contract first, then reaction/voice feedback, then workbook UI
```

The new HPI implementation direction is:

```text
facade first -> curated retrieval projection -> bounded tools -> Telegram
concierge commands -> confirmation-gated voice feedback -> dogfood metrics
-> four-week product decision before optional vector retrieval
```

Reference documents:

- `docs/tasks.md`
- `docs/hermes_pi_assistant_roadmap.md`
- `docs/dogfood_4_week_plan.md`
- `docs/next_development_roadmap.md`
- `docs/report_quality_roadmap.md`
- `docs/ai_knowledge_intelligence_roadmap.md`
- `docs/ai_intelligence_workbook_roadmap.md`
- `docs/mvp_weekly_radar.md`
- `docs/COGNITION_MANIFEST.md`
- `docs/VPS_COGNITION_VAULT.md`
- `docs/IMPLEMENTATION_CONTRACT.md`
- `docs/architecture.md`

Radar cross-repo path for RADAR tasks:

```text
/srv/openclaw-you/workspace/Demand-to-MVP-Radar
```
