# Telegram Research Agent — Development Roadmap

**Version:** 3.0
**Date:** 2026-03-31
**Status:** Roadmap v2 complete. Roadmap v3 starts here.

---

## Current State

Roadmap v2 (Phases 1–8, tasks T29–T64) is complete. 83 tests passing. CI on every push.

What exists now:
- deterministic scoring pipeline (5 dimensions, configurable weights)
- three-tier model routing (CHEAP/MID/STRONG) with cost logging
- signal-first report format (`format_signal_report()`) with 8 sections
- project relevance scoring (keyword matching, `project_relevance_score`)
- personalization layer (boost/downrank with strong-post floor protection)
- learning gap detection (`extract_learning_gaps()`)
- CLI: `score-stats`, `cost-stats`, `health-check`, `report-preview`
- delivery: Telegram text messages with Markdown sections

What does NOT yet exist:
- weekly review as a readable article artifact (Telegraph / HTML / Instant View)
- Telegram notification + separate full artifact link delivery model
- source traceability links in the report (t.me deep links per signal)
- "What changed since last week" section (delta computation)
- "Decisions to consider" section (explicit action items)
- project action queue (per-project sub-sections)
- feedback/taste capture (acting-on-signal tracking)

---

## Roadmap v3 — Next Phases

### Phase 0 — Documentation Reset (COMPLETE)

This phase. Repository documentation aligned with new product framing.

Deliverables:
- `README.md` rewritten — product thesis, three signal layers, model selection guide
- `docs/architecture.md` rewritten — component contracts, design constraints
- `docs/spec.md` updated — framing, schema, AD notes
- `docs/report_format.md` created — full artifact specification
- `docs/operator_workflow.md` created — week-to-week operating guide
- `docs/tasks.md` updated — this document

---

## 1. Updated System Architecture

### High-level flow

```text
Ingestion
  -> Preprocessing
  -> Scoring
  -> Routing
  -> Interpretation
  -> Project Lens
  -> Learning Layer
  -> Output Layer

Cross-cutting:
  Personalization
  Observability
```

### What changed

- `Routing` is now an explicit layer instead of an implicit detail inside LLM calls.
- `Output` changes from digest taxonomy to a signal-first decision format.
- `Personalization` becomes a system layer rather than a few profile boosts.
- `Observability` becomes mandatory because cost, escalation, and relevance quality are now first-order concerns.

### Why each layer is required

| Layer | Why it exists now |
|---|---|
| Ingestion | Preserve source-of-truth corpus and source metadata |
| Preprocessing | Produce deterministic, comparable features before interpretation |
| Scoring | Gate later work with reproducible signal estimates |
| Routing | Protect cost budget and keep strong models focused on high-value items |
| Interpretation | Turn selected signals into explicit meaning and implications |
| Project Lens | Separate general importance from project-specific relevance |
| Learning Layer | Convert recurring validated signals into study priorities |
| Output Layer | Present decisions, not summaries |
| Personalization | Make ranking user-specific and accumulate preference memory |
| Observability | Measure routing quality, output quality, and cost discipline |

---

## 2. Phase Restructuring

## Phase 1 — Baseline Stabilization

**Goal**

Stabilize the current system, remove architecture drift, and establish documentation, metrics, and contracts needed for disciplined iteration.

**What is implemented**
- reconcile current codebase with living docs
- lock current scoring/output behavior as baseline
- define quality metrics schema and measurement procedure
- identify stale prompt contracts and outdated phase references
- document non-goals and frozen interfaces for the next phases

**What is NOT included**
- no new routing logic
- no new output taxonomy in production
- no personalization logic beyond documenting current state

**Dependencies**
- none; this phase starts immediately

**Risks**
- false confidence if baseline metrics are not captured
- hidden drift between docs and code

**Success criteria**
- baseline behavior is documented and reproducible
- current metrics can be collected for a full run
- docs no longer describe the product as a digest bot

**Cycle 3 fix tasks**

- T35 [P1] — Add `time.sleep(1)` between digest send and insights send in `src/output/generate_digest.py:534–546`; add test asserting sleep is called between the two `send_text` calls. Blocks production digest run until resolved. (CODE-12)

---

## Phase 2 — Scoring Foundation

**Goal**

Turn scoring into the stable control plane for later routing, relevance, and personalization decisions.

**What is implemented**
- scoring dimensions and thresholds review
- deterministic signal buckets
- evidence fields explaining score composition
- basic quality metrics for score distribution
- tests/evals for precision of strong vs weak/noise segmentation

**What is NOT included**
- no multi-model routing yet
- no personal preference modulation
- no large output redesign beyond mapping current buckets to future needs

**Dependencies**
- Phase 1

**Risks**
- overfitting heuristics to a tiny sample
- unstable thresholds causing churn between weeks

**Success criteria**
- strong bucket is small and defensible
- weak/noise separation is measurable
- score distribution is stable across multiple runs

**Tasks**

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| T36 | Add `score_run_id` + `scored_at` columns to `posts`; populate in `score_posts()`; run migration idempotently | codex | `[ ]` | T35 |
| T37 | Add `score_breakdown` JSON column to `posts` (stores per-dimension scores: channel_priority, topic_relevance, novelty, actionability, personal_interest); populate in `score_posts()` | codex | `[ ]` | T36 |
| T38 | Expose `score_distribution` CLI command: `python3 src/main.py score-stats` — prints bucket counts, avg scores per bucket, top 3 topics per bucket for last 7 days | codex | `[ ]` | T37 |
| T39 | Add 3 evals to `tests/test_score_posts.py`: (a) strong bucket ≤ 20% of total scored posts, (b) noise bucket ≥ 30%, (c) score_breakdown sums within ±0.05 of signal_score | codex | `[ ]` | T37 |
| T40 | Fix CODE-9: add MID tier test to `tests/test_router.py` (`signal_score=0.6` → MID, `signal_score=0.45` boundary → MID) | codex | `[ ]` | T35 |
| T41 | Fix CODE-11: remove dead import `generate_recommendations` from `handlers.py:15`; update test accordingly | codex | `[ ]` | T35 |

**Phase 2 Review Criteria**
- `posts` table has `score_run_id`, `scored_at`, `score_breakdown` columns; migration is idempotent
- `score-stats` CLI command runs without error and prints non-empty output
- `test_score_posts.py` has bucket distribution evals that would fail on a random scorer
- `test_router.py` covers all 3 tiers
- Dead import removed from `handlers.py`
- 45+ tests passing

---

## Phase 3 — Model Routing

**Goal**

Introduce cost-aware multi-model routing so only high-value items reach expensive interpretation.

**What is implemented**
- `CHEAP / MID / STRONG` model tiers
- routing policy and escalation rules
- conditional execution by bucket, confidence, and cost budget
- routing observability: escalation rate, tier usage, cost per run
- prompt/runtime contracts for tier-specific tasks

**What is NOT included**
- no deep personalization logic
- no product-surface expansion
- no routing based on learned taste signals yet

**Dependencies**
- Phase 2

**Risks**
- routing complexity before metrics exist
- routing rules that are too opaque to debug
- too many items escalating to strong tier

**Success criteria**
- strong tier receives only a minority of items
- cost per run drops or stays bounded while preserving output quality
- routed subsets remain interpretable and reviewable

**Tasks**

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| T42 | Fix CODE-10: guard `signal_score=None` in `router.py` — emit `LOGGER.warning` and return CHEAP_MODEL instead of silently coercing to 0.0 | codex | `[ ]` | T41 |
| T43 | Wire per-post routing: `score_posts()` calls `route("per_post", signal_score=...)` and stores result in new `routed_model TEXT` column in `posts` (idempotent migration) | codex | `[ ]` | T42 |
| T44 | Populate `llm_usage` table after each LLM call in `client.py`: insert row with `model`, `task_type`, `input_tokens`, `output_tokens`, `est_cost_usd`, `called_at` (idempotent migration) | codex | `[ ]` | T43 |
| T45 | Add `cost-stats` CLI subcommand: `python3 src/main.py cost-stats` — prints total cost, cost by model, number of runs from `llm_usage` table | codex | `[ ]` | T44 |
| T46 | Fix ARCH-1: add `complete_vision()` in `src/llm/client.py` with same retry wrapper as `complete()`; route `src/llm/vision.py` through it instead of calling Anthropic directly | codex | `[ ]` | T43 |
| T47 | Fix ARCH-2: extract `handle_ask` business logic from `src/bot/handlers.py` to `src/output/generate_answer.py`; handler calls `generate_answer()` | codex | `[ ]` | T46 |

**Phase 3 Review Criteria**
- `route("per_post", signal_score=None)` returns CHEAP_MODEL with a warning (not silent coercion)
- `posts` table has `routed_model` column populated after `score_posts()`
- `llm_usage` table is populated after LLM calls; `cost-stats` CLI works on empty and non-empty DB
- `vision.py` routes through `complete_vision()` retry wrapper
- `handle_ask` business logic is in `generate_answer.py`
- 54+ tests passing

---

## Phase 4 — Signal-First Output

**Goal**

Replace digest-style reporting with signal-first decision support.

**What is implemented**
- new output sections:
  - Strong signals
  - Project relevance
  - Weak signals
  - Think layer
  - Light/cultural
  - Ignored
- concise evidence-forward report structure
- output contracts for readability and section completeness
- example outputs reflecting triage, not dumping

**What is NOT included**
- no full personalization ordering yet
- no multi-surface UI work beyond current delivery channels

**Dependencies**
- Phase 3

**Risks**
- verbose output that recreates the digest in another shape
- weak explanation of ignored items

**Success criteria**
- output is scannable in minutes
- strong signals are visibly distinct from weak/cultural items
- ignored/noise handling is explicit and trusted

**Tasks**

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| T48 | Create `src/output/signal_report.py` with `format_signal_report(posts, settings) -> str` — outputs 6 structured sections: Strong Signals, Watch, Cultural, Ignored, Think Layer (themes from strong+watch), Stats footer | codex | `[ ]` | T47 |
| T49 | Wire `format_signal_report()` into `generate_digest.py` — prepend signal-first section to digest output; existing LLM synthesis remains but follows the structured section | codex | `[ ]` | T48 |
| T50 | Each Strong Signals entry must show: post summary (≤20 words), signal_score, bucket, routed_model; Watch entries show summary + score; Ignored shows only count + top 3 topics | codex | `[ ]` | T48 |
| T51 | 3 output contract tests in `tests/test_signal_report.py`: (a) empty posts → all 6 headers present; (b) mixed posts → Strong section before Watch; (c) noise posts → Ignored shows count not full content | codex | `[ ]` | T48 |

**Phase 4 Review Criteria**
- `format_signal_report()` exists and returns a string with all 6 section headers
- Strong signals ranked by signal_score descending, each showing score + routed_model
- Ignored/noise section shows count only (not full post text)
- Signal-first section appears in digest output before LLM synthesis
- 60+ tests passing

---

## Phase 5 — Project Relevance Upgrade

**Goal**

Make project relevance a first-class decision layer rather than an append-only insight section.

**What is implemented**
- stronger project matching logic
- relevance tiers and rationale contracts
- separation of global significance vs project significance
- better linkage between routed signals and active projects

**What is NOT included**
- no user taste memory yet
- no learning recommendations based on personal behavior

**Dependencies**
- Phase 3 and Phase 4

**Risks**
- project matching becomes too permissive
- relevance explanations are generic and not actionable

**Success criteria**
- project relevance section contains fewer but stronger matches
- users can see why an item matters for a specific project
- false-positive project links are reduced

**Tasks**

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| T52 | Create `src/output/project_relevance.py` with `score_project_relevance(post_content, projects) -> list[dict]` — for each project returns `{name, score (0.0-1.0), rationale (str)}` using keyword overlap from project focus/description; no LLM call | codex | `[ ]` | T51 |
| T53 | Add `project_relevance` section to `signal_report.py` — replace or supplement existing project_matches with top 3 project matches (score ≥ 0.3 threshold), each showing project name + rationale; add after Stats section | codex | `[ ]` | T52 |
| T54 | Add `project_relevance_score REAL` column to `posts` table (idempotent migration); populate with max project match score after scoring | codex | `[ ]` | T52 |
| T55 | 3 tests in `tests/test_project_relevance.py`: (a) post with focus keywords returns score ≥ 0.5 for matching project; (b) post with no keyword overlap returns score < 0.2 for all projects; (c) score_project_relevance returns rationale string | codex | `[ ]` | T52 |

**Phase 5 Review Criteria**
- `score_project_relevance()` uses keyword matching (no LLM), returns score + rationale per project
- Only matches with score ≥ 0.3 appear in signal report
- `posts` table has `project_relevance_score` column
- False positives reduced: unrelated posts don't appear in project section
- 66+ tests passing

---

## Phase 6 — Personalization / Taste Model

**Goal**

Make prioritization user-aware through explicit profile, downranking, and preference memory.

**What is implemented**
- user profile schema
- interest and anti-interest rules
- preference memory and feedback capture model
- personalized re-ranking on top of core signal quality
- taste-aware ordering in output

**What is NOT included**
- no fully autonomous reinforcement loop
- no opaque learned model that cannot be audited

**Dependencies**
- Phase 2, Phase 3, and Phase 5

**Risks**
- fake personalization based on weak signals
- brittle preference rules that overfit transient interests
- hiding objectively important signals

**Success criteria**
- ranking changes are explainable
- personalization improves relevance without collapsing diversity
- user profile can downrank noise without suppressing important outliers

**Tasks**

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| T56 | Create `src/output/personalize.py` with `apply_personalization(posts, profile) -> list[dict]` — re-ranks posts by multiplying signal_score by boost/downrank multipliers from `profile.yaml`; returns sorted list with `personalized_score` field; strong posts never drop below watch threshold | codex | `[ ]` | T55 |
| T57 | Wire `apply_personalization()` into `signal_report.py` — load profile.yaml, apply personalization before formatting sections; add `[personalized]` tag to entries whose order changed | codex | `[ ]` | T56 |
| T58 | 3 tests in `tests/test_personalize.py`: (a) boost_topic post gets higher personalized_score than neutral; (b) downrank_topic post gets lower score; (c) strong post (signal_score=0.8) with downrank_topic stays ≥ watch threshold (0.45) | codex | `[ ]` | T56 |

**Phase 6 Review Criteria**
- `apply_personalization()` uses profile.yaml boost/downrank, no LLM calls
- Strong posts cannot be downranked below watch threshold
- `[personalized]` tag appears in signal report for re-ranked entries
- 72+ tests passing

---

## Phase 7 — Learning Layer Refinement

**Goal**

Convert recurring validated signals into focused learning guidance.

**What is implemented**
- stronger mapping from signals to knowledge gaps
- learning priorities tied to project goals and persistent themes
- think-layer vs learn-layer separation
- evals for novelty and usefulness of recommendations

**What is NOT included**
- no broad educational content generation pipeline
- no habit/coach product features

**Dependencies**
- Phase 4, Phase 5, and Phase 6

**Risks**
- learning guidance repeats obvious topics
- recommendations follow hype instead of strategic need

**Success criteria**
- learning outputs are sparse, concrete, and linked to validated signals
- recommendations are clearly downstream of project and personal context

**Tasks**

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| T59 | Create `src/output/learning_layer.py` with `extract_learning_gaps(posts, projects) -> list[dict]` — finds recurring strong/watch topics not yet in any project's focus, returns list of `{topic, frequency, rationale, linked_project}` (max 5 items); no LLM call | codex | `[ ]` | T58 |
| T60 | Add `## Learn` section to `signal_report.py` — render top 3 learning gaps from extract_learning_gaps(); format: "- <topic> (seen N times) → <rationale>"; if no gaps: "No new learning gaps identified." | codex | `[ ]` | T59 |
| T61 | 2 tests in `tests/test_learning_layer.py`: (a) 5 posts with same topic not in any project focus → gap returned with frequency=5; (b) topic already in a project focus → NOT returned as gap | codex | `[ ]` | T59 |

**Phase 7 Review Criteria**
- `extract_learning_gaps()` only surfaces topics NOT in any project focus
- Frequency counted correctly across posts
- Learn section appears in signal report with max 3 items
- 75+ tests passing

---

## Phase 8 — Productization / Surface Layer

**Goal**

Package the intelligence system into a stable operator-facing product surface.

**What is implemented**
- final delivery structure for Telegram and file artifacts
- better observability and operator controls
- configuration cleanup
- release readiness checks
- human-readable examples and operator docs

**What is NOT included**
- no major core-logic rewrites
- no new intelligence layers

**Dependencies**
- all prior phases

**Risks**
- polishing the surface while core quality is still unstable
- freezing bad defaults into operator UX

**Success criteria**
- product surface exposes the new signal-first model clearly
- operators can inspect cost, routing, and quality metrics
- the system is understandable without reading the code

**Tasks**

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| T62 | Add `health-check` CLI subcommand: `python3 src/main.py health-check` — prints DB path, test DB connection, counts (posts, scored_posts, llm_usage rows), config files present (profile.yaml, projects.yaml, scoring.yaml) | codex | `[ ]` | T61 |
| T63 | Add `report-preview` CLI subcommand: `python3 src/main.py report-preview --week YYYY-Www` — runs format_signal_report() on last 7 days of scored posts and prints to stdout; exits 0 even if no posts | codex | `[ ]` | T62 |
| T64 | Update `README.md` operator section: document all CLI subcommands (score-stats, cost-stats, health-check, report-preview) with one-line description and example output | codex | `[ ]` | T63 |

**Phase 8 Review Criteria**
- `health-check` outputs DB stats and config presence without crashing
- `report-preview` runs end-to-end and prints signal-first report to stdout
- README documents all 4 CLI subcommands
- 77+ tests passing

---

## Roadmap v3 — New Phases

> These phases start after the Phase 0 documentation reset (complete).
> Roadmap v2 (Phases 1–8) is the foundation. Roadmap v3 builds the delivery surface on top.

---

## Phase 1v3 — Weekly Review Artifact Redesign

**Objective:** Replace the current Markdown-blob Telegram output with a structured, readable review artifact as specified in `docs/report_format.md`.

**Why now:** The scoring, routing, and signal-extraction layers are stable. The content exists. The delivery format is the remaining gap between what the system produces and what is actually useful to read.

**Scope:**

In scope:
- Generate the full review artifact as an HTML file (9 sections per `docs/report_format.md`)
- Add source links (`https://t.me/{channel}/{message_id}`) per signal in all sections
- Split delivery: short Telegram notification (executive summary, ≤300 chars) + link to/attachment of full artifact
- Add "What Changed Since Last Week" section (delta vs previous `quality_metrics` row)
- Add "Decisions to Consider" section (populated from strong signals if they have clear action implications — can be static heuristic in v1)
- Add "Project Action Queue" as per-project sub-sections within existing project relevance section

Out of scope:
- Telegraph API integration (Phase 4v3)
- Feedback/taste capture
- Any scoring or routing changes

**Tasks**

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| T65 | Add `message_url` population in ingestion: ensure `raw_posts.message_url` is set to `https://t.me/{channel_username_clean}/{message_id}` for every ingested post | codex | `[ ]` | — |
| T66 | Extend `format_signal_report()` to include source URL per signal entry in Strong, Watch, and Project sections | codex | `[ ]` | T65 |
| T67 | Add "What Changed Since Last Week" section: compare current bucket counts with previous `quality_metrics` row; show delta | codex | `[ ]` | — |
| T68 | Add "Decisions to Consider" section: for each strong signal, if `actionability_score = implement`, emit a decision-style bullet | codex | `[ ]` | — |
| T69 | Add "Project Action Queue": restructure project relevance section into per-project sub-sections | codex | `[ ]` | — |
| T70 | Generate report as HTML file to `data/output/reviews/YYYY-Www.html`; send Telegram notification with executive summary + file attachment | codex | `[ ]` | T66 T67 T68 T69 |

**Validation criteria:**
- report HTML file is generated and contains all 9 sections
- every strong/watch entry has a valid `t.me` source link
- Telegram delivery: notification message ≤ 300 chars; full report attached or linked
- 83+ tests passing

---

## Phase 2v3 — Project Relevance Strengthening

**Objective:** Make the project relevance layer more precise and less prone to false positives.

**Why now:** Current keyword matching is functional but coarse. As the system is used weekly, project relevance false positives are the most common complaint pattern. This phase sharpens it before adding a feedback mechanism.

**Scope:**

In scope:
- Add `project_focus_keywords` as an explicit list (not just a free-text field) in `projects.yaml`
- Update `score_project_relevance()` to use the explicit keyword list with exact match + stemming
- Add negative keywords per project: `exclude_keywords` that suppress relevance even if focus words match
- Expose `project_relevance_score` in the report next to each match with matched keywords shown
- Add test: post with exclude keyword scores < 0.1 despite focus match

Out of scope:
- LLM-based project matching
- cross-project deduplication

**Tasks**

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| T71 | Update `projects.yaml` schema: add `keywords: list[str]` and `exclude_keywords: list[str]` | codex | `[ ]` | — |
| T72 | Update `score_project_relevance()` to use `keywords` list (exact) and apply `exclude_keywords` suppression | codex | `[ ]` | T71 |
| T73 | Show matched keywords and score in report Project section | codex | `[ ]` | T72 |

**Validation criteria:**
- project with `exclude_keywords` does not match posts containing those words
- matched keywords visible in report
- no regression on existing project relevance tests

---

## Phase 3v3 — Taste / Feedback Loop

**Objective:** Allow the owner to mark signals as "acted on" or "skipped" to inform future boost/downrank suggestions.

**Why now:** The current profile.yaml requires manual editing to tune taste. This phase adds a lightweight feedback capture layer so the system can surface tuning suggestions without the owner having to guess.

**Scope:**

In scope:
- Add `signal_feedback` table: `{post_id, feedback (acted_on/skipped/marked_important), recorded_at}`
- Add Telegram bot command `/mark_useful <message_id>` and `/mark_skipped <message_id>` for inline feedback
- Add `python3 src/main.py tune-suggestions` CLI: analyzes signal_feedback, suggests boost/downrank topic additions
- Store feedback; do not auto-apply to profile.yaml (owner applies manually)

Out of scope:
- automatic profile.yaml updates
- ML-based preference learning
- feedback-driven scoring weight adjustment

**Tasks**

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| T74 | Add `signal_feedback` table migration | codex | `[ ]` | — |
| T75 | Add `/mark_useful` and `/mark_skipped` bot commands in `handlers.py` | codex | `[ ]` | T74 |
| T76 | Add `tune-suggestions` CLI: show topics that frequently appear in acted-on signals but are not in boost list | codex | `[ ]` | T74 |

**Validation criteria:**
- feedback stored in DB after bot command
- `tune-suggestions` shows non-empty output when feedback exists
- no auto-modifications to profile.yaml

---

## Phase 4v3 — Article-Style Delivery Surface

**Objective:** Deliver the weekly review as a Telegraph article readable inside Telegram with Instant View.

**Why now:** HTML file attachment is a functional but clunky delivery. Telegraph articles are the cleanest reading experience inside Telegram — full-screen, scrollable, source links inline.

**Scope:**

In scope:
- Publish weekly HTML review to Telegraph via the Telegraph API
- Send Telegram notification with Telegraph article URL instead of file attachment
- Telegraph article title: "Research Review — YYYY-Www"
- Fallback: if Telegraph API unavailable, send HTML file attachment (existing Phase 1v3 behavior)

Out of scope:
- custom domain for articles
- article editing / version history
- multi-article archives

**Tasks**

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| T77 | Add `src/delivery/telegraph.py` with `publish_article(title, html_content) -> str` returning article URL | codex | `[ ]` | T70 |
| T78 | Wire `telegraph.py` into digest delivery: publish → get URL → send Telegram notification with URL | codex | `[ ]` | T77 |
| T79 | Add fallback: if Telegraph publish fails, attach HTML file (existing behavior) | codex | `[ ]` | T78 |

**Validation criteria:**
- `publish_article()` returns a valid URL
- Telegram notification contains the article URL
- fallback to file attachment works when Telegraph API unavailable

---

## Phase 5v3 — Observability and Polish

**Objective:** Make the system's behavior visible and trustworthy over long-term use.

**Scope:**

In scope:
- Weekly `cost-per-run` trend in `cost-stats` CLI (last 4 runs comparison)
- `score-stats` shows trend vs previous week
- Add `cluster_coherence` score per post (currently hardcoded 0.5) using actual silhouette score from `cluster_runs`
- Expand `health-check` to include last run timestamp, last digest week, any stuck queues

Out of scope:
- dashboards
- external monitoring integrations

---

## Phase Priority Rationale

| Phase | Why this order |
|---|---|
| 1v3 — Report redesign | Content quality exists; delivery gap is the bottleneck for weekly value |
| 2v3 — Project relevance | Most common false-positive source; fix before adding feedback |
| 3v3 — Feedback loop | Can only be meaningful after delivery is good enough to generate real reactions |
| 4v3 — Telegraph delivery | Polish on top of working content; don't polish before content is right |
| 5v3 — Observability | Ongoing; no hard dependency, can run in parallel with Phase 4v3 |

---

## 3. Phase Priorities

### Must happen first

- Phase 1: baseline stabilization
- Phase 2: scoring foundation
- Phase 3: model routing

Reason:
- routing needs scoring
- personalization needs both scoring and routing
- output redesign is cheaper and safer after routing contracts exist

### Can wait

- deep learning-layer refinement
- broader product surface improvements
- advanced user preference memory

### Optional after core value appears

- richer UI surfaces beyond Telegram/files
- advanced feedback loops for taste adaptation
- aggressive automation around learning plans

### Dangerous to do too early

- personalization before stable scoring
- multi-surface productization before signal-first output is proven
- complex routing before instrumentation exists
- over-engineered project relevance before core signal quality is reliable

---

## 4. Development Workflow Integration

Target workflow:

```text
Strategist -> Orchestrator -> Codex -> Review -> Fixes
```

### Strategist produces per phase

- phase brief with exact scope
- updated architecture deltas
- implementation constraints
- success criteria and quality gates
- non-goals and stop conditions

### Orchestrator produces

- current-phase selection
- dependency check
- concrete task packet for Codex
- review packet for reviewer
- phase completion state update

### Codex task split

Codex should receive:
- one epic at a time
- small sub-epics with explicit file ownership
- task units that can be reviewed in isolation

Codex should not receive:
- an entire multi-phase implementation in one pass
- tasks that mix architecture redesign with broad refactor and product polish

### Review checks required

- architecture adherence
- contract adherence
- routing policy correctness
- output format correctness
- metrics and observability coverage
- regression risk against prior phase success criteria

### STOP conditions

Do not proceed to the next phase if any of the following is true:
- entry metrics for the current phase were not captured
- review found unresolved contract violations
- docs and implementation disagree on output or routing behavior
- strong-tier escalation is not measurable
- cost impact is unknown
- personalization logic is introduced before project relevance quality is acceptable

---

## 5. Task Decomposition Model

### Hierarchy

- `Epic`: one phase-level capability, for example "model routing"
- `Sub-epic`: one coherent slice, for example "tier policy", "routing metrics", "prompt segregation"
- `Task unit`: one reviewable implementation change, ideally touching a narrow file set

### Ideal task size

Task units should be:
- completable in one focused implementation pass
- reviewable without loading the whole repo
- narrow enough to have explicit acceptance criteria

Practical rule:
- 1 capability
- 1 clear contract
- 1 bounded test/eval surface

### How to avoid giant implementation

- do not combine routing, output redesign, and personalization in one task
- separate data-contract changes from presentation changes
- create task units around interfaces, not around "make feature X fully done"
- require each sub-epic to have its own quality gate

### Clarity rule

If a task cannot be reviewed without re-reading multiple phases of context, it is too large and must be split.

---

## 6. Documentation Updates

The following documents must stay aligned with each phase.

### 1. `README.md`

What must change:
- product framing from digest bot to personal intelligence system
- target output framing
- development priorities

Why it matters:
- the README sets the mental model for every future contributor and tool invocation

### 2. `docs/architecture.md`

What must change:
- new layers: routing, personalization, updated output, observability
- sequencing constraints
- rationale for each layer

Why it matters:
- Codex and reviewers need a stable structural contract

### 3. Prompt templates in `docs/prompts/`

What must change:
- scoring prompts and rubrics must align with signal taxonomy
- routing prompts must distinguish cheap/mid/strong tasks
- output prompts must enforce signal-first structure

Why it matters:
- prompt contracts are part of system behavior, not documentation garnish

### 4. Orchestrator docs

What must change:
- phase order
- dependency checks
- phase handoff contracts
- stop conditions

Why it matters:
- the workflow must enforce sequencing, not just describe it

### 5. Review checklists

What must change:
- routing validation
- cost validation
- output-section validation
- personalization guardrails

Why it matters:
- review must catch product regressions, not just syntax or style issues

### 6. Evaluation / metrics docs

What must change:
- routing metrics
- signal density
- relevance quality
- personalization effect and cost-per-run

Why it matters:
- without metrics the new architecture cannot be tuned or trusted

### 7. Example outputs

What must change:
- move from digest examples to signal-first examples
- show ignored/noise handling explicitly
- separate project relevance from general importance

Why it matters:
- examples train reviewers, future prompt changes, and operator expectations

---

## 7. Evaluation & Quality Gates

### Phase 1

Good:
- baseline run is reproducible
- docs and current behavior match

Failure:
- team cannot explain what the current system actually does

### Phase 2

Good:
- strong bucket is selective
- weak/noise split is stable

Failure:
- most posts look "important"
- scores swing heavily between runs

### Phase 3

Good:
- only a minority of items reach `STRONG`
- cost per run is bounded and explainable

Failure:
- strong tier becomes default path
- routing decisions cannot be audited

Suggested metrics:
- `% items escalated to STRONG`
- `% items handled by CHEAP only`
- `cost per weekly run`

### Phase 4

Good:
- report can be scanned quickly
- strong signals dominate attention

Failure:
- report reads like a reformatted digest
- ignored section is absent or useless

Suggested metrics:
- `output readability review`
- `signal density`
- `section completeness`

### Phase 5

Good:
- project matches are fewer and sharper

Failure:
- project section is padded with vague matches

Suggested metrics:
- `precision of project matches`
- `false-positive review rate`

### Phase 6

Good:
- personalization changes ranking meaningfully and explainably

Failure:
- ranking feels arbitrary
- system simply mirrors recent clicks/interests without evidence

Suggested metrics:
- `personalized relevance delta`
- `downrank accuracy`
- `diversity retention`

### Phase 7

Good:
- learning guidance points to durable gaps

Failure:
- recommendations are generic or hype-driven

Suggested metrics:
- `learning actionability`
- `repeat-topic rate`

### Phase 8

Good:
- operators can run, inspect, and trust the system

Failure:
- product surface hides core metrics or makes triage harder

Suggested metrics:
- `operator setup success`
- `surface clarity`

---

## 8. Risk Analysis

### Overengineering routing

Risk:
- too many branches and thresholds before baseline metrics exist

Mitigation:
- start with a small, transparent tier policy
- require routing dashboards before adding nuance

### Fake personalization

Risk:
- "personalized" output is just noisy boosts and suppressions

Mitigation:
- personalization may re-rank, not replace signal quality
- require explainable preference effects

### Weak signal detection

Risk:
- weak signals get promoted because heuristics are loose

Mitigation:
- keep strong bucket selective
- review borderline samples explicitly

### Verbose output

Risk:
- signal-first format degenerates into another long digest

Mitigation:
- cap output by section
- review for scan time, not just completeness

### Breaking simplicity

Risk:
- each improvement adds a new subsystem without preserving operator clarity

Mitigation:
- each phase must reduce ambiguity, not add hidden logic
- productization happens last

### Losing product clarity

Risk:
- system tries to be digest, analyst, coach, and dashboard at once

Mitigation:
- keep the core promise narrow: filter signals, tie them to projects, guide learning

---

## 9. Updated Roadmap

| Order | Phase | Depends On | Expected Outcome | Product Value |
|---|---|---|---|---|
| 1 | Baseline stabilization | — | reliable baseline, aligned docs, measurable current state | low but essential |
| 2 | Scoring foundation | 1 | trustworthy signal buckets | early internal value |
| 3 | Model routing | 2 | cost-aware execution path | strong internal leverage |
| 4 | Signal-first output | 3 | decision-support report replaces digest | first visible product shift |
| 5 | Project relevance upgrade | 3, 4 | stronger project-specific prioritization | major user-facing value |
| 6 | Personalization / taste model | 2, 3, 5 | user-aware ranking and filtering | major differentiated value |
| 7 | Learning layer refinement | 4, 5, 6 | strategic study guidance | compounding value |
| 8 | Productization / surface layer | 1-7 | stable delivery and operator experience | packaging and scale readiness |

Where real product value appears:
- first clearly in Phase 4
- substantially in Phase 5
- differentiated and durable in Phase 6

---

## 10. Orchestrator Handoff

### What Codex should implement first

- Phase 1 baseline stabilization tasks
- metrics capture for current scoring/output behavior
- documentation-aligned contracts for scoring and output

### What must NOT be touched yet

- deep personalization logic
- advanced feedback learning loops
- major UI/surface expansion
- overly complex routing heuristics before Phase 3 entry criteria are met

### What to validate before moving forward

Before Phase 2:
- baseline metrics captured
- docs aligned with current system

Before Phase 3:
- scoring buckets stable and reviewable

Before Phase 4:
- routing tiers measurable and cost-aware

Before Phase 5:
- signal-first output works without personalization

Before Phase 6:
- project relevance has acceptable precision

Before Phase 7:
- personalization changes are explainable and non-destructive

Before Phase 8:
- output, routing, relevance, and personalization all have quality gates

---

## Immediate Next Step

The next implementation packet should cover only:
- baseline stabilization
- measurement setup
- document and prompt contract cleanup required for the new roadmap

It should not attempt routing, signal-first output, and personalization in one pass.
