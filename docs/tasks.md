# Current Backlog

**Status:** Active lightweight backlog
**Last updated:** 2026-07-08

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
- VPS dogfood baseline was configured on 2026-07-08: Hermes bot polling,
  weekly ingest/digest/MVP/cleanup/study timers, explicit runtime paths in the
  environment, output ownership, healthcheck, manual scoring recovery after a
  one-time persistent-timer DB lock, and production `ops-validate` evidence
  checks are documented for dogfood readiness.
- Telegram voice input now has a managed transcription path: voice `.ogg`
  files are downloaded to temporary storage, transcribed through the OpenAI
  audio endpoint when `OPENAI_API_KEY` is configured, routed through the Hermes
  intent classifier as chat/feedback/reminder, and deleted locally after
  processing. Feedback still uses the existing `/feedback_voice` confirmation
  draft when the transcript is classified as feedback. Missing transcription
  config returns a text fallback instead of pretending voice input worked.
- Hermes bounded LLM chat is available through plain Telegram text plus
  `/chat`, `/hermes`, and `/ask`; the model can plan calls only to the
  read-only PI tool catalog and cannot run Codex, mutate config/code/profile,
  or query raw Telegram firehose RAG by default.
- Operator reminders are stored locally and delivered as a once-daily Telegram
  check-in with `сделал` / `не сделал` inline buttons; they do not run every 30
  minutes and do not mutate workbook/report scoring.

## Active Maintenance Queue

The previous receipt/source-trust/operator-reporting backlog, reader-facing
report quality, Radar handoff, cost guardrails, artifact consistency,
editorial memory, initial Pathway-ready live source intelligence, and initial
KIR plumbing are implemented.

HPI: Hermes / Personal Intelligence Assistant / Dogfood has shipped the first
usable assistant loop, split Knowledge Atlas / Weekly Intelligence Brief
artifacts, and a context-only market/business lens for MVP Radar. KIR plumbing
and KIR-Q0..KIR-Q13 are implemented.

The active next engineering queue is RVE: Radar Validation Evidence Layer. The
goal is not to generate prettier ideas or ingest a raw external firehose. The
goal is to let Radar test Telegram/market hypotheses against candidate-specific
external demand evidence: search demand, public complaints, manual workaround
examples, competitor traction, and willingness-to-pay signals.

Implementation details, end-to-end stages, acceptance criteria, metrics, risks,
and non-goals for the completed KIR queue remain in
`docs/ai_knowledge_intelligence_roadmap.md` and
`docs/ai_intelligence_workbook_roadmap.md`. Historical report-quality and Radar
paths remain in `docs/report_quality_roadmap.md`.

## RVE: Radar Validation Evidence Layer

Status: active next implementation queue after the first 2026-W28 split-HTML
dogfood run.

Context:

- The 2026-W28 run produced both HTML artifacts:
  - `data/output/knowledge_atlas/2026-W28.knowledge-atlas.html`;
  - `data/output/weekly_intelligence_briefs/2026-W28.weekly-brief.html`.
- Demand-to-MVP Radar selected `Hotkey Dictation Workflow Probe` with
  `dossier_status=investigate`, `recommendation=revisit_with_evidence_gap`,
  and score 60.
- Radar correctly kept the market/business context lens as `context_only`, so
  it did not become a candidate and did not satisfy build gates by itself.
- The remaining evidence gap is structural: Radar can see Telegram signal, but
  often lacks matched external validation for the selected candidate. Typical
  missing evidence: fresh KIR thread, two independent non-Telegram sources,
  WTP signal, repeatable search queries, and concrete manual workaround
  examples.

Goal:

Make Radar produce and consume candidate-specific validation evidence before
it recommends build/focused-experiment. The market/business lens should tell
Radar what to look for and why; external adapters should validate or reject
that candidate with public demand evidence.

Architecture rules:

- This is a validation-evidence layer, not an idea-generation layer.
- Market/business context remains context-only unless a record is explicitly
  matched to the selected candidate and source-gated as external evidence.
- External results must be classified and tied to a candidate before they can
  affect `source_gate_satisfied`, `dossier_status`, or final recommendation.
- Unmatched external results can appear as research context, but cannot satisfy
  build gates.
- Missing credentials or disabled adapters must degrade to
  `credential_limited` / `adapter_disabled`, not fail the weekly run.
- Cache-first and dry-run behavior is required for every live external
  adapter.
- Do not weaken existing gates to make candidates look better.

Candidate external resources to wire in as adapters:

Source repository for these skills:

- `https://github.com/artwist-polyakov/polyakov-claude-skills`
- Marketplace hint from that repository: `/plugin marketplace add artwist-polyakov/polyakov-claude-skills`.
- Do not assume these skills are installed in the current runtime. The next
  implementation session should inspect/install/fetch only the needed skill
  docs or plugin code, then wrap them behind the RVE adapter boundary.

- `yandex-wordstat`: search demand and monthly demand dynamics.
- `yandex-search-api`: Yandex Cloud Search API v2 SERP evidence.
- `reddit-skill`: Reddit API search over posts/comments/subreddits with
  cache-first and dry-run safeguards.
- `x-research`: X/Twitter discussion research through xAI/Grok where
  credentials exist.
- `crawl4ai-seo`: competitor/landing-page/workaround crawling and SEO review.

Priority order:

1. Query planner and evidence contract.
2. Search/SERP demand adapter.
3. Reddit/forum complaint adapter.
4. Competitor/workaround crawler.
5. X/Twitter corroboration only after the lower-noise adapters work.
6. Weekly Brief/Radar visual surface for validation evidence.

### RVE-0 - Document Radar Validation Evidence Contract

Status: planned.

Goal: define the JSON/report contract that separates candidate hypotheses,
validation queries, matched external evidence, context-only research, and
missing evidence.

Files likely:

- `docs/tasks.md`
- `docs/CODEX_PROMPT.md`
- `docs/mvp_weekly_radar.md`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/README.md`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/mvp_weekly.py`

Contract sketch:

- `validation_queries`: candidate-specific searches grouped by intent:
  `search_demand`, `manual_workarounds`, `competitors`, `wtp_signals`,
  `reddit_forum_complaints`, `github_discussions`, `x_discussions`.
- `matched_external_evidence`: evidence records that are explicitly tied to
  the selected candidate and classified by evidence kind.
- `decision_context.external_research_context`: useful but unmatched research
  that cannot satisfy gates.
- `missing_evidence_by_category`: what is still needed and which query should
  be run next.
- `validation_adapter_status`: per-source status, including
  `ok`, `adapter_disabled`, `credential_limited`, `rate_limited`,
  `cache_only`, and `error`.

Acceptance:

- The contract states that context-only market records never satisfy gates.
- The contract states that unmatched external results never satisfy gates.
- The contract is documented in both repos or linked clearly between them.
- Future adapters have a stable target shape before implementation starts.

Verification:

```bash
rg "validation_queries|matched_external_evidence|context_only|credential_limited" docs /srv/openclaw-you/workspace/Demand-to-MVP-Radar
```

Stop conditions:

- stop if the design treats external search results as build evidence without
  candidate matching;
- stop if the design turns into raw external RAG or a broad idea crawler.

### RVE-1 - Candidate Validation Query Planner

Status: planned.

Goal: add a deterministic query planner in Demand-to-MVP Radar that turns the
selected candidate and shortlist into concrete external validation queries.
This task should not make live network calls yet.

Files likely:

- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/mvp_weekly.py`
- optional new `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/validation_queries.py`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/tests/test_mvp_of_week.py`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/tests/integration/test_report_quality.py`

Planner inputs:

- selected candidate title/summary;
- pain statement;
- ICP/customer type if known;
- workflow keywords;
- existing project fit;
- market lens hints;
- current missing evidence.

Planner output:

- repeatable search queries for demand and pain;
- manual workaround queries;
- competitor/alternative queries;
- WTP/pricing/buying-intent queries;
- Reddit/forum complaint queries;
- GitHub issue/discussion queries for developer workflow candidates;
- X/Twitter corroboration queries marked lower confidence by default.

Acceptance:

- Radar JSON includes `validation_queries` for the selected candidate.
- Radar Markdown includes a concise "Validation Query Pack" section.
- Query pack is deterministic in tests.
- Queries are candidate-specific and not just broad AI-market searches.
- No live network dependency is introduced by this task.

Verification:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py tests/integration/test_report_quality.py
```

Stop conditions:

- stop if query planning calls external APIs;
- stop if queries are generic trend mining instead of candidate validation.

### RVE-2 - Matched Evidence Contract And Gate Wiring

Status: planned after RVE-1.

Goal: add a normalized evidence matcher so external records can affect Radar
only when they are explicitly tied to the selected candidate and classified as
decision-grade validation evidence.

Files likely:

- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/mvp_weekly.py`
- optional new `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/validation_evidence.py`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/tests/test_mvp_of_week.py`

Evidence kinds:

- `repeated_complaint`
- `manual_workaround`
- `search_demand`
- `competitor_traction`
- `wtp_signal`
- `developer_issue`
- `negative_signal`

Acceptance:

- `matched_external_evidence` appears in Radar JSON and Markdown.
- Only matched external evidence can satisfy external source gates.
- Context-only market lens records remain excluded from candidate score and
  source gates.
- Unmatched external research appears only as decision context.
- Missing evidence explains which evidence kind is absent.

Verification:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py tests/test_telegram_research_bridge.py
```

Stop conditions:

- stop if a context-only or unmatched record changes the candidate score;
- stop if the matcher hides negative evidence.

### RVE-3 - Search Demand / SERP Adapter

Status: planned after RVE-1/RVE-2.

Goal: add the first external validation adapter for search demand and SERP
evidence. Prefer existing SERP/source config first; add `yandex-search-api`
and optionally `yandex-wordstat` only behind credentials and cache/dry-run
guards.

Files likely:

- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/sources/*`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/config/mvp_weekly_sources.json`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/tests/*`
- `docs/mvp_weekly_radar.md`

Acceptance:

- Adapter can run in dry-run/cache-only mode.
- Missing credentials produce `credential_limited`, not a crash.
- Results are normalized into the RVE-2 evidence contract.
- Search demand alone can support `investigate`/`focused_experiment` only when
  matched to the candidate and corroborated as required by gates.
- Report shows which query produced each matched item.

Verification:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest
```

Stop conditions:

- stop if credentials are hard-required for the weekly run;
- stop if SERP snippets without matching are counted as source-gate evidence.

### RVE-4 - Reddit / Forum Complaint Adapter

Status: planned after the search adapter.

Goal: validate whether real users complain about the same pain in public
forums. Prefer `reddit-skill` or Reddit API exports when available; keep the
adapter cache-first and credentials-gated.

Files likely:

- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/sources/*`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/tests/*`
- `docs/mvp_weekly_radar.md`

Acceptance:

- Adapter captures complaint text, subreddit/forum, URL, author/date when
  available, and query provenance.
- Evidence matcher classifies repeated complaints and manual workaround
  mentions separately.
- Reddit/forum evidence cannot satisfy gates if it is about an adjacent but
  different pain.
- Missing credentials/rate limits are surfaced in `validation_adapter_status`.

Verification:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py tests/integration/test_report_quality.py
```

Stop conditions:

- stop if generic AI subreddit posts are counted for a specific workflow pain;
- stop if API errors break the weekly report.

### RVE-5 - Competitor / Workaround Crawler Adapter

Status: planned after RVE-3/RVE-4.

Goal: use `crawl4ai-seo` or an equivalent crawler boundary to inspect
competitor pages, alternatives, pricing pages, and public workaround guides
for a selected candidate.

Files likely:

- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/sources/*`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/tests/*`
- `docs/mvp_weekly_radar.md`

Acceptance:

- Adapter records landing URL, title, positioning, pricing/WTP hints, and
  whether the page is a competitor, workaround, integration, or irrelevant.
- Crawler output is bounded by domain/page limits.
- Competitor traction supports validation only when tied to the same pain and
  ICP.
- Negative evidence is shown when pages are irrelevant or only hype.

Verification:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest
```

Stop conditions:

- stop if crawling is unbounded;
- stop if SEO/landing evidence is treated as proof of WTP without support.

### RVE-6 - X/Twitter Corroboration Adapter

Status: planned P2, only after lower-noise adapters work.

Goal: use `x-research` / xAI/Grok-backed X research only as corroborating
discussion evidence for a candidate, not as primary build proof.

Acceptance:

- Adapter is disabled by default unless credentials/config are present.
- Results are classified lower-confidence unless independently corroborated.
- Trend chatter without pain/workaround/WTP content does not satisfy gates.

Stop conditions:

- stop if X trends become the main source of product decisions;
- stop if cost/rate limits are not bounded.

### RVE-7 - Weekly Brief And Radar Validation Surface

Status: planned after the core query/evidence contract lands.

Goal: make the validation layer readable in the Weekly Intelligence Brief and
Radar Markdown/JSON so the operator can quickly see why a candidate is
investigate/reject/focused/build.

Files likely:

- `src/output/weekly_intelligence_brief.py`
- `src/output/mvp_weekly_pipeline.py`
- `src/output/split_intelligence_reports.py`
- `tests/test_weekly_intelligence_brief.py`
- `tests/test_mvp_weekly_pipeline.py`
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/demand_mvp_radar/mvp_weekly.py`

UX blocks:

- MVP Radar Gate Card.
- Validation Query Pack.
- Matched Evidence by source/kind.
- Missing Evidence checklist.
- "What would change the decision" action card.

Acceptance:

- Weekly Brief exposes external validation state without becoming long.
- The operator can see the exact next validation action for the candidate.
- Context-only market lens is clearly labeled as context, not proof.
- If no external validation is found, the report says why and gives next
  repeatable searches.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_weekly_intelligence_brief tests.test_mvp_weekly_pipeline
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/integration/test_report_quality.py
```

Stop conditions:

- stop if this becomes visual polish without better decision clarity;
- stop if the Brief buries the decision and next action.

### RVE-8 - Dogfood Validation Run

Status: planned after RVE-1/RVE-2 and at least one adapter.

Goal: rerun the weekly MVP + split HTML flow and judge whether Radar can now
explain the selected candidate's external demand state.

Commands:

```bash
set -a; source /srv/openclaw-you/.env; [ -f /etc/demand-mvp-radar.env ] && source /etc/demand-mvp-radar.env; set +a
PYTHONPATH=src /srv/openclaw-you/venv/bin/python3 src/main.py mvp-weekly --no-deliver
PYTHONPATH=src /srv/openclaw-you/venv/bin/python3 src/main.py ai-split-report --week 2026-W28 --skip-refresh --threads-limit 24 --atoms-limit 8 --mvp-radar-json /srv/openclaw-you/workspace/Demand-to-MVP-Radar/reports/mvp_of_week/mvp-weekly-2026-W28.json
```

Acceptance:

- Radar JSON includes validation queries, adapter status, matched evidence,
  and missing evidence by category.
- Weekly Brief shows a clear gate card and next validation action.
- A candidate with Telegram-only evidence remains investigate/reject unless
  matched external evidence is present.
- Manual voice/text feedback can be given after reviewing the HTML artifacts.

Stop conditions:

- stop if the run needs a full archive pass;
- stop if private generated reports or large cache artifacts are staged.

## HPI: Hermes / Personal Intelligence Assistant / Dogfood

Status: implemented post-KIR product layer; continue dogfood measurement while
RVE handles the next Radar validation work.

KIR-Q0..KIR-Q13 are implemented. The next phase is HPI: Hermes as a
Telegram-facing operator concierge, PI Assistant as bounded Q&A over curated
intelligence objects, Strategy Reviewer as advisory layer, and a four-week
dogfood protocol that measures real weekly usefulness before adding more
complexity.

Roadmap details:

- `docs/hermes_pi_assistant_roadmap.md`
- `docs/dogfood_4_week_plan.md`

### HPI-0 - Document Hermes/PI Assistant Roadmap And Dogfood Plan

Status: implemented by HPI-0.

Goal: document the post-KIR product layer, architecture boundaries, Hermes
Guide review, Dream Motif Interpreter reference patterns, dogfood protocol, and
Codex-ready implementation queue.

Files likely:

- `docs/hermes_pi_assistant_roadmap.md`
- `docs/dogfood_4_week_plan.md`
- `docs/tasks.md`
- `docs/operator_workflow.md`
- `docs/CODEX_PROMPT.md`
- `docs/ai_intelligence_workbook_roadmap.md`
- `docs/README.md`

Acceptance:

- HPI roadmap exists and states Hermes/PI/Strategy Reviewer boundaries;
- Hermes Guide Review includes Adopt / Defer / Reject;
- Dream Motif Interpreter pattern review is captured;
- four-week dogfood plan exists with metrics and success/failure criteria;
- task queue HPI-0..HPI-10 exists;
- HPI-1 was identified as the next P0 implementation task at HPI-0 handoff;
- docs do not claim Hermes/PI is implemented.

Verification:

```bash
git diff --stat
rg "HPI-0|HPI-1|Hermes|PI Assistant|dogfood|Hermes Guide Review" docs
```

Stop conditions:

- do not implement Hermes commands or vector retrieval inside HPI-0;
- do not touch generated private reports.

### HPI-1 - PersonalIntelligenceFacade Read-Only Contract

Status: implemented by HPI-1.

Goal: add a bounded read-only facade that exposes stable DTO-like access to
current workbook, idea threads, curated intelligence items, project actions,
MVP Radar status, feedback summary, marked posts, and Strategy Reviewer notes.

Files likely:

- `src/assistant/pi_facade.py`
- `tests/test_pi_facade.py`
- maybe `src/assistant/__init__.py`

Implemented files:

- `src/assistant/__init__.py`
- `src/assistant/pi_facade.py`
- `tests/test_pi_facade.py`

Implementation notes:

- HPI-1 creates a read-only facade only.
- The facade exposes stable DTO-like dictionaries/lists for workbook summary,
  workbook sections, idea threads, project actions, MVP Radar status, feedback
  summary, marked posts, and curated intelligence search.
- It does not expose raw SQLite sessions/rows and has no code/config/Codex
  mutation methods.

Acceptance:

- facade instantiates from Settings or repo-local path conventions;
- methods return stable dict/list DTO shapes;
- missing workbook/MVP/feedback/reviewer data returns empty/insufficient
  results instead of crashing;
- no mutation methods exist;
- no sqlite connection, cursor, ORM row, or mutable internal state is exposed;
- tests cover empty states and basic shape stability.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_pi_facade
```

Stop conditions:

- stop if the implementation needs assistant write tools;
- stop if it requires broad raw Telegram RAG;
- stop if it exposes raw database handles to the assistant layer.

### HPI-2-lite - Curated Intelligence Retrieval Items Projection

Status: implemented as HPI-2-lite.

Goal: build a deterministic projection of curated intelligence objects into
`intelligence_retrieval_items` so PI Assistant can search workbook sections,
claim cards, Knowledge Atoms, Idea Threads, thread deltas, action cards,
project diagnostics, feedback events, MVP dossiers, and Strategy Reviewer notes.

Files likely:

- `src/output/intelligence_retrieval_items.py`
- `src/db/` migration/helper for the projection table if needed
- `tests/test_intelligence_retrieval_items.py`

Implemented files:

- `src/output/intelligence_retrieval_items.py`
- `tests/test_intelligence_retrieval_items.py`

Implementation notes:

- HPI-2-lite creates the curated retrieval projection; HPI-9-lite adds
  transient SQLite FTS ranking over that projection.
- It builds an in-memory projection from workbook JSON sidecars, claim cards,
  Knowledge Atoms, Idea Threads, project diagnostics/actions, MVP Radar status,
  feedback summaries, and Strategy Reviewer advisory notes when those curated
  sources are available.
- It is SQLite-first/read-only and skips missing artifacts or tables
  gracefully.
- It does not create a vector index, does not perform raw Telegram firehose
  RAG, and does not introduce mutation tools.
- A persisted refresh table can be considered later only if the in-memory
  projection plus request-local FTS becomes too slow or too hard to inspect.

Acceptance:

- projection has stable IDs, item type, week, title, text/summary, source refs,
  atom IDs, thread slug, project name, confidence/evidence fields, status, and
  timestamps;
- deterministic in-memory projection build is idempotent for the same inputs;
- filters run before broad search;
- no raw Telegram firehose vector index is introduced.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_intelligence_retrieval_items
```

Stop conditions:

- stop if the task turns raw posts into the default answer memory;
- stop if scoped deterministic retrieval cannot express insufficient evidence.

### HPI Phase Implementation Notes After HPI-1..HPI-8

- HPI-3 added the PI Assistant bounded read-only tool catalog around
  `PersonalIntelligenceFacade`.
- HPI-4 added read-only Hermes Telegram concierge commands and bounded LLM chat
  on top of the tool catalog.
- HPI-5 is covered by the existing confirmation-gated `/feedback` and
  `/feedback_voice` flow plus the Hermes intent router: no memory writes happen
  until `/feedback_confirm`.
- HPI-6 delivers structured Strategy Reviewer notes through `/strategy` without
  applying suggestions.
- HPI-7 added a read-only action-status projection; missing feedback stays
  `unknown`.
- HPI-8 added compact dogfood review artifact helpers.
- The first usability slice routes plain text and voice through chat/feedback/
  reminder intent classification and adds once-daily reminders with explicit
  done/not-done callbacks.
- Raw RAG, vector retrieval, mutation tools, autonomous Codex execution, and
  config/profile/project edits are still not implemented.

### HPI-3 - PI Assistant Bounded Tool Catalog

Status: implemented by HPI-3.

Goal: define read-only assistant tools around `PersonalIntelligenceFacade` and
the curated retrieval projection.

Files likely:

- `src/assistant/pi_tools.py`
- `src/assistant/pi_prompts.py`
- `tests/test_pi_tools.py`

Acceptance:

- tools cover weekly summary, section lookup, curated search, thread lookup,
  project actions, MVP status, feedback summary, marked posts, and Strategy
  Reviewer notes;
- tool outputs cite source refs or return insufficient evidence;
- no write tools exist in the default catalog;
- tool loop has a bounded round count when chat is added later.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_pi_tools
```

Stop conditions:

- stop if a tool can edit config/code/profile/projects;
- stop if a tool answers source claims without evidence refs.

Implementation notes:

- `src/assistant/pi_tools.py` defines a read-only `PITool` catalog and
  `call_pi_tool` wrapper.
- `src/assistant/pi_prompts.py` defines the bounded assistant contract and
  `PI_TOOL_LOOP_MAX_CALLS`.
- Tool responses include `evidence_status` plus collected source refs, atom
  ids, thread slugs, and artifact paths.
- Strategy Reviewer access is read through bounded PI/facade DTOs; no mutation
  or DB session is exposed.
- No Telegram commands, vector retrieval, raw firehose RAG, code/config
  editing, or feedback writes were added in HPI-3.

### HPI-4 - Telegram Hermes Concierge Commands

Status: implemented by HPI-4.

Goal: add small Telegram commands for Hermes concierge behavior:
`/weekly`, `/actions`, `/explain`, `/projects`, `/mvp`, `/feedback`,
`/strategy`, and `/codex`.

Files likely:

- `src/bot/handlers.py`
- `src/assistant/pi_facade.py`
- `src/assistant/pi_tools.py`
- `tests/test_bot_handlers.py` or focused handler tests

Acceptance:

- commands are short and action-oriented;
- workbook link/path is surfaced when available;
- `/mvp` preserves Radar status and missing evidence;
- `/codex` shows prepared prompt text only, never executes Codex;
- missing data returns a clear fallback instead of a traceback.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_bot_handlers
```

Stop conditions:

- stop if Hermes becomes the main reading surface;
- stop if commands require multi-user/public product assumptions.

Implementation notes:

- `/weekly`, `/actions`, `/explain`, `/projects`, `/mvp`, `/strategy`, and
  `/codex` are registered in `src/bot/handlers.py`.
- Commands call read-only PI tools/facade methods and format short concierge
  messages.
- `/codex` prepares prompt text only and never executes Codex.
- Existing `/feedback` remains confirmation-gated and was not expanded into a
  direct write surface.

### HPI-5 - Voice Feedback Through PI/Hermes Confirmation Loop

Status: implemented by existing feedback intake and HPI-5 review.

Goal: route voice/text feedback through transcript parsing, structured
proposal, Hermes confirmation, and confirmed memory writes.

Files likely:

- `src/output/ai_report_feedback_intake.py`
- `src/db/ai_report_feedback.py`
- `src/bot/handlers.py`
- `tests/test_ai_report_feedback.py`

Acceptance:

- parsed proposal separates memory writes, suggestions, config changes, code
  changes, and Codex task suggestions;
- confirmation message shows what will be written;
- no confirmed feedback means no memory writes;
- Strategy Reviewer can consume confirmed feedback.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_ai_report_feedback
```

Stop conditions:

- stop if free-form voice feedback directly changes config/code;
- stop if no-reaction is inferred as negative feedback.

Implementation notes:

- `ai_report_feedback_intake` parses text/voice transcripts into proposed
  memory writes and manual-only suggestions.
- `/feedback` and `/feedback_voice` draft confirmation summaries.
- `/feedback_confirm` is the only path that writes confirmed feedback events.
- Config/code/Codex suggestions remain manual-only.

### HPI-6 - Strategy Reviewer Telegram Delivery

Status: implemented by HPI-6.

Goal: deliver Strategy Reviewer summaries to Telegram through Hermes without
letting the reviewer mutate code/config.

Files likely:

- `src/output/strategy_reviewer.py`
- `src/bot/handlers.py`
- `tests/test_strategy_reviewer.py`

Acceptance:

- Telegram summary includes keep/change/demote/test-next-week, memory-only
  updates, approval-required suggestions, Codex tasks, and risks;
- Codex tasks include title, why, likely files, acceptance, and verification;
- no code/config/profile/project mutation is performed.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_strategy_reviewer
```

Stop conditions:

- stop if delivery implies automatic application of reviewer suggestions.

Implementation notes:

- `PersonalIntelligenceFacade.get_strategy_reviewer_notes` returns structured
  read-only Strategy Reviewer DTOs.
- `/strategy` includes keep/change/demote/test-next-week, memory-only updates,
  approval-required items, Codex tasks, risks, and mutation policy.
- Reviewer tasks remain suggestion-only and require approval.

### HPI-7 - Workbook Action Status And Feedback Follow-Up Loop

Status: implemented as read-only HPI-7 status projection.

Goal: let workbook actions carry status and follow-up context so later reports
can show what happened to read/try/project/MVP actions.

Files likely:

- `src/output/ai_intelligence_report.py`
- `src/output/ai_visual_report.py`
- `src/db/ai_report_feedback.py`
- focused report tests

Acceptance:

- action cards have stable target IDs;
- statuses include read, tried, applied_to_project, deferred,
  wrong_priority, not_interested, and unknown;
- next workbook can state which prior feedback changed recommendations;
- unknown stays unknown.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_ai_intelligence_report tests.test_ai_visual_report tests.test_ai_report_feedback
```

Stop conditions:

- stop if the report treats absence of feedback as negative signal.

Implementation notes:

- `src/output/action_status.py` projects workbook action cards to stable action
  status DTOs from confirmed feedback events.
- `PersonalIntelligenceFacade.get_action_statuses` exposes the projection.
- `/actions` shows status and follow-up context.
- Missing feedback is always `unknown`, not negative.
- Full next-workbook narrative integration remains a dogfood follow-up if this
  projection proves useful.

### HPI-8 - Four-Week Dogfood Metrics And Weekly Review Artifact

Status: implemented by HPI-8.

Goal: record dogfood metrics and weekly review notes without turning the system
into another heavy reporting surface.

Files likely:

- `src/output/dogfood_review.py`
- `src/db/` migration/helper if persisted in SQLite
- `tests/test_dogfood_review.py`
- `docs/dogfood_4_week_plan.md`

Acceptance:

- records time-to-understand, sections read, completed read/try/actions,
  feedback counts, MVP statuses, decisions changed, value score, and friction
  score;
- weekly review artifact is compact and private;
- post-four-week review can summarize success/failure criteria;
- generated private artifacts are not committed.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_dogfood_review
```

Stop conditions:

- stop if metrics collection becomes more cumbersome than voice feedback.

Implementation notes:

- `src/output/dogfood_review.py` normalizes weekly dogfood metrics and writes
  compact private JSON/Markdown review artifacts to an explicit output path.
- The helper can summarize four weeks against the dogfood success criteria.
- No generated dogfood artifacts are committed.

### HPI-9 - Optional Scoped Vector Retrieval Over Curated Items Only

Status: deferred P2; do not implement until curated deterministic+FTS search
proves insufficient during dogfood.

Goal: add vector retrieval only if curated deterministic+FTS search proves
insufficient during dogfood.

Files likely:

- `src/output/intelligence_retrieval_items.py`
- `src/assistant/pi_facade.py`
- dedicated retrieval tests

Acceptance:

- vectors are built only over curated intelligence items;
- raw Telegram posts are not vectorized as default assistant memory;
- insufficient evidence remains possible;
- deterministic filters still run before vector/semantic ranking.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_intelligence_retrieval_items tests.test_pi_facade
```

Stop conditions:

- stop if vector retrieval weakens provenance or makes raw archive RAG default.

### HPI-10 - Post-Dogfood Product Decision Review

Status: blocked until four dogfood weeks are recorded.

Goal: decide after four weeks whether to continue, simplify, pause, or add the
next implementation layer.

Files likely:

- `docs/dogfood_4_week_plan.md`
- optional dogfood review artifact code if HPI-8 is implemented
- `docs/tasks.md`

Acceptance:

- review covers four workbook runs, feedback sessions, confirmed feedback
  events, real actions, decisions changed, value score, and friction score;
- next roadmap is based on observed weekly use;
- features that added friction are removed or deferred.

Verification:

```bash
rg "Post-Four-Week Review|decisions_changed_by_system|friction_score" docs
```

Stop conditions:

- stop if the review is skipped and new complex features are proposed anyway.

### HPI-11 - Hermes Telegram UX And Tbilisi Timezone Cleanup

Status: implemented by HPI-11.

Goal: make Hermes feel like a normal private assistant, not a slash-command
debug console. Fix Telegram escaping, use the operator timezone, and keep slash
commands as manual fallbacks instead of the primary visible UX.

Problem statement:

- Current Telegram messages can render escaped punctuation such as
  `1\. Открой weekly HTML Workbook\.` because `send_message(...,
  parse_mode=None)` still MarkdownV2-escapes text.
- Reminder scheduling is operationally correct but should be explicitly
  operator-local: `Asia/Tbilisi`.
- Help/onboarding should not show a wall of `/commands` to the operator.

Files likely:

- `src/bot/handlers.py`
- `src/bot/telegram_delivery.py`
- `src/bot/callbacks.py`
- `src/output/operator_reminders.py`
- `systemd/telegram-reminders.timer`
- `/srv/openclaw-you/.env` for non-secret `REMINDER_TIMEZONE=Asia/Tbilisi`
- `tests/test_handlers.py`
- `tests/test_callbacks.py`
- `tests/test_operator_reminders.py`
- `README.md`
- `docs/operator_workflow.md`

Implemented files:

- `src/bot/handlers.py`
- `src/output/operator_reminders.py`
- `systemd/telegram-reminders.timer`
- `tests/test_handlers.py`
- `tests/test_operator_reminders.py`
- `README.md`
- `docs/operator_workflow.md`
- `docs/tasks.md`
- `docs/CODEX_PROMPT.md`

Implementation result:

- `send_message(..., parse_mode=None)` sends plain text without MarkdownV2
  escaping; escaping is applied only when `parse_mode` is `MarkdownV2`.
- `/start` and `/help` start with normal private-assistant guidance: write text
  or send voice first; slash commands remain available as manual fallbacks.
- Reminder parsing, formatting, daily digest labels, and
  `telegram-reminders.timer` use `Asia/Tbilisi`.
- `REMINDER_TIMEZONE` remains an optional override and defaults to
  `Asia/Tbilisi`.

Implementation notes:

- Fix `send_message` so escaping is applied only when `parse_mode` is
  `MarkdownV2`. `parse_mode=None` must send plain text without backslashes.
- Add tests that assert rendered/help text does not contain escaped dots such
  as `\.` or escaped list numbers such as `1\.`
- Use `Asia/Tbilisi` for all user-facing reminder parsing/formatting.
- Prefer a daily reminder slot expressed in Tbilisi time. If systemd
  `Timezone=Asia/Tbilisi` verifies cleanly, use it; otherwise use a UTC
  `OnCalendar` equivalent and document the mapping.
- Keep slash commands available, but remove slash-heavy lists from normal
  help/onboarding text. Say "just write or send voice" first.
- Add confirmation buttons for feedback drafts if the callback contract already
  supports it cleanly; otherwise leave a small follow-up note for HPI-12.

Acceptance:

- Telegram help and normal bot messages render without `\.` / `1\.` artifacts.
- Daily reminders are scheduled and displayed in `Asia/Tbilisi`.
- `/help` is compact and user-facing; slash commands are presented only as
  fallback/manual options.
- Existing explicit commands still work.
- No mutation/code/config/Codex capability is added.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_handlers tests.test_callbacks tests.test_operator_reminders
systemd-analyze verify systemd/telegram-reminders.service systemd/telegram-reminders.timer
systemctl list-timers 'telegram-*' --all --no-pager
```

Stop conditions:

- stop if the fix requires switching Telegram delivery to a new gateway;
- stop if user-facing text becomes another long command manual.

### HPI-12 - Opus Feedback Strategist

Status: implemented by HPI-12.

Goal: upgrade feedback handling from "parse and store" to "understand, propose,
and confirm". Feedback should be interpreted by an Opus-class model with a
dedicated system prompt because it is the main learning signal for the private
intelligence loop.

Files likely:

- `src/output/ai_report_feedback_intake.py`
- `src/assistant/pi_intent.py`
- `src/llm/client.py`
- optional `src/assistant/feedback_prompts.py`
- `src/bot/handlers.py`
- `src/bot/callbacks.py`
- `tests/test_ai_report_feedback.py`
- `tests/test_handlers.py`
- `tests/test_pi_intent.py`
- `README.md`
- `docs/operator_workflow.md`

Implemented files:

- `src/assistant/feedback_prompts.py`
- `src/output/ai_report_feedback_intake.py`
- `src/llm/client.py`
- `tests/test_ai_report_feedback.py`
- `tests/test_llm_client.py`
- `README.md`
- `docs/operator_workflow.md`
- `docs/tasks.md`
- `docs/CODEX_PROMPT.md`

Implementation result:

- Text and voice feedback drafts first try the `feedback_intake_strategist`
  LLM category with default model `claude-opus-4-8` and env override
  `LLM_MODEL_FEEDBACK_INTAKE_STRATEGIST`.
- The strategist prompt returns separated proposed memory events,
  report/workbook suggestions, Codex task drafts, clarifying questions, risk
  notes, and confirmation summary.
- Proposed memory events are normalized into the existing
  `ai_report_feedback_intakes.proposals_json`; report changes, Codex task
  drafts, questions, and risk notes are stored as manual-only suggestions.
- If the strategist call fails or returns invalid output, intake falls back to
  deterministic parsing.
- Feedback events are still written only by `/feedback_confirm` /
  `apply_confirmed_feedback_intake`.

Model routing:

- Add category `feedback_intake_strategist`.
- Default model: `claude-opus-4-8`.
- Env override: `LLM_MODEL_FEEDBACK_INTAKE_STRATEGIST`.
- Transcription remains OpenAI audio (`VOICE_TRANSCRIPTION_MODEL`, default
  `whisper-1`); only interpretation/strategy uses Opus.

System prompt requirements:

- Treat feedback as private operator learning signal.
- Extract what was useful, wrong-priority, too shallow, missed, tried,
  applied-to-project, not interesting, and trust corrections.
- Propose confirmed memory events, but do not write memory until operator
  confirmation.
- Propose report/workbook changes separately from memory writes.
- Propose Codex-ready tasks only as drafts requiring manual approval.
- Never change scoring/config/profile/projects/code directly.
- Preserve "no reaction is not negative".
- Return explicit uncertainty when feedback is ambiguous.

Output shape should separate:

- `memory_events_proposed`;
- `report_changes_suggested`;
- `codex_tasks_suggested`;
- `clarifying_questions`;
- `risk_notes`;
- `confirmation_summary`.

Acceptance:

- Text and voice feedback use the Opus strategist path after transcription.
- Operator sees a concise confirmation summary and can confirm/discard.
- Memory writes remain confirmation-gated.
- Strategy suggestions do not mutate code/config/profile/projects.
- Tests prove model category routing and fallback behavior.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_ai_report_feedback tests.test_handlers tests.test_pi_intent
```

Stop conditions:

- stop if feedback interpretation writes memory without confirmation;
- stop if Opus suggestions are treated as applied Strategy Reviewer changes.

### HPI-13 - Market Business Channel Pack For MVP Radar

Status: implemented by HPI-13.

Goal: create a separate market/business intelligence input for MVP Radar from
operators who understand AI market pain, distribution, and business models.
This should improve Radar context and audit whether current filters are too
strict, without running a costly full-year archive pass.

Requested channels:

- `https://t.me/its_capitan`
- `https://t.me/exitsexist`
- `https://t.me/leadgenvalley`
- `https://t.me/cryptoEssay`
- `https://t.me/huntermikevolkov`

Files likely:

- `src/config/channels.yaml`
- `src/ingestion/bootstrap_ingest.py`
- `src/ingestion/incremental_ingest.py`
- `src/output/knowledge_extraction.py`
- `src/output/opportunity_seed_export.py`
- `src/output/mvp_weekly_pipeline.py`
- new optional `src/output/market_pain_intelligence.py`
- `tests/test_opportunity_seed_export.py`
- `tests/test_mvp_weekly_pipeline.py`
- new tests for market pain pack
- `docs/operator_workflow.md`

Implemented:

- `src/config/channels.yaml` now marks the requested market/business channels
  under `market_business_ai` and adds `@huntermikevolkov`.
- `src/output/market_pain_intelligence.py` builds a bounded, deterministic,
  cited market analyst context pack from curated Knowledge Atoms and Idea
  Threads first, with raw-post fallback only for requested channels that have
  not yet produced curated atoms in the lookback.
- The pack exposes what seems to work, what does not work, market pains,
  buying/WTP triggers, customer segments, distribution channels,
  workflow/business-model opportunities, proof points, source refs, and Radar
  gate-audit fields.
- `opportunity_seed_export` writes a market context sidecar and can add a
  context-only `market_analyst_context` Radar seed without consuming the
  ordinary opportunity seed limit.
- `mvp_weekly_pipeline` carries the pack through operator output and explains
  empty bounded lookbacks instead of silently looking empty.
- CLI output reports the market pack path and status for opportunity seed
  export and weekly MVP runs.
- Regression coverage verifies curated atom/thread context, raw fallback
  context, context-only seeds beyond the ordinary limit, empty-pack audit
  behavior, and operator-message explanation for empty market packs.

Implementation notes:

- First inspect whether those channels already exist in `channels.yaml` and the
  local DB.
- If missing, add them under a distinct group such as `market_business_ai`.
- Do a bounded backfill/lookback only, for example 90 days or a configurable
  limit. Do not start the one-year full archive pass in this task.
- Extract a market pain pack from these sources:
  - repeated pains;
  - ICP/customer type;
  - urgency/willingness-to-pay hints;
  - distribution/channel hints;
  - workflow/business-model opportunities;
  - anti-signals and hype warnings;
  - source refs.
- Feed the pack to MVP Radar as context, not as unconditional build evidence.
- Add a Radar gate audit explaining why recent weeks selected/rejected
  candidates and whether the filter is too strict.
- MVP Radar should surface several candidate ideas when evidence exists, but
  still mark weak candidates as investigate/reject instead of build-worthy.

Acceptance:

- Market channels can be ingested or reused from existing DB data.
- Market pain pack is deterministic, cited, and bounded.
- MVP weekly can consume the pack without treating Telegram-only evidence as
  build-ready proof.
- Output explains "nothing passed" weeks instead of silently looking empty.
- Regression tests for opportunity seed export and MVP weekly still pass.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_opportunity_seed_export tests.test_mvp_weekly_pipeline
```

Stop conditions:

- stop if this turns into an unbounded annual backfill;
- stop if market commentary alone bypasses Radar evidence gates;
- stop if private generated reports are staged.

### HPI-14 - Split HTML Into Knowledge Atlas And Weekly Intelligence Brief

Status: implemented by HPI-14.

Goal: stop forcing one HTML artifact to be both a global knowledge map and a
weekly action brief. Produce two distinct reader-facing HTML surfaces.

Artifact 1: Knowledge Atlas.

- cumulative/global view of how the knowledge base expanded;
- new and evolving Knowledge Atoms and Idea Threads;
- trend timelines and momentum;
- source/channel contribution;
- ideas the operator has not studied yet;
- infographic/diagram-heavy knowledge map;
- focus-maintenance document for long-running AI/business learning.

Artifact 2: Weekly Intelligence Brief.

- what changed this week;
- concise decision brief;
- implementation/action results;
- MVP Radar result with several candidate ideas when evidence exists;
- explicit reject/investigate/build/focused-experiment gates;
- read/try/watch prompts;
- feedback prompts.

Files likely:

- `src/output/ai_visual_report.py`
- `src/output/ai_intelligence_report.py`
- new optional `src/output/knowledge_atlas_report.py`
- new optional `src/output/weekly_intelligence_brief.py`
- `src/output/obsidian_export.py`
- `tests/test_ai_visual_report.py`
- `tests/test_ai_intelligence_report.py`
- new report contract tests
- `README.md`
- `docs/operator_workflow.md`

Implemented:

- `src/output/knowledge_atlas_report.py` renders a cumulative/rolling
  Knowledge Atlas with overview metrics, Idea Thread map, trend board,
  source/concept contribution, study backlog, and bounded audit metadata.
- `src/output/weekly_intelligence_brief.py` renders a short Weekly
  Intelligence Brief with decision snapshot, week changes, action/read/try
  prompts, MVP Radar status, and feedback prompts.
- `src/output/split_intelligence_reports.py` loads curated context once and
  writes both surfaces with distinct HTML/JSON filenames and cross-linked
  sidecars.
- `src/main.py ai-split-report` exposes the split generation loop with
  `--skip-refresh`, `--threads-limit`, `--atoms-limit`, `--output-root`, and
  optional `--mvp-radar-json`.
- `src/output/intelligence_retrieval_items.py` can discover split sidecars and
  project their sections/MVP status into read-only Hermes/PI retrieval items.
- Tests verify distinct Atlas/Brief outputs, sidecar cross-links, MVP Radar
  inclusion, short Brief action ordering, and split-sidecar retrieval.

Implementation notes:

- Do not duplicate heavy generation if shared JSON sidecars can be reused.
- Keep JSON sidecars stable for Hermes/PI retrieval.
- Atlas may be cumulative/rolling; Weekly Brief should stay short and
  operational.
- Obsidian remains a generated navigation/audit projection, not the runtime
  source of truth.

Acceptance:

- Two HTML outputs have distinct filenames, titles, JSON sidecars, and delivery
  semantics.
- Weekly Brief can be read quickly and does not bury the week's actions.
- Knowledge Atlas shows trend development over time.
- Hermes/PI retrieval can still read the relevant sidecars.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_ai_visual_report tests.test_ai_intelligence_report tests.test_intelligence_retrieval_items tests.test_pi_facade
```

Stop conditions:

- stop if this becomes visual polish without improving weekly comprehension;
- stop if the Atlas becomes an unbounded mirror of every Telegram post.

### HPI-9-lite - Curated Semantic RAG Decision And Prototype

Status: implemented by HPI-9-lite; do not implement raw Telegram RAG.

Goal: decide whether the PI Assistant needs semantic retrieval, and if yes,
prototype it over curated knowledge objects only.

Reference implementation:

- `/srv/openclaw-you/workspace/Dream_Motif_Interpreter`
- especially:
  - `app/retrieval/query.py`
  - `app/assistant/chat.py`
  - `app/assistant/facade.py`
  - `app/assistant/tools.py`
  - `app/assistant/prompts.py`

Architecture position:

- SQLite + workbook/JSON sidecars remain source of truth.
- Obsidian is a generated human navigation/audit layer, not runtime memory.
- Deterministic curated retrieval remains baseline.
- Semantic RAG, if added, searches curated items only:
  - Knowledge Atoms;
  - Idea Threads;
  - claim cards;
  - workbook sections;
  - MVP dossiers;
  - Strategy Reviewer notes;
  - confirmed feedback summaries.
- Raw Telegram posts are not default assistant memory.

Decision:

- Vector RAG is not needed now. It stays deferred until dogfood produces
  specific curated-search misses.
- The accepted prototype is deterministic curated ranking plus transient
  SQLite FTS5 over filtered `IntelligenceRetrievalItem` objects.
- The decision record lives in `docs/curated_semantic_retrieval.md`.
- Dream Motif patterns adopted: facade boundary, exact/FTS before vector,
  filters before ranking, provenance, and insufficient-evidence states.
- Dream Motif parts deferred: Postgres/pgvector, persisted embeddings, and LLM
  query expansion.

Files likely:

- `src/output/intelligence_retrieval_items.py`
- `src/assistant/pi_facade.py`
- `src/assistant/pi_chat.py`
- optional `src/assistant/semantic_retrieval.py`
- `tests/test_intelligence_retrieval_items.py`
- `tests/test_pi_facade.py`
- `tests/test_pi_chat.py`
- docs update capturing the retrieval decision

Implemented:

- `src/assistant/semantic_retrieval.py` adds the curated-only prototype:
  filter-first request-local SQLite FTS5, deterministic rank merge, small
  deterministic domain query expansion, raw-post item-type denylist, and
  `retrieval_mode` metadata.
- `src/assistant/pi_facade.py` routes `search_intelligence_items` through the
  curated deterministic+FTS prototype and returns `retrieval_decision`.
- `src/assistant/pi_prompts.py` tells the assistant that curated FTS is allowed
  but raw Telegram firehose retrieval and vector memory remain disallowed.
- `tests/test_semantic_retrieval.py` covers MVP Radar expansion, filter-first
  retrieval, raw item exclusion, and the vector/raw-RAG decision note.
- `tests/test_pi_facade.py` covers the facade-level retrieval decision and
  curated FTS search path.

Implementation plan:

1. Read the Dream Motif retrieval code and summarize what is reusable.
2. Add an architecture note: deterministic search vs SQLite FTS vs vector
   retrieval over curated objects.
3. Prefer SQLite FTS or deterministic+FTS as the first prototype if it solves
   the observed misses.
4. Add vector embeddings only if FTS cannot solve real dogfood misses.
5. Keep filters before semantic search: week, item type, project, thread,
   status.
6. Preserve source refs, atom IDs, evidence tier, and insufficient-evidence
   states.

Acceptance:

- Decision note explains whether RAG is needed now and why.
- Prototype, if implemented, searches curated items only.
- No raw Telegram firehose vector index is created.
- PI Assistant answers include provenance and can still say insufficient
  evidence.
- Tests cover deterministic fallback and missing index behavior.

Verification:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_semantic_retrieval tests.test_intelligence_retrieval_items tests.test_pi_facade tests.test_pi_tools tests.test_pi_chat
```

Stop conditions:

- stop if the task attempts raw-post RAG by default;
- stop if the implementation requires Postgres/pgvector as P0;
- stop if semantic retrieval weakens provenance.

## KIR-Q: AI Intelligence Quality / Workbook / Feedback / Radar Contract

Status: active planning and implementation queue.

The earlier KIR-Q-001..KIR-Q-009 quality-audit tasks below record the W28
report-contract implementation history. The active product queue now moves from
weekly report plumbing to a Weekly AI Intelligence Workbook, feedback intake,
and a stronger KIR-backed Radar contract. Roadmap details live in
`docs/ai_intelligence_workbook_roadmap.md`.

### KIR-Q0 - Document AI Intelligence Workbook Roadmap

Status: implemented by KIR-Q0.

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

Status: implemented by KIR-Q1.

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

Status: implemented by KIR-Q2.

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

Status: implemented by KIR-Q3.

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

Status: implemented by KIR-Q4.

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

Status: implemented by KIR-Q5.

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

Status: implemented by KIR-Q6.

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

Status: implemented by KIR-Q7.

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

Status: implemented by KIR-Q8.

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

Status: implemented by KIR-Q9.

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

Status: implemented by KIR-Q10.

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

Status: implemented by KIR-Q11.

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

Status: implemented by KIR-Q12.

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

Status: implemented by KIR-Q13.

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
