# Current Backlog

**Status:** Active lightweight backlog
**Last updated:** 2026-07-07

The historical memory-unification roadmap is complete and archived at
`docs/archive/roadmaps/tasks-v5-memory-unification.md`.

Detailed next-roadmap context lives in
`docs/next_development_roadmap.md`.

Reader-facing report quality and Demand-to-MVP Radar handoff details live in
`docs/report_quality_roadmap.md`. The active KIR quality/user-value roadmap
from the 2026-W28 artifact audit, including the Russian final-HTML report
requirement, lives in
`docs/ai_knowledge_intelligence_roadmap.md`.

Pathway live source intelligence and Radar incremental-indexing work lives in
`docs/pathway_live_source_intelligence.md`.

AI Knowledge Intelligence Desk strategy, architecture, phases, and implementation
details live in `docs/ai_knowledge_intelligence_roadmap.md`.

## Current State

Implemented:

- Telegram ingestion and normalized post storage
- deterministic scoring and project relevance
- reaction-based feedback sync for original Telegram posts
- inline Telegram feedback cards for implementation ideas
- compact Implementation Ideas feedback cards capped for Telegram scanning
- integration-style bot polling callback dispatch test around `bot.run_bot`
- weekly Research Brief, Implementation Ideas, and Study Plan
- README and active docs aligned with current delivery/feedback behavior
- evidence memory via `signal_evidence_items`
- Implementation Ideas evidence guard: parsed `[Implement]` / `[Build]` ideas without concrete source post URLs render an insufficient-evidence note instead of actionable recommendations
- decision continuity via `decision_journal`
- operator-authored weekly usefulness logs via `weekly_usefulness_logs`
- project context snapshots
- low-signal / empty digest health alerts
- weekly quality trend from Research Brief receipt health alerts in `score-stats`
- monthly `projects.yaml` review guardrail in `health-check`
- memory inspection CLI
- Telegram Channel Intelligence design, schema migrations, deterministic repeated-claim extraction, canonical source-observation refresh, active-project intelligence links, narrative candidate refresh, inspection CLI, and optional Markdown report surface captured in `docs/telegram_channel_intelligence.md`
- Research Brief receipt SQLite schema, storage helpers, generation-time creation, delivery ref updates, deterministic verification checks, CLI inspection, operator review, and optional operator-only audit notes via `research_brief_receipts`
- Core-compatible Research Brief receipt adapter, weekly audit-note hash wiring,
  `memory inspect-core-receipt` for delivered briefs, and deterministic Core
  evidence lookup checks via `--verify-evidence`
- Core receipt schema compatibility tests and product-local boundary guards
- artifact-level operator feedback via `log-artifact-feedback` and
  `memory inspect-artifact-feedback`
- monthly operator report via `operator-report`
- source down-rank explanations via `memory explain-source-downrank`
- product split gate via `product-split-gate`
- production validation surfaces for reaction sync and inline callbacks via
  `ops-validate`
- deterministic report-quality gates for weekly artifacts via
  `output.report_quality`, digest delivery warnings, Study Plan/Project
  Insights logging, and `operator-report`
- reader-facing Research Brief Decision Brief and Actions header, with early
  What Changed summary and compact Telegram notification funnel/action count
- artifact-level Telegram feedback buttons for Research Brief,
  Implementation Ideas, MVP weekly, and Study Plan delivery notifications,
  recorded in `artifact_feedback_logs`
- reader-facing Research Brief evidence/source-mix summary derived from local
  receipt evidence lookup, source links, fallback state, and top channels
- Demand-to-MVP Radar final gate contradiction guard: runtime LLM Markdown
  cannot override deterministic source-mix gates, and Radar Markdown/JSON agree
- Demand-to-MVP Radar Candidate Dossier output: canonical
  `build/focused_experiment/investigate/reject` status, decision, confidence,
  next action, missing evidence, next experiment, kill criteria, and Telegram
  notification status display
- Demand-to-MVP Radar source-mix truth surface: selected-candidate source mix
  in Markdown/JSON, missing credentials, Reddit API vs SERP-indexed Reddit, and
  GitHub primary/repeated-variant labeling surfaced to Telegram notification
- Demand-to-MVP Radar report-quality tests: Candidate Dossier top block,
  required sections, source-mix card, missing evidence, kill criteria,
  existing-project context, and no contradictory build-ready claims
- internal LLM cost guardrail sentinel via deterministic `llm_usage` summaries:
  budget/spike warnings in `cost-stats` and monthly `operator-report`
- weekly artifact consistency contract: Study Plan/Project Insights checks
  against Research Brief facts, MVP delivery build-readiness guard, and
  operator-report consistency warnings
- weekly editorial memory via `memory inspect-editorial-memory`: local
  operator/system-authored keep/change/demote/test-next-week notes from
  artifact feedback, usefulness logs, report-quality findings, receipt health,
  and source down-rank explanations
- Pathway-ready live source intelligence: append-only source events from
  Telegram ingestion, deterministic live-source snapshots, Radar context-only
  consumption, and optional `mvp-weekly --with-live-source-index` bridge
- weekly delivery health checks in `health-check`: inactive
  `telegram-digest.timer`, missing current-week digest after the scheduled
  Monday window, root-owned `data/output` files, and deployed
  `scripts/healthcheck.sh` wiring through the Python health surface
- non-blocking best-effort `llm_usage` recording: short SQLite busy timeout,
  autocommit insert, closed usage connection, and quiet skip under database
  lock contention so report generation is not delayed by cost logging
- Knowledge Atom schema and storage helpers: `knowledge_extraction_batches`
  and `knowledge_atoms` migrations with source citation JSON, atom type,
  confidence/novelty/utility/relevance scores, staleness status, stable keys,
  and focused round-trip tests
- cheap batched Knowledge Atom extraction CLI via `knowledge-extract`: bounded
  post batches, cheap-model routing, JSON-only validation, idempotent completed
  batch skips, failed-batch recording, source URL derivation, and
  `memory inspect-knowledge-atoms`
- Idea Thread grouping and momentum layer: `idea_threads` and
  `idea_thread_atoms` migrations, deterministic Knowledge Atom grouping,
  7/30/90 day momentum scores, active/stale/superseded/hype-only status
  handling, source-channel visibility, and `memory inspect-idea-threads`
  timeline inspection
- standalone weekly AI Intelligence HTML report via
  `ai-intelligence-report`: deterministic report assembly from compressed Idea
  Thread and Knowledge Atom context, required Executive Brief / What Changed /
  Idea Evolution / Tools-Models-Practices / Contradictions / Read Queue / Try
  This Week / Source Map / Appendix sections, JSON sidecar, local notification
  text, and quality gates that block internal matching traces
- Archify-backed weekly visual artifact via `ai-visual-report`: generates a
  one-off interactive `AI Decision Intelligence` HTML report with a first-screen
  Decision Brief, top actions, week delta metrics, conservative Project
  Implication leads, trend board, embedded Archify data-flow visualization,
  frontier-model study/action sections, JSON sidecar, quality gates, and
  optional Telegram document delivery through `--deliver`. Broad keyword-only
  project overlaps are suppressed, so zero project leads is an honest outcome
  when the evidence is not specific enough.
- generated Obsidian knowledge vault projection via `obsidian-export`:
  deterministic Markdown notes for weekly intelligence, idea threads,
  tools/models, practices, channels, read queue, and experiments; frontmatter,
  generated-file markers, source references, HTML report section links,
  namespace support, idempotent regeneration, and hand-authored note overwrite
  protection
- AI Intelligence report feedback and personal learning loop:
  `ai_report_feedback_events` persistence, `log-ai-report-feedback`,
  `memory inspect-ai-report-feedback`, prior-feedback personalization context
  in the next HTML report, missed-post eval example extraction, feedback-aware
  downranking for thread/atom recommendations, and a quality-gated weekly loop
  with five read targets, two try targets, one experiment, one skill gap, and
  one reflection question
- frontier-model analysis layer via `frontier-analysis`: top-model synthesis
  over compressed Idea Threads and Knowledge Atoms, persisted in
  `frontier_analyses`, rendered as the reader-facing Frontier Analysis section
  in HTML reports, and projected into generated Obsidian weekly notes
- downstream MVP Radar and project consumers now read the curated knowledge
  layer: opportunity seed export emits Knowledge Thread-backed Radar seeds with
  source atom provenance, MVP weekly surfaces knowledge-thread counts,
  Implementation Ideas blocks on stale Knowledge Thread context and prompts
  from engineering/workflow threads, and Project Insights can render
  project-relevant Knowledge Thread notes without raw keyword-only matches
- Telegram digest timer was restored on 2026-07-06 after being inactive since
  2026-06-22; 2026-W28 Research Brief and Implementation Ideas were regenerated
  manually. This exposed the next product direction: convert the project from a
  project/MVP-centered weekly digest into an AI Knowledge Intelligence Desk.

## Active Maintenance Queue

The previous receipt/source-trust/operator-reporting backlog, reader-facing
report quality, Radar handoff, cost guardrails, artifact consistency,
editorial memory, initial Pathway-ready live source intelligence, and initial
KIR plumbing are implemented.

The active queue is not closed after KIR-050. KIR plumbing is done, but the
quality/eval/user-value roadmap is open: the next stage must turn the working
knowledge-intelligence pipeline into a reliable weekly intelligence desk that
shows verified claims, temporal deltas, personalization, operational actions,
and outcome feedback instead of only attractive atoms/threads/HTML.

Implementation details, end-to-end stages, acceptance criteria, metrics, risks
and non-goals for this queue are in
`docs/ai_knowledge_intelligence_roadmap.md`. Historical report-quality and
Radar paths remain in `docs/report_quality_roadmap.md`.

## KIR-Q: AI Intelligence Quality / Workbook / Feedback / Radar Contract

Status: active planning and implementation queue.

The earlier KIR-Q-001..KIR-Q-009 quality-audit tasks below record the W28
report-contract implementation history. The active product queue now moves from
weekly report plumbing to a Weekly AI Intelligence Workbook, feedback intake,
and a stronger KIR-backed Radar contract. Roadmap details live in
`docs/ai_intelligence_workbook_roadmap.md`.

### KIR-Q0 - Document AI Intelligence Workbook Roadmap

Status: in_progress for this planning session.

Goal: convert the product pivot into explicit docs, task IDs, implementation
order, and acceptance criteria before code work starts.

Files likely:

- `docs/ai_intelligence_workbook_roadmap.md`
- `docs/tasks.md`
- `docs/operator_workflow.md`
- `docs/mvp_weekly_radar.md`
- `docs/ai_knowledge_intelligence_roadmap.md`
- `docs/CODEX_PROMPT.md`
- optional `docs/README.md`

Acceptance:

- roadmap exists;
- tasks KIR-Q0..KIR-Q13 are listed;
- operator workflow includes the weekly workbook routine;
- KIR-backed Radar contract is documented;
- risks/open questions, stop conditions, and four-week success criteria are
  documented;
- next P0 implementation task is identified.

Verification:

```bash
git diff --stat
rg "KIR-Q0|KIR-Q1|KIR-Q13|Weekly AI Intelligence Workbook|KIR-backed Radar Contract" docs
```

### KIR-Q1 - Preserve KIR Provenance In Radar Import

Status: planned P0.

Goal: Demand-to-MVP Radar must preserve Knowledge Thread provenance emitted by
Telegram Research Agent opportunity seeds.

Files likely:

- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/sources/telegram_research_agent.py`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/tests/test_mvp_of_week.py`
- maybe `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/tests/test_mvp_report_quality.py`

Acceptance:

- imported `EvidenceRecord.provider_metadata` preserves `source_kind`,
  `source_urls`, `knowledge_thread_slug`, `knowledge_thread_title`,
  `knowledge_thread_status`, `knowledge_atom_types`, and `source_atom_ids`;
- tests cover a `knowledge_thread` seed export;
- selected JSON/report can expose KIR metadata or make it available to source
  mix code;
- existing non-KIR Telegram seed imports still pass.

Verification:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py tests/test_mvp_report_quality.py
```

### KIR-Q2 - Add KIR-Backed Radar Gate

Status: planned P0.

Goal: in Telegram-seeded weekly mode, `build` or `focused_experiment` must
require fresh KIR Knowledge Thread evidence with source atoms plus
decision-grade external evidence.

Files likely:

- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/mvp_weekly.py`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/tests/test_mvp_of_week.py`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/tests/test_mvp_report_quality.py`

Acceptance:

- imported seed metadata derives `kir_source_kind`, `kir_thread_slug`,
  `kir_thread_status`, `kir_source_atom_count`, `kir_has_fresh_thread`, and
  `kir_gate_status`;
- Telegram-seeded `focused_experiment`/`build` requires fresh KIR thread,
  source atoms, source URLs, decision-grade external evidence, operator fit,
  and no blocking risk/profile mismatch;
- external-first standalone Radar mode is not broken;
- Markdown explains KIR evidence present/missing;
- JSON exposes KIR gate state.

Verification:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py tests/test_mvp_report_quality.py
```

### KIR-Q3 - Simplify Reaction Feedback

Status: planned P0.

Goal: any visible operator reaction on a Telegram source post means the post
caught the operator's interest. The operator should not need to remember emoji
semantics.

Files likely:

- `src/ingestion/reaction_sync.py`
- `src/db/migrate.py`
- feedback/tag helpers around `signal_feedback` and `user_post_tags`
- `src/output/ai_intelligence_report.py`
- `src/output/ai_visual_report.py`
- `tests/test_reaction_sync.py`

Acceptance:

- first validate whether Telethon can see the operator's own reactions across
  selected channels;
- if only aggregate reactions are visible, do not treat them as personal
  feedback;
- any visible personal reaction records `operator_marked_interesting` or
  equivalent positive implicit feedback;
- raw emoji is stored for audit;
- no reaction means unknown, not negative;
- report can show "Posts you marked this week."

Validation:

```bash
python3 src/main.py sync-reactions --days 14 --limit 300
python3 src/main.py ops-validate reaction-sync --days 14
```

Test command:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_reaction_sync
```

### KIR-Q4 - Voice Feedback Intake

Status: planned P0.

Goal: let the operator send voice/text feedback after reading the workbook,
parse it into structured proposals, ask for confirmation, and write only
confirmed feedback to memory.

Files likely:

- bot handlers for voice/text messages;
- DB migration for raw voice feedback, transcripts, parse proposals, and
  confirmation status if existing tables are insufficient;
- new feedback parser module;
- `src/db/ai_report_feedback.py`;
- `tests/test_ai_report_feedback.py`;
- bot handler tests.

Acceptance:

- voice/text feedback can be transcribed or accepted as text;
- parser extracts useful, not-interested, wrong-priority, too-shallow, tried,
  applied-to-project, missed-post, project-correction, source-trust, preference,
  config, and Codex-task suggestions;
- bot returns a human-readable confirmation summary;
- no confirmed feedback means no memory writes;
- confirmed feedback writes `ai_report_feedback_events` and optional artifact
  feedback/editorial memory entries;
- parser suggestions never edit code/config/prompts automatically.

### KIR-Q5 - Feedback Affects Next Workbook

Status: planned P1.

Goal: confirmed feedback should visibly affect the next workbook's ranking,
wording, and "what changed because of feedback" section.

Files likely:

- `src/db/ai_report_feedback.py`
- `src/output/frontier_analysis.py`
- `src/output/ai_intelligence_report.py`
- `src/output/ai_visual_report.py`
- workbook renderer tests.

Acceptance:

- wrong-priority/not-interested downranks related threads/actions;
- useful/tried/applied raises priority for related targets;
- missed important posts become eval examples;
- next report includes "what feedback changed this week";
- no-feedback weeks state low personalization confidence.

### KIR-Q6 - Weekly Intelligence Workbook HTML

Status: planned P1.

Goal: create the primary rich Weekly AI Intelligence Workbook HTML artifact.

Files likely:

- `src/output/ai_visual_report.py` or new `src/output/ai_workbook_report.py`
- `src/main.py`
- JSON sidecar contract/tests
- `tests/test_ai_visual_report.py` or new workbook tests.

Acceptance:

- workbook has Decision Brief, Strong Signals, Deep Explain, Project
  Implementation, MVP Radar, Read/Try/Build, Feedback, and Appendix sections;
- first screen is concise;
- deep sections use progressive disclosure;
- HTML is standalone;
- JSON sidecar includes structured workbook sections;
- output does not become an 80-page wall of text;
- diagrams and explanations are labeled as explanatory and do not upgrade
  evidence strength.

### KIR-Q7 - Deep Explanation Cards

Status: planned P1.

Goal: strongest signals should explain complex AI/engineering topics in plain
language without uncited strong claims.

Files likely:

- `src/output/frontier_analysis.py`
- workbook schema/renderer
- `tests/test_ai_visual_report.py` or workbook tests.

Acceptance:

- top 3-5 signals have simple explanations;
- cards include "what is this", "why now", "how it works", "where is hype",
  "what to do", and "what not to do";
- caveats and source links are visible;
- no uncited strong claims;
- every strong claim includes evidence tier, quote verification status, caveat,
  and "what would change my mind."

### KIR-Q8 - Concept Diagrams With Archify/Local Renderer

Status: planned P1.

Goal: add deterministic concept/dataflow diagrams for selected workbook topics
when they improve understanding.

Files likely:

- `src/output/ai_visual_report.py` or diagram helper;
- Archify/local IR generator;
- docs and renderer tests.

Acceptance:

- at least one concept diagram appears in a suitable selected report;
- diagram IR is deterministic and locally generated;
- diagrams are explanatory, not evidence;
- no external image scraping in P0/P1.

### KIR-Q9 - Project Implementation Section

Status: planned P1.

Goal: translate strong signals into concrete existing-project PR/backlog
candidates without broad keyword matching.

Files likely:

- project implication logic;
- `src/config/projects.yaml` interpretation;
- workbook renderer;
- tests around conservative project matching.

Acceptance:

- concrete repo/backlog/PR suggestions include effort, acceptance criteria,
  risk/caveat, and source atom links;
- zero project leads still produces useful diagnostics;
- broad terms like `AI`, `workflow`, `evidence`, and `tool` do not create
  fake project leads.

### KIR-Q10 - MVP Radar Workbook Section

Status: planned P1.

Goal: embed the weekly Radar candidate dossier into the workbook as a
conservative opportunity section.

Files likely:

- `src/output/mvp_weekly_pipeline.py`
- workbook renderer;
- Demand-to-MVP Radar JSON contract if needed.

Acceptance:

- workbook includes selected MVP candidate, status, source mix, missing
  evidence, next validation, and kill criteria;
- weak candidates clearly say "do not build";
- KIR evidence and external evidence are separated;
- live source intelligence remains context-only.

### KIR-Q11 - Strategy Reviewer Agent

Status: planned P2.

Goal: after feedback, produce advisory system-improvement suggestions and
Codex-ready tasks without modifying code/config.

Files likely:

- new `src/output/strategy_reviewer.py`
- bot delivery or CLI command;
- editorial memory / feedback integration;
- tests.

Acceptance:

- reviewer outputs keep/change/demote/test-next-week suggestions;
- separates memory-only updates from config/code changes requiring approval;
- creates Codex-ready task suggestions with files, acceptance criteria, and
  verification commands;
- does not modify source code, prompts, thresholds, profile, or projects.

### KIR-Q12 - Quote Verification / Evidence Tiers / Claim Cards

Status: planned P2.

Goal: harden claim discipline across atom extraction and workbook rendering.

Files likely:

- `src/output/knowledge_extraction.py`
- knowledge atom schema/migration if stored fields are needed;
- report/workbook renderers;
- tests around quote verification and wording guardrails.

Acceptance:

- quote verification status is stored or derived;
- evidence tier is shown for top claims;
- top claims include claim cards with atom IDs, source URLs, verification,
  source count, caveat, expiry/staleness, and next verification step;
- weak claims use cautious wording.

### KIR-Q13 - Obsidian Workbook Projection

Status: planned P2.

Goal: refine generated Obsidian projection for workbook/read/try/build and
Strategy Reviewer outputs without note explosion.

Files likely:

- `src/output/obsidian_export.py`
- `tests/test_obsidian_export.py`

Acceptance:

- weekly workbook note links to read/try/build/experiment/project watch;
- strategy reviewer note and feedback summary note can be exported;
- no one-note-per-post output;
- no channel/tool/model note explosion;
- generated notes remain disposable and protected from overwriting
  hand-authored notes.

### KIR-Q-001 - Weekly Report Quality Contract

Status: implemented.

Goal: define a testable weekly AI Intelligence report quality contract. The
operator-facing final HTML report must be in Russian and must explicitly answer
what changed, which 3-5 claims matter, which claims are weak/speculative, what
to read, what to try, what to ignore, how this relates to projects/profile, and
which feedback the operator should leave.

Required work:

- add a report contract to docs and code-facing schemas;
- define JSON fields for `decision_cards`, `claim_cards`, `thread_deltas`,
  and `feedback_targets`;
- add deterministic quality checks for required user-value sections;
- use the 2026-W28 versioned artifact as the first fixture.

Acceptance:

- `docs/tasks.md` no longer says KIR has no open work;
- report-quality tests can fail a report that has structure but no useful
  operator verdict, claim evidence, temporal delta, actions, or feedback
  targets;
- generated final HTML uses Russian user-facing copy while internal JSON keys,
  code identifiers, and CLI names may remain English;
- W28 artifact can be evaluated as a fixture without live DB/VPS pipeline.

Implementation notes:

- `src/output/ai_report_contract.py` defines
  `weekly-ai-intelligence-v1`, including `decision_cards`, `claim_cards`,
  `thread_deltas`, `action_cards`, `project_diagnostic`,
  `feedback_targets`, and Russian HTML language metadata.
- `ai-visual-report` now builds that contract, renders the final
  operator-facing weekly HTML report in Russian, and fails quality gates before
  writing output when user-value sections or contract fields are missing.
- `tests/test_ai_report_contract.py` evaluates the committed W28 snapshot under
  `docs/artifacts/ai-decision-intelligence-2026-W28/` offline as the first
  regression fixture; the old W28 artifact intentionally fails the new
  contract until regenerated.

### KIR-Q-002 - Claim Evidence Cards And Quote Verification

Status: implemented.

Goal: prevent high-impact Telegram-derived claims from being presented as
established intelligence without source strength, verified evidence, caveat,
and next verification action.

Required work:

- extend atom/report metadata with evidence tier, evidence role,
  verification status, `quote_verified`, claim scope, time horizon, expiry hint,
  and source independence key;
- add deterministic quote verification against source post text;
- render top claims as evidence cards in HTML;
- add single-source wording rules for strong trend language.

Acceptance:

- a claim without source URL or verified quote cannot appear in Decision Brief
  unless it is explicitly labeled weak/single-source;
- top W28 claims such as GigaChat/J-space/Fable/Nvidia/Stanford-style claims
  show source count, evidence tier, caveat, and verification action;
- report quality gates catch missing atom IDs, missing URLs, and unverifiable
  evidence quotes for top claims.

Implementation notes:

- `ai-visual-report` now enriches Knowledge Atom context with local source-post
  text, verifies evidence quotes deterministically against `posts.content`, and
  writes evidence role, source independence key(s), verification status,
  `quote_verified`, claim scope, time horizon, expiry hint, caveat, and next
  verification action into each `claim_cards` item.
- claim-card quality gates now fail missing atom IDs, missing source URLs, and
  unverifiable top claims unless they are explicitly weak/single-source and
  decision-ineligible; `apply`/`study` decision cards cannot rely on
  unverifiable claims.
- generated Russian HTML evidence cards surface source count, evidence tier,
  evidence role, quote verification status, caveat, expiry, verification
  action, and source links.

### KIR-Q-003 - Temporal Thread Delta Layer

Status: implemented.

Goal: make `What Changed` a real temporal-intelligence section instead of a
list of updated threads or momentum bars.

Required work:

- add per-thread previous state, this-week evidence, delta reason,
  confidence movement, and new evidence atom IDs;
- render previous -> new evidence -> updated interpretation in HTML;
- make insufficient history explicit rather than pretending a trend exists;
- add merge/split audit hooks for suspicious thread continuity.

Acceptance:

- at least five top threads show a clear delta or an explicit
  `insufficient_history` state;
- `What Changed` no longer equals a count of changed threads;
- thread timeline explains why grouped atoms belong to the same idea.

Implementation notes:

- `thread_deltas` now split each top Idea Thread into previous atoms and
  this-week evidence, then render previous state -> current evidence ->
  updated interpretation in the Russian HTML report.
- each delta includes `previous_week_state`, `this_week_evidence`,
  `confidence_change`, `delta_reason`, `new_evidence_atom_ids`, `state`,
  `why_this_is_one_thread`, and `merge_split_audit_status`.
- quality gates require enough deltas for the available thread count, require
  this-week evidence details, and allow empty new-evidence IDs only when the
  delta is explicitly marked `insufficient_history`.

### KIR-Q-004 - Project Fit Diagnostic

Status: implemented.

Goal: keep conservative project matching while making a zero-project-lead week
useful to the operator.

Required work:

- preserve broad-term suppression for terms such as `AI`, `workflow`,
  `evidence`, and `tool`;
- add tiers: confirmed project lead, project watch, and learning-only
  implication;
- render empty-state diagnostics: checked projects, rejected overlaps,
  close-but-not-enough signals, and missing evidence/config needed for a lead.

Acceptance:

- a week with 0 confirmed project leads still explains what was checked and why
  no lead passed;
- broad keyword overlaps do not create a fake project-fit matrix;
- learning-only implications remain visible without being framed as project
  decisions.

Implementation notes:

- project diagnostic now has explicit `confirmed_leads`, `project_watch`,
  `learning_only_implications`, `close_but_not_enough_signals`,
  `rejected_broad_overlaps`, `missing_evidence`, and
  `missing_config_suggestions`.
- broad terms such as `AI`, `workflow`, `evidence`, and `tool` remain
  suppressed as project decisions; they are surfaced only as rejected
  close-but-not-enough diagnostics with required evidence/config additions.
- Russian HTML renders confirmed leads, project watch, broad-overlap rejects,
  learning-only implications, missing evidence, and config suggestions so a
  zero-confirmed-lead week remains useful.

### KIR-Q-005 - Operational Action Cards

Status: implemented.

Goal: turn `Do Now` / `Study Next` into actions that can be tried, killed, or
fed back into the next report.

Required work:

- render effort, scope, success criterion, kill condition, feedback target, and
  follow-up hint for every action card;
- carry `success_criterion` from frontier JSON into HTML;
- store stable target references for action/read/experiment feedback.

Acceptance:

- every action answers what to do, how to know it worked, when to stop, and how
  to leave feedback;
- at least two try items and one experiment target exist for each weekly run;
- action outcome is not counted useful until feedback says read/tried/applied.

Implementation notes:

- `action_cards` now include stable `target_ref`, `action_kind`, effort, scope,
  next step, success criterion, kill condition, follow-up hint,
  feedback-event options, outcome policy, and `feedback_target_id`.
- the weekly contract guarantees at least two `try` action cards and one
  `experiment` action card, deriving fallback actions from study items when
  frontier output is sparse.
- quality gates fail action cards that lack the minimum mix or feedback policy;
  Russian HTML renders follow-up and outcome policy so useful outcomes are not
  implied until operator feedback records them.

### KIR-Q-006 - Obsidian Projection Pruning

Status: implemented.

Goal: keep Obsidian as a generated cockpit, not a noisy database mirror.

Required work:

- limit autogenerated term/channel notes to active, repeated, promoted, or
  decision-relevant items;
- add experiment note templates with hypothesis, method, result, decision, and
  optional project link;
- connect weekly notes to top idea threads, read queue, try items, experiments,
  and project watches only when thresholds pass.

Acceptance:

- no one-note-per-post dump and no weekly channel/term note explosion;
- generated notes keep frontmatter, backlinks, source refs, and generated-file
  markers;
- mature insights are promotable manually into hand-authored cognition vault
  areas.

Implementation notes:

- `obsidian-export` now builds a bounded projection context from the weekly
  contract, using report action cards and project diagnostics before writing
  vault notes.
- idea thread, term, channel, read queue, and experiment notes are thresholded:
  low-signal one-off terms/channels do not create notes, read queue notes are
  capped, and experiment notes come from the contract's experiment action.
- experiment notes include hypothesis, method, result, decision, project-link,
  and manual-promotion sections while preserving frontmatter, backlinks, source
  refs, and generated-file markers.

### KIR-Q-007 - Minimum Weekly Feedback And Eval Loop

Status: implemented.

Goal: make personalization measurable instead of theoretical.

Required work:

- add weekly feedback completion indicator;
- support minimum feedback targets: two read items, one action, one missed-post
  or explicit no-missed marker, and one trust correction when relevant;
- convert missed important posts and wrong-priority feedback into eval examples;
- feed recent wrong-priority/not-interested/useful/tried signals into next
  frontier prompt.

Acceptance:

- next report can state which prior feedback was used and how similar items
  were downranked or promoted;
- at least 3-5 feedback events can be recorded against one weekly report;
- no-feedback weeks show low personalization confidence.

Implementation notes:

- `ai_report_feedback_events` now accepts `no_missed_posts`,
  trust-correction events, missed-post targets, and trust-correction targets.
- feedback summaries include minimum completion state, promoted/downranked
  target refs, missed-post examples, priority-calibration eval examples, and
  frontier prompt guidance.
- the weekly contract now requests two read feedback targets, action feedback,
  missed/no-missed feedback, and trust correction; the visual report states
  prior-feedback usage and low personalization confidence when no feedback is
  available.
- `frontier-analysis` prompt context explicitly uses wrong-priority,
  not-interested, useful, tried, missed-post, and priority-calibration signals.

### KIR-Q-008 - Regeneration And Manual Quality Eval

Status: open; standard loop verified, forced frontier regeneration blocked by
missing `LLM_API_KEY`/`ANTHROPIC_API_KEY`.

Goal: prove the new quality contract on the W28 artifact and the standard
weekly run path.

Required work:

- run the standard loop for W28 after KIR-Q-001..KIR-Q-007 land:
  `knowledge-extract`, `idea-threads`, `frontier-analysis`,
  `ai-visual-report`, and `obsidian-export`;
- run structural and new user-value gates;
- record at least three manual feedback events for the generated artifact;
- compare W28 before/after for first-screen clarity, evidence quality,
  action usefulness, and project diagnostic value.

Acceptance:

- HTML passes structural gates and new claim/action/evidence gates;
- the W28 diff visibly improves operator clarity without adding visual polish
  as a substitute for evidence/action quality;
- regenerated W28 final HTML is Russian for user-facing sections, actions,
  caveats, labels, and empty states;
- regenerated Obsidian output remains scoped and disposable.

Verification notes:

- 2026-07-07 standard W28 loop completed through `knowledge-extract`,
  `idea-threads`, skipped-existing `frontier-analysis`, `ai-visual-report`, and
  `obsidian-export`.
- fresh W28 visual HTML/JSON passed the weekly report contract with zero
  findings; Obsidian export stayed bounded at 44 generated notes.
- five feedback events were recorded against the W28 visual artifact and the
  minimum feedback completion indicator reports 4/4.
- forced frontier regeneration failed locally because no LLM API key is set, so
  some reused frontier-derived action titles and next steps remain English.
- manual eval notes are stored in
  `docs/artifacts/ai-decision-intelligence-2026-W28/manual-quality-eval-2026-07-07.md`.

### KIR-Q-009 - Referee, Thread Audit, Monthly Changed Beliefs

Status: planned after 3-4 stable weekly runs.

Goal: add higher-cost checks only where the weekly loop has shown repeated
value.

Required work:

- add referee pass only for 3-5 high-impact Decision Brief claims;
- add thread merge/split audit CLI and labels such as hype-only,
  production-pattern, contested, validated, stale, superseded;
- generate a monthly changed-beliefs report covering accepted, rejected,
  uncertain, tried, applied, and ignored claims;
- evaluate scoped retrieval/embeddings over evidence items only, not all raw
  posts.

Acceptance:

- high-impact claims receive a second-pass check without running expensive
  review over every atom;
- monthly report can show what actually changed in operator beliefs/actions;
- embeddings are introduced only if scoped evidence retrieval is insufficient.

Production validation remains inspectable with `ops-validate`. If no live
Telegram reaction or callback event has occurred in the selected window, the
command reports `needs_live_event` rather than storing unverified success.

## Parking Lot

- Public/product UI after `PROD-1` passes.
- Referee pass for high-impact claims after KIR-Q-001..KIR-Q-008 produce stable
  weekly runs.
- Productized Telegram Channel Intelligence repo or workspace after repeated
  operator value is demonstrated.
- Pathway as an incremental indexing backend after the deterministic
  knowledge-atom and idea-thread contracts are proven locally.
