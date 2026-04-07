# Telegram Research Agent — Execution Roadmap

**Version:** 5.0
**Date:** 2026-04-07
**Status:** Documentation-aligned planning reset

---

## Current Status

The repository already has a working end-to-end weekly pipeline:

- Telegram ingestion and normalized post storage
- deterministic scoring and bucket assignment
- project relevance scoring
- manual feedback and explicit tagging
- derived channel memory and project context snapshots
- weekly research brief, implementation ideas, and study plan generation
- rejection memory for weak implementation ideas

What it does **not** yet have is one coherent memory architecture.

Today the system behaves as several adjacent memory surfaces:

- canonical operational state in SQLite
- derived snapshot text used in prompts
- manual preference and feedback data
- rejection suppression for implementation ideas
- raw post text stored in `raw_posts` but not retrieved as a first-class evidence layer

That fragmentation is now the main architecture issue. The next roadmap focuses on **memory unification for decision support**, not on adding a generic memory platform.

Authoritative design document: `docs/memory_architecture.md`

---

## Planning Principles

- Structured state stays canonical when downstream logic depends on it.
- Summaries are working context, not source of truth.
- Verbatim evidence is stored only where the “why” matters.
- Retrieval must narrow by scope before any broad search.
- Project and time boundaries matter more than global semantic recall.
- Decision continuity matters as much as content continuity.
- The MVP must stay local-first, private, debuggable, and cheap.
- No decorative “palace” abstractions in this repo.

---

## Phase 0 — Planning Reset

**Status:** Complete in this change set.

Deliverables:

- current-state assessment captured in `docs/memory_architecture.md`
- MemPalace extraction and adopt/reject decisions documented
- target memory architecture defined for this repo
- active roadmap rewritten around memory unification
- AI workflow handoff updated to the new execution order

---

## Phase 1 — Memory Contract And Inventory

**Goal**

Define the schema boundaries, retrieval contract, and migration rules before adding new memory behavior.

**What this phase implements**

- explicit ownership map for current memory/state tables and derived artifacts
- retrieval contract for project/topic/time/source scoped lookups
- schema design for `signal_evidence_items` and `decision_journal`
- evolution plan for `project_context_snapshots` into a canonical project snapshot surface
- operator/debug contract for inspecting why an item was retrieved

**What this phase does not implement**

- no new production retrieval yet
- no prompt rewrites beyond adding placeholders for the upcoming surfaces
- no embeddings or generic memory engine

**Dependencies**

- Phase 0

**Success criteria**

- every memory surface has a declared owner and refresh rule
- new tables/entities are defined before migration work begins
- the first implementation phase can proceed without reinterpreting architecture

**Tasks**

| ID | Task | Status | Depends On |
|---|---|---|---|
| M1 | Document current canonical vs derived vs missing memory surfaces in `docs/memory_architecture.md` | `[x]` | — |
| M2 | Define retrieval flow and scoping policy in `docs/architecture.md` and `docs/IMPLEMENTATION_CONTRACT.md` | `[x]` | M1 |
| M3 | Define target schemas for `signal_evidence_items`, `decision_journal`, and evolved project snapshots | `[ ]` | M2 |
| M4 | Add migration notes: how existing `channel_memory`, `project_context_snapshots`, `signal_feedback`, and triage tables map into the new model | `[ ]` | M3 |
| M5 | Define debug/eval requirements for retrieval inspection and report usefulness checks | `[ ]` | M2 |

---

## Phase 2 — MVP Memory Unification

**Goal**

Introduce the minimum new storage needed to unify continuity across signals, projects, feedback, and decisions.

**What this phase implements**

- `signal_evidence_items` table storing scoped verbatim excerpts with provenance
- `decision_journal` table for acted-on / ignored / deferred / rejected continuity
- project snapshot refresh rules that preserve structured project state plus bounded textual snapshot
- deterministic retrieval helpers for scope-first evidence lookup

**What this phase does not implement**

- no cross-project semantic graph
- no generalized conversation memory system
- no automatic preference model beyond current explicit-tag logic

**Dependencies**

- Phase 1

**Success criteria**

- high-value weekly signals can be traced through a stable evidence surface
- decisions and rejections can be looked up with provenance and dates
- prompt builders can request scoped memory without scraping unrelated tables

**Tasks**

| ID | Task | Status | Depends On |
|---|---|---|---|
| M6 | Add DB migrations for `signal_evidence_items` and `decision_journal` | `[ ]` | M4 |
| M7 | Populate evidence items from strong/watch posts, explicit tags, and triaged insights with source provenance | `[ ]` | M6 |
| M8 | Write decision-journal rows from feedback actions and insight triage outcomes | `[ ]` | M6 |
| M9 | Add retrieval helpers that filter by project, topic, week range, source channel, and status before fallback search | `[ ]` | M7 M8 |
| M10 | Add CLI/debug output to inspect scoped evidence and recent decision history | `[ ]` | M9 |

---

## Phase 3 — Wire Memory Into Weekly Outputs

**Goal**

Make the weekly brief, implementation ideas, and study loop use the unified memory model rather than loosely assembled prompt context.

**What this phase implements**

- preference judge context assembled from scoped evidence and project snapshots
- implementation ideas generation conditioned on recent decisions and rejection history
- study plan generation conditioned on project snapshot plus acted-on evidence
- provenance-forward rendering improvements where evidence matters

**What this phase does not implement**

- no UI beyond current Telegram/Telegraph/file outputs
- no speculative “agent diary” system

**Dependencies**

- Phase 2

**Success criteria**

- repeated weak ideas are suppressed for explicit reasons
- project-specific recommendations cite recent evidence rather than generic focus text
- weekly outputs preserve source, time, and decision continuity more reliably

**Tasks**

| ID | Task | Status | Depends On |
|---|---|---|---|
| M11 | Replace ad hoc prompt context assembly in `preference_judge.py` with scoped retrieval helpers | `[ ]` | M9 |
| M12 | Update recommendations generation to consult `decision_journal` and evidence items before surfacing ideas | `[ ]` | M8 M9 |
| M13 | Update study-plan generation to use project snapshots plus recent acted-on evidence | `[ ]` | M7 M9 |
| M14 | Improve report sections to preserve concise provenance where evidence is materially important | `[ ]` | M11 |

---

## Phase 4 — Observability And Evaluation

**Goal**

Measure whether the new memory architecture improves retrieval precision and weekly usefulness without turning into invisible prompt complexity.

**What this phase implements**

- retrieval inspection CLI/tests
- fixture-based evals for scoped recall and rejection suppression
- report usefulness checklist grounded in evidence provenance and decision continuity
- documentation for operator debugging

**Dependencies**

- Phase 3

**Success criteria**

- retrieval outputs can be inspected by scope and reason
- new memory behavior has tests beyond “prompt didn’t crash”
- operator can understand why an item resurfaced or stayed suppressed

**Tasks**

| ID | Task | Status | Depends On |
|---|---|---|---|
| M15 | Add tests for scoped retrieval precision and provenance completeness | `[ ]` | M14 |
| M16 | Add tests for decision continuity: acted-on, skipped, deferred, and rejected flows | `[ ]` | M12 |
| M17 | Add CLI/operator docs for memory inspection and weekly troubleshooting | `[ ]` | M10 M15 |

---

## Later, If Needed

These are explicitly deferred until the MVP memory architecture proves useful:

- evidence-only FTS or vector search across `signal_evidence_items`
- cross-project linking beyond explicit project/topic overlap
- automated preference summarization beyond current explicit tags and channel bias
- knowledge-graph style entities and temporal triples
- generic memory MCP layer
- compression dialects or wake-up context formats

---

## First Recommended Implementation Phase

Start with **Phase 1 — Memory Contract And Inventory** and execute in this order:

1. M3 — finalize schema design for evidence items, decision journal, and project snapshots
2. M4 — document migration mapping from current tables
3. M5 — define debug/eval contract

That is the smallest next step that reduces ambiguity without committing the repo to premature implementation complexity.
