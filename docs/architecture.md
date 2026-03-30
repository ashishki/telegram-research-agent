# Telegram Research Agent — Architecture

**Version:** 2.0.0
**Date:** 2026-03-30
**Status:** Strategic redesign aligned

---

## Overview

This system is no longer defined as a digest bot.

It is a personal intelligence system that:
- filters noisy Telegram flow into ranked signals
- estimates which signals matter for active projects
- adapts ranking to the user's evolving taste
- produces compact decision-support output instead of a generic summary

This document is the high-level architecture contract for future implementation phases.

---

## What Changed

Previous center of gravity:
- ingest posts
- cluster topics
- generate digest

New center of gravity:
- ingest posts
- score and rank them deterministically
- route only selected items to appropriate model tiers
- interpret them through a project and personal lens
- emit signal-first output with explicit discard handling

Three structural additions drive the redesign:
- `Routing layer`: required to make model usage conditional and cost-aware
- `Personalization layer`: required to make prioritization user-specific rather than generic
- `Updated output layer`: required to convert analysis into action-support instead of information dump

---

## Component Map

```text
Telegram Sources
  ->
Ingestion Layer
  ->
Preprocessing Layer
  ->
Scoring Layer
  ->
Routing Layer
  ->
Interpretation Layer
  ->
Project Lens
  ->
Learning Layer
  ->
Output Layer
  ->
Telegram / Files / Future UI

Cross-cutting:
  Personalization Layer
  Observability Layer
```

---

## Layer Definitions

### 1. Ingestion Layer

Purpose:
- retrieve raw Telegram messages
- preserve source metadata
- write immutable raw records

Why it stays separate:
- reliability and idempotency rules belong here
- ingestion must remain independent from any model usage

Core outputs:
- raw post content
- source/channel metadata
- stable message identifiers and URLs

---

### 2. Preprocessing Layer

Purpose:
- normalize text
- derive lightweight metadata
- prepare posts for scoring and matching

Responsibilities:
- cleanup and normalization
- language detection
- metadata extraction
- topic preparation and cluster support

Why it is required:
- routing and personalization need structured, comparable inputs
- this layer keeps later decisions reproducible and cheap

Constraint:
- no expensive interpretation should happen here

---

### 3. Scoring Layer

Purpose:
- produce the first reliable estimate of signal value before any expensive model call

Responsibilities:
- deterministic scoring dimensions
- source quality weighting
- novelty / actionability heuristics
- preliminary strong/weak/noise segmentation

Why it is required:
- model routing without scoring is blind
- personalization without scoring overfits preferences onto noise

This is now the foundation layer for all later reasoning.

Implementation:
- `src/processing/score_posts.py` — deterministic scoring engine; writes `signal_score`, `bucket`, `project_matches`, `interpretation` to the `posts` table
- Configuration surface: `src/config/scoring.yaml` (scoring weights and thresholds), `src/config/profile.yaml` (per-user boost/downrank rules)

---

### 4. Routing Layer

Purpose:
- decide whether a post should be ignored, processed cheaply, escalated to a mid-tier model, or sent to a strong model

Responsibilities:
- `CHEAP / MID / STRONG` tier mapping
- conditional execution
- batch selection
- budget enforcement
- fallback behavior when confidence is low or cost budget is near limit

Why it is new:
- the old system assumed synthesis first
- the new system requires most items to die early, cheaply

Without routing:
- cost scales with volume
- strong models see too much low-value material
- output quality degrades because interpretation attention is wasted on noise

Implementation:
- `src/llm/router.py` — `route(task_type, signal_score)` selects model tier; thresholds: `WATCH_THRESHOLD=0.45` (CHEAP→MID), `STRONG_THRESHOLD=0.75` (MID→STRONG); `task_type="synthesis"` always routes to STRONG_MODEL
- Note: per-post score-based routing (`route(signal_score=score)`) is implemented but not yet wired to any production call site. This is Phase 3 pre-wiring scaffolding. Only `route("synthesis")` is active in production (`src/output/generate_digest.py`)
- LLM calls are made via the `anthropic` SDK through `src/llm/client.py`; `client.py` records usage per call to the `llm_usage` table via `_record_usage()`, with cost estimated via `router.estimate_cost_usd()`

---

### 5. Interpretation Layer

Purpose:
- convert routed items into concise semantic judgments

Responsibilities:
- explain why a signal matters
- summarize implications
- generate structured evidence objects, not free-form prose only

Why it is required:
- scoring tells us that something might matter
- interpretation explains what it means

Constraint:
- interpretation only runs on routed subsets, never on the full corpus

---

### 6. Project Lens

Purpose:
- estimate relevance to active projects and initiatives

Responsibilities:
- project matching
- relevance tiering
- rationale generation
- separation between generally important signals and project-specific signals

Why it is required:
- users do not need "important in general"
- they need "important for what I am building"

Dependency:
- depends on scoring and routing being stable enough to avoid drowning projects in false positives

---

### 7. Learning Layer

Purpose:
- turn repeated or strategically important signals into guided learning actions

Responsibilities:
- detect durable knowledge gaps
- suggest study directions
- connect signals to explicit learning objectives

Why it remains downstream:
- learning should be informed by validated signals and project relevance
- otherwise the system recommends studying whatever was merely noisy but recent

---

### 8. Output Layer

Purpose:
- package intelligence in a signal-first structure

Target output structure:
- `Strong signals`
- `Project relevance`
- `Weak signals`
- `Think layer`
- `Light / cultural`
- `Ignored`

Why it changed:
- digest-style output optimizes readability but not actionability
- the new output must make triage obvious, including what was intentionally discarded

Key principle:
- the system should surface decisions, not just summaries

---

### 9. Personalization Layer

Purpose:
- adapt scoring, routing, ranking, and output ordering to the user's taste and strategic focus

Responsibilities:
- maintain user profile
- encode interests and anti-interests
- keep preference memory
- apply downranking and boosting rules

Why it is new:
- a generic intelligence feed is not a personal system
- two users can see the same corpus and need different outputs

Constraint:
- personalization must modulate the system, not replace evidence
- it cannot overrule basic signal quality or create fake relevance

---

### 10. Observability Layer

Purpose:
- make every phase measurable and reviewable

Responsibilities:
- cost per run
- routing distribution
- escalation rate to strong models
- signal density
- output length and structure checks
- relevance and personalization diagnostics

Why it is required:
- routing and personalization are unsafe without feedback loops
- cost-aware systems fail silently if metrics are absent

---

## Data Model

### New tables (added Phase 1 / T33–T34)

| Table | Key columns | Purpose |
|---|---|---|
| `llm_usage` | `called_at`, `category`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `duration_ms` | Per-call LLM usage and cost tracking; written by `src/llm/client.py:_record_usage()` |
| `quality_metrics` | `week_label`, `total_posts`, `strong_count`, `watch_count`, `cultural_count`, `noise_count`, `avg_signal_score`, `project_match_count`, `output_word_count` | Per-run digest quality observability; written by `src/output/generate_digest.py:_store_quality_metrics()` in both early-exit and normal paths |
| `cluster_runs` | `run_at`, `post_count`, `cluster_count`, `unlabeled_count`, `inertia`, `silhouette_score` | Clustering run metadata and global silhouette score; written by `src/processing/cluster.py` |
| `study_plans` | `week_label`, `generated_at`, `content_md`, `topics_covered`, `reminder_sent_tue`, `reminder_sent_fri` | Generated study plans with reminder delivery state |

### New columns on existing tables (added Phase 1)

| Table | New columns | Purpose |
|---|---|---|
| `posts` | `signal_score REAL`, `bucket TEXT`, `project_matches TEXT`, `interpretation TEXT` | Scoring engine output; written by `src/processing/score_posts.py` |
| `post_project_links` | `tier TEXT`, `rationale TEXT` | Project relevance inference tier and reasoning |
| `raw_posts` | `message_url TEXT`, `image_description TEXT` | Stable message URL (`https://t.me/{channel}/{id}`) and LLM vision analysis output |

---

## Architectural Sequencing Rules

The build order is strict:
1. Baseline stabilization
2. Scoring foundation
3. Routing layer
4. Signal-first output
5. Project relevance upgrade
6. Personalization
7. Learning refinement
8. Productization

Rules:
- routing must not be introduced before scoring is measurable
- personalization must not be introduced before routing and project relevance are stable
- product surface work must not outrun output quality

---

## Design Constraints

- Expensive models must only see filtered subsets
- Output must preserve a visible ignored/noise decision
- Personalization must be auditable
- Project relevance must remain separable from general importance
- Every phase must define success metrics before implementation starts

---

## Required Documentation Alignment

Any implementation change that affects this architecture must also update:
- `README.md`
- `docs/spec.md`
- `docs/tasks.md`
- `docs/dev-cycle.md`
- relevant prompt docs in `docs/prompts/`
- review and evaluation checklists

No phase is considered complete while architecture and execution docs disagree.
