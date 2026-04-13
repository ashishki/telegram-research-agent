# Architecture

**Version:** 6.1
**Date:** 2026-04-13

---

## System Role

`telegram-research-agent` is a private, single-user research intelligence pipeline. It ingests Telegram channels, scores signals deterministically, and produces weekly decision-support artifacts for active projects.

Its architecture is intentionally local-first, SQLite-first, and scoped to one operator. It is not a general memory platform.

---

## Current Architectural Shape

```text
Telegram ingestion
  -> normalization + topic assignment
  -> deterministic scoring + project relevance
  -> explicit feedback + manual tags
  -> evidence recording (signal_evidence_items)
  -> weekly outputs (brief / ideas / study)
  -> decision journal (decision_journal)

Cross-cutting:
  project snapshots
  channel memory + dynamic channel_score
  scope-first evidence retrieval
  cost + health observability
  memory CLI inspection
```

What the system provides:

- canonical post storage and scoring
- explicit preference capture
- dynamic per-channel preference with time decay blended into source scoring
- project-aware outputs
- rejection memory for weak implementation ideas
- stricter implementation-idea selection: unique source usage, fewer stronger items, preference for current-project improvements
- verbatim evidence layer: `signal_evidence_items` records curated post excerpts with provenance per week and project scope
- decision continuity: `decision_journal` unifies signal feedback, insight triage, and study completion in one append-only log
- scope-first retrieval: all weekly generators query by project → week → source before broader fallback

---

## Memory Architecture

The active design is defined in [`docs/memory_architecture.md`](/home/ashishki/Documents/dev/ai-stack/projects/telegram-research-agent/docs/memory_architecture.md).

High-level contracts:

### 1. Canonical operational state

Stored in SQLite and treated as source of truth:

- raw Telegram posts
- normalized/scored posts
- topic/project links
- explicit feedback and tags
- weekly artifact records
- triage and rejection records

### 2. Derived snapshots

Refreshable working context:

- `channel_memory` including a dynamic `channel_score` and weighted feedback strength
- project snapshots from config + GitHub deltas + linked signals

These are bounded summaries, not canonical facts.

### 3. Verbatim evidence memory

Implemented as `signal_evidence_items`:

- selected high-value post excerpts with provenance (source channel, Telegram link, selection reason, week label, project scope)
- written during scoring (`record_signal_evidence_for_scored_posts`) and manual tagging (`record_signal_evidence_for_manual_tag`)
- retrieved by scope before any broad search; `fetch_evidence_items` supports project, week, source, kind, and exclude-by-status filters

### 4. Decision continuity

Implemented as `decision_journal`:

- acted-on / ignored / deferred / rejected / completed history with links to project scope
- signal feedback writes via `record_decision_for_feedback`
- insight triage writes via `record_decisions_for_triage`
- study-plan completion writes via `record_study_completion_decision`
- unified continuity across all decision types; used by recommendations and study-plan generators to suppress repeated ideas

---

## Retrieval Policy

Retrieval must be **scope-first**:

1. narrow by project
2. narrow by topic
3. narrow by time window
4. narrow by source channel
5. narrow by decision state
6. only then fall back to broader search

This is the main MemPalace idea worth adopting here. A flat global memory pool is the wrong fit for this product.

---

## Storage Boundaries

### Keep structured and canonical

- tables that drive scoring, routing, project relevance, feedback, and weekly outputs

### Keep derived and bounded

- channel summaries
- project snapshots
- weekly digest/report summaries

### Implemented (Phases 1–4)

- `signal_evidence_items` — Tier 3 verbatim evidence memory
- `decision_journal` — Tier 4 decision continuity

### Explicitly out of scope

- palace metaphor layers
- global temporal knowledge graph
- diary systems
- custom compression dialects
- generic multi-agent memory platform

---

## Build Order (Completed)

Memory unification was implemented in four phases (M1–M17):

1. **Phase 1 — Contract** (M1–M5): memory schema design, retrieval contract, debug/eval spec
2. **Phase 2 — MVP Tables** (M6–M10): `signal_evidence_items` and `decision_journal` migrations, retrieval helpers, evidence writers, feedback integration
3. **Phase 3 — Wire into Outputs** (M11–M14): preference judge evidence injection, recommendations context, study plan acted-on evidence, signal report channel attribution
4. **Phase 4 — Observability** (M15–M17): retrieval tests, evidence writer tests, memory CLI inspection subcommands

All 167 tests pass. All four memory surfaces are live.

---

## Observability Requirements

The operator must be able to answer:

- why was this signal surfaced?
- what evidence was used?
- what project/time/source scope was applied?
- why did this idea reappear or stay suppressed?

If the system cannot answer those questions from stored state, the memory design is too vague.
