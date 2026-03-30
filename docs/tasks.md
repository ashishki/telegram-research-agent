# Telegram Research Agent — Strategic Roadmap v2

**Version:** 2.0.0
**Date:** 2026-03-30
**Status:** Strategic redesign integrated

---

## Purpose

This document is the execution roadmap for subsequent development.

It replaces the older feature-by-feature build order with a dependency-aware plan aligned to the new product definition:
- personal intelligence system
- cost-aware model routing
- signal-first output
- user-aware prioritization

This is a planning document, not a code task checklist.

Legacy delivery phases remain part of project history, but they are no longer the active execution model.
Current execution follows `Strategic Roadmap v2` below.

---

## Current Execution State

- `Roadmap version`: v2
- `Current phase`: Phase 1 — Baseline Stabilization
- `Status`: ready for bounded implementation packet
- `Primary blocker`: current CI/CD issue must be treated as a baseline blocker inside Phase 1
- `Do not start yet`: Phase 2+ work, deep personalization, broad surface changes

### Legacy Bridge

- `Legacy phases 1–20`: implementation history and audit trail
- `Roadmap v2 phases 1–8`: current strategic execution sequence

Rule:
- when docs mention old phases, treat them as historical context only
- when orchestrating new work, use `Roadmap v2` numbering only

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
