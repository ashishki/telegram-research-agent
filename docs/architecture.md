# Architecture

**Version:** 5.0
**Date:** 2026-04-07

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
  -> weekly outputs (brief / ideas / study)

Cross-cutting:
  project snapshots
  channel memory
  cost + health observability
```

What already works:

- canonical post storage and scoring
- explicit preference capture
- project-aware outputs
- rejection memory for weak implementation ideas

What was missing before this planning reset:

- one coherent memory architecture spanning signals, evidence, feedback, and decisions

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

- `channel_memory`
- project snapshots from config + GitHub deltas + linked signals

These are bounded summaries, not canonical facts.

### 3. Verbatim evidence memory

New planned layer:

- selected high-value post excerpts with provenance
- stored only for items worth resurfacing
- retrieved by scope before any broad search

### 4. Decision continuity

New planned layer:

- acted-on / ignored / deferred / rejected history with links to evidence and project scope

This is the missing architectural glue between feedback, triage, and weekly recommendations.

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

### Add in MVP

- `signal_evidence_items`
- `decision_journal`

### Explicitly out of scope

- palace metaphor layers
- global temporal knowledge graph
- diary systems
- custom compression dialects
- generic multi-agent memory platform

---

## Build Order Constraint

The next implementation order is strict:

1. memory schema and retrieval contract
2. MVP memory unification tables and helpers
3. integrate weekly generators with the new retrieval path
4. add observability and evaluation

Prompt work without these storage contracts will just deepen the current fragmentation.

---

## Observability Requirements

The operator must be able to answer:

- why was this signal surfaced?
- what evidence was used?
- what project/time/source scope was applied?
- why did this idea reappear or stay suppressed?

If the system cannot answer those questions from stored state, the memory design is too vague.
