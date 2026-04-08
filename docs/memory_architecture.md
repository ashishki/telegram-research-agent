# Memory Architecture Decision

**Version:** 2.0
**Date:** 2026-04-08
**Status:** Implemented — all four phases complete (M1–M17)

---

## Architectural Verdict

`telegram-research-agent` already has meaningful persistence. Its problem is not “no memory.” Its problem is that memory is split across scoring state, feedback state, derived snapshots, and output-specific prompt assembly.

The right move is **not** a generic memory platform.

The right move is:

- keep structured operational state in SQLite
- add a small verbatim evidence layer for high-value Telegram signals
- add a decision journal for acted-on / ignored / deferred / rejected continuity
- make retrieval scope-first by project, topic, time, and source
- keep summaries bounded and derived

This repo needs **memory unification**, not memory maximalism.

---

## Verified Current State

### What already exists

**Canonical operational state**

- `raw_posts`: immutable Telegram source text plus source metadata and `message_url`
- `posts`: normalized/scored post state
- `post_topics`, `topics`: cluster-derived topical indexing
- `post_project_links` and `project_relevance_score`: project matching state
- `signal_feedback`: acted_on / skipped feedback events
- `user_post_tags`: explicit ranking and preference tags
- `insight_triage_records` and `insight_rejection_memory`: implementation-idea continuity
- `study_plans`, `digests`, `recommendations`: generated weekly artifacts

**Derived memory surfaces**

- `channel_memory`: summary and counters derived from explicit post tags
- `project_context_snapshots`: project summary text plus recent commit messages
- `user_preference_score` and `user_adjusted_score`: derived ranking state

**Current retrieval-like behavior**

- project relevance uses deterministic keyword overlap, not a memory retrieval layer
- preference judge loads recent tagged examples, derived channel memory, and project snapshots
- recommendations and study-plan generation load digest summaries and project snapshots
- there is FTS over `posts.content`, but no dedicated evidence retrieval layer

### What is strong already

- provenance is partially present: Telegram links, channel names, dates, project ids
- explicit user feedback is preserved, not hidden inside a model
- rejection continuity already exists for implementation ideas
- local-first SQLite architecture is a good fit for the product

### Where continuity is too lossy

- raw Telegram text exists, but the system does not preserve a curated “why this mattered” evidence layer
- weekly generation relies on prompt assembly from several disconnected tables
- project snapshots are text-heavy and useful, but they are not clearly positioned as bounded derived state versus canonical state
- acted-on / skipped feedback is not unified with implementation-idea triage outcomes into one decision history
- there is no shared retrieval contract for project/topic/time/source scoped context assembly

### Where docs were stale or misleading

- `docs/tasks.md` was still dominated by historical roadmap phases rather than the actual next architectural bottleneck
- `docs/CODEX_PROMPT.md` still pointed to obsolete next tasks
- several docs described “memory” features but did not distinguish canonical state from derived summaries

---

## What This Repo Should Store

### Structured canonical state

Keep as source of truth:

- raw Telegram posts and normalized posts
- topic assignments and project links
- explicit user tags and feedback events
- triage outcomes and rejection suppression records
- generated artifact records

This state is deterministic or user-authored. Downstream logic depends on it. It should remain canonical.

### Bounded summaries and snapshots

Keep, but treat as derived and refreshable:

- `channel_memory`
- project snapshots derived from config + GitHub deltas + linked signal counts
- weekly digest/report summaries

These are working context, not source of truth. They should always be reproducible from canonical state plus current code.

### Verbatim searchable memory

Implemented as `signal_evidence_items`. A dedicated evidence layer for **selected** Telegram material:

- strong/watch posts that actually enter decision support
- explicitly tagged posts
- excerpts referenced in recommendations or study plans

Each item should preserve:

- `raw_post_id` / `post_id`
- excerpt text
- channel/source
- Telegram link
- posted date
- project/topic scope
- evidence reason or selection reason
- capture week / last used time

Do **not** duplicate the full corpus into a second generic memory store.

### Preference / ranking memory

Keep lightweight:

- explicit tags remain the ground truth
- channel bias remains derived
- optional topic-level preference summaries may be added later if clearly useful

This repo does not need a learned opaque preference model.

### What should not be stored

- decorative wing/hall/room abstractions
- a global knowledge graph for every topic
- agent diaries
- compressed dialect artifacts
- duplicate copies of low-signal posts
- broad semantic embeddings across everything before scoped retrieval is proven necessary

---

## MemPalace: What Is Verified

### Verified implementation facts

From the repo and code:

- verbatim memory is stored in ChromaDB “drawers” with metadata for `wing` and `room`
- retrieval supports scope filters by `wing` and `room`
- a four-layer memory stack exists: identity, essential story, on-demand filtered retrieval, deep search
- conversation mining chunks transcripts into exchange pairs or paragraph groups
- room assignment is mostly heuristic in `convo_miner.py`
- a local SQLite knowledge graph exists separately from ChromaDB
- MCP tools expose search, filing, graph queries, navigation, and diary operations

### Claims that are only partly reliable for our purposes

- high benchmark claims are real in the repo, but some benchmark sections explicitly admit contamination or structural shortcuts
- the README’s “palace” framing overstates the practical necessity of the metaphorical hierarchy
- AAAK compression may be real inside that system, but it is not a demonstrated need for this repo

### MemPalace ideas that genuinely matter here

- preserve verbatim evidence instead of summarizing away the reason
- scope retrieval before global search
- keep a layered memory model with small always-on context and deeper on-demand retrieval
- preserve provenance in retrieval results
- stay local-first and avoid cloud-only memory services

### MemPalace ideas that conflict with this repo

- generic cross-domain memory taxonomy
- MCP-first memory surface as a product in itself
- large memory product surface unrelated to weekly research decisions
- diary and specialist-agent memory layers

---

## Adopt / Reject / Redesign

| Candidate idea | Decision | Why |
|---|---|---|
| Verbatim-first evidence storage | Adopt | This repo already has raw text, but needs a curated evidence layer for high-value signals |
| Scope-first retrieval | Adopt | Project/topic/time/source scoping fits the product and improves precision |
| Layered memory model | Adopt in lighter custom form | Useful if translated into repo-native layers, not a generic palace abstraction |
| Clear provenance on retrieved items | Adopt | Already partly available; should become mandatory for evidence retrieval |
| Decision continuity | Adopt | Acted-on, skipped, deferred, and rejected history are core decision-support state |
| Bounded always-on summaries | Adopt in lighter custom form | Project snapshots and channel memory should stay small and derived |
| Global vector memory over everything | Defer | Might help later, but only after scoped evidence retrieval is proven insufficient |
| Knowledge graph / temporal triples | Reject for current roadmap | Too much abstraction for limited incremental value here |
| Palace metaphor: wings / halls / rooms | Reject | Adds naming complexity without engineering leverage in this repo |
| AAAK compression dialect | Reject | Token compression is not the current bottleneck and adds a second representation system |
| Agent diary memory | Reject | Not aligned with the repo’s product shape |
| Benchmark-driven universal memory optimization | Reject | This product needs reliable weekly decision support, not benchmark theater |

---

## Target Architecture For This Repo

### Tier 1 — Canonical operational state

Owner: SQLite schema and deterministic pipeline.

Includes:

- `raw_posts`, `posts`, `topics`, `post_topics`
- project linkage and relevance state
- explicit feedback and tag tables
- triage and rejection tables
- generated weekly artifact tables

Rule: downstream systems may derive from this layer, but may not redefine it.

### Tier 2 — Project and source snapshots

Owner: derived refresh jobs.

Includes:

- refreshed source/channel summaries
- refreshed project snapshots

Rule: bounded text, refreshable, no unique facts that cannot be regenerated.

### Tier 3 — Verbatim evidence memory

Owner: scoped evidence builder.

Proposed entity: `signal_evidence_item`

Suggested fields:

- `id`
- `post_id`
- `raw_post_id`
- `week_label`
- `evidence_kind` (`strong_signal`, `manual_tag`, `project_insight_source`, `study_source`, `decision_support`)
- `excerpt_text`
- `source_channel`
- `message_url`
- `posted_at`
- `topic_labels_json`
- `project_names_json`
- `selection_reason`
- `last_used_at`

Rule: this is not the whole corpus. It is the subset worth resurfacing.

### Tier 4 — Decision continuity

Owner: feedback + triage integration.

Proposed entity: `decision_journal`

Suggested fields:

- `id`
- `decision_scope` (`signal`, `insight`, `study`, `project`)
- `subject_ref_type`
- `subject_ref_id`
- `project_name`
- `status` (`acted_on`, `ignored`, `deferred`, `rejected`, `completed`)
- `reason`
- `evidence_item_ids_json`
- `recorded_at`
- `recorded_by`

Rule: this becomes the continuity layer for “what we did with this.”

### Tier 5 — Preference memory

Owner: explicit feedback and derived counters.

Keep:

- `user_post_tags`
- `signal_feedback`
- per-channel derived bias

Do not add hidden learned state until the explicit system stops being sufficient.

---

## Retrieval Policy

### Principle

Narrow before deep.

### Retrieval flow

1. Determine scope from the caller:
   - project
   - topic
   - time window
   - source channel
   - decision state
2. Read canonical structured state first:
   - recent project snapshot
   - explicit decisions/tags/triage state
3. Pull matching evidence items inside that scope.
4. Only if the scoped result is weak:
   - fallback to FTS over raw posts or evidence
   - later, optionally fallback to embeddings over evidence items only
5. Return provenance-rich items, not just summary text.

### Example scopes

- Weekly brief for project insight:
  project `telegram-research-agent` + last 21 days + non-rejected signals + source provenance

- Implementation ideas suppression:
  recent related decisions + rejection history + recent evidence items touching that project/topic

- Study plan:
  active project snapshots + acted-on evidence + gaps not yet completed in study history

---

## Summary Refresh Rules

- `channel_memory`: refresh from explicit tags, not from model output
- project snapshots: refresh from project config, GitHub metadata, linked signal counts, recent commits
- weekly summaries: rebuildable artifacts tied to a week label
- evidence items: append/select during weekly processing; update `last_used_at` when resurfaced
- decision journal: append-only except for explicit state transitions

---

## Observability And Evaluation

### Needed debug surfaces

- inspect evidence items by project/topic/week/source
- inspect decision-journal history for a project or signal
- show why a recommendation resurfaced
- show why an item was suppressed

### Minimum evaluation surfaces

- scoped retrieval precision on fixture data
- provenance completeness checks
- repeated-idea suppression tests
- report usefulness review against recent decision history

---

---

## M3 — Target Schema Definitions

### `signal_evidence_items`

Full DDL:

```sql
CREATE TABLE signal_evidence_items (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,
    raw_post_id INTEGER NOT NULL,
    week_label TEXT NOT NULL,
    evidence_kind TEXT NOT NULL CHECK (
        evidence_kind IN (
            'strong_signal',
            'manual_tag',
            'project_insight_source',
            'study_source',
            'decision_support'
        )
    ),
    excerpt_text TEXT NOT NULL CHECK (length(trim(excerpt_text)) > 0),
    source_channel TEXT NOT NULL CHECK (length(trim(source_channel)) > 0),
    message_url TEXT,
    posted_at TEXT NOT NULL CHECK (length(trim(posted_at)) > 0),
    topic_labels_json TEXT NOT NULL DEFAULT '[]',
    project_names_json TEXT NOT NULL DEFAULT '[]',
    selection_reason TEXT NOT NULL CHECK (length(trim(selection_reason)) > 0),
    last_used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY (raw_post_id) REFERENCES raw_posts(id) ON DELETE CASCADE
);

CREATE INDEX idx_signal_evidence_items_post_id
    ON signal_evidence_items(post_id);

CREATE INDEX idx_signal_evidence_items_week_label
    ON signal_evidence_items(week_label);

CREATE INDEX idx_signal_evidence_items_evidence_kind
    ON signal_evidence_items(evidence_kind);

CREATE INDEX idx_signal_evidence_items_source_channel
    ON signal_evidence_items(source_channel);
```

Owner rule: scoped evidence builder (Phase 2).

Refresh rule: append during weekly processing; update `last_used_at` when resurfaced.

Provenance requirement: `source_channel`, `posted_at`, and `selection_reason` must be non-empty on every insert.

### `decision_journal`

Full DDL:

```sql
CREATE TABLE decision_journal (
    id INTEGER PRIMARY KEY,
    decision_scope TEXT NOT NULL CHECK (
        decision_scope IN ('signal', 'insight', 'study', 'project')
    ),
    subject_ref_type TEXT NOT NULL,
    subject_ref_id TEXT NOT NULL,
    project_name TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('acted_on', 'ignored', 'deferred', 'rejected', 'completed')
    ),
    reason TEXT,
    -- nullable: pipeline writes may omit reason; all inserts should provide a non-empty value where available
    evidence_item_ids_json TEXT NOT NULL DEFAULT '[]',
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recorded_by TEXT NOT NULL DEFAULT 'pipeline'
);

CREATE INDEX idx_decision_journal_decision_scope
    ON decision_journal(decision_scope);

CREATE INDEX idx_decision_journal_project_name
    ON decision_journal(project_name);

CREATE INDEX idx_decision_journal_status
    ON decision_journal(status);

CREATE INDEX idx_decision_journal_recorded_at
    ON decision_journal(recorded_at);
```

Owner rule: feedback + triage integration (Phase 2).

Refresh rule: append-only except for explicit status transitions; never delete.

Documented `subject_ref_type` values:

- `post_id`
- `insight_triage_id`
- `study_plan_week`
- `project_name`

### `project_context_snapshots` evolution

Additive schema change:

```sql
ALTER TABLE project_context_snapshots
    ADD COLUMN linked_signal_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE project_context_snapshots
    ADD COLUMN snapshot_week_label TEXT;
```

State: remains Tier 2 derived state; these columns support stale detection.

Compatibility rule: existing rows remain valid via defaults.

---


## M4 — Migration Mapping

### `channel_memory`

- New tier mapping: Tier 2.
- Structural changes: none.
- Migration strategy: no migration needed.

### `project_context_snapshots`

- New tier mapping: Tier 2.
- Structural changes: add `linked_signal_count INTEGER NOT NULL DEFAULT 0` and `snapshot_week_label TEXT`.
- Migration strategy: forward-only additive migration; no backfill needed.

### `signal_feedback`

- New tier mapping: stays Tier 1 canonical for explicit feedback; also feeds Tier 4 `decision_journal` going forward.
- Structural changes: none in Phase 1.
- Migration strategy: forward-only journal writes; no backfill required.
- Status mapping:
  - `acted_on` -> `acted_on`
  - `skipped` -> `ignored`
  - `marked_important` -> `acted_on`
- Recorded-by rule: `recorded_by='user'`.

### `insight_triage_records`

- New tier mapping: stays Tier 1 canonical for triage state; also feeds Tier 4 `decision_journal`.
- Structural changes: none in Phase 1.
- Migration strategy: forward-only journal writes from future triage events.
- Status mapping:
  - `do_now` -> `acted_on`
  - `backlog` -> `deferred`
  - `reject_or_defer` -> `rejected`
- Journal contract: `decision_scope='insight'` and `subject_ref_type='insight_triage_id'`.

### `insight_rejection_memory`

- New tier mapping: stays Tier 1 canonical fast gate.
- Structural changes: none in Phase 1.
- Migration strategy: forward-only dual-write in Phase 2 when a new rejection is recorded.
- Continuity rule: Phase 2 also writes a matching `decision_journal` row with `status='rejected'`.
- Role split: `insight_rejection_memory` remains the O(1) fingerprint lookup; `decision_journal` carries why and provenance.

### `user_post_tags`

- New tier mapping: Tier 1 canonical.
- Structural changes: none.
- Migration strategy: no migration required.
- Downstream use: tags feed `signal_evidence_items` selection in Phase 2.

### `study_plans`

- New tier mapping: stays canonical generated artifact state and feeds Tier 4 `decision_journal` on completion.
- Structural changes: deferred to Phase 2.
- Migration strategy: forward-only journal writes on completion with `status='completed'` and `decision_scope='study'`.

---


## M5 — Debug And Eval Contract

### Required debug surfaces

These surfaces must exist before Phase 3 output integration ships.

| CLI command | What it shows |
|---|---|
| `memory inspect evidence --project X --week LABEL` | Evidence items for that project and week, including `source_channel`, `message_url`, and `selection_reason` |
| `memory inspect evidence --kind strong_signal` | Evidence items of that kind sorted by `posted_at` descending |
| `memory inspect decisions --project X` | `decision_journal` rows for the project, newest first, with `status` and `reason` |
| `memory inspect decisions --scope insight --status rejected` | Rejected insight decisions |
| `memory inspect stale-snapshots` | `project_context_snapshots` rows where `snapshot_week_label` is older than two weeks |
| `memory inspect suppression --title '...'` | `insight_rejection_memory` fingerprint lookup plus matching `decision_journal` rows explaining why the idea was suppressed |

### Provenance completeness eval gate

- Every `signal_evidence_items` row must have non-null, non-empty `source_channel`, `posted_at`, `selection_reason`, and `excerpt_text`.
- `excerpt_text` must be at least 10 characters.
- Missing `message_url` is warning-only.
- Gate: at least 99% of inserted rows must pass.

### Scoped retrieval precision test

- Fixture shape: two projects and two weeks.
- Query contract: querying project A plus week W returns only rows where `project_names_json` contains A and `week_label = W`.
- Failure condition: zero tolerance for cross-project leakage.
- Test file: `tests/test_evidence_retrieval.py`.

### Decision continuity test

- Rejected insight in `insight_rejection_memory` must produce a matching `decision_journal` row with `status='rejected'`.
- `signal_feedback` with `acted_on` must produce a corresponding `decision_journal` row on the next run.
- Completed `study_plan` must produce a `decision_journal` row with `status='completed'`.
- Test file: `tests/test_decision_continuity.py`.

### Repeated-idea suppression test

- Insert a rejected fingerprint.
- Run recommendations.
- Assert the candidate is absent or explicitly labeled rejected.

### Report usefulness checklist

Phase 3 quality gate and Phase 4 fixture:

- At least one evidence citation includes source channel and date.
- No implementation idea rejected in the last 90 days resurfaces without explicit reason.
- Study plan references at least one acted-on evidence item or project snapshot.
- No evidence cited outside the project/time scope for that section.

---


## Implementation Summary

All phases are complete. The full build order was:

1. **M1–M5 (Phase 1 — Contract)**: schema finalized for `signal_evidence_items` and `decision_journal`; retrieval helper contract defined; debug/eval spec written
2. **M6–M10 (Phase 2 — MVP Tables)**: migrations applied; `fetch_evidence_items` and `fetch_decisions` retrieval helpers implemented; `record_signal_evidence_for_scored_posts`, `record_signal_evidence_for_manual_tag`, `record_decision_for_feedback`, `record_decisions_for_triage`, `record_study_completion_decision` evidence writers implemented; `project_context_snapshots` extended with `linked_signal_count` and `snapshot_week_label`
3. **M11–M14 (Phase 3 — Wire into Outputs)**: preference judge seeded with scoped project evidence; recommendations LLM prompt includes recent decisions and recent project evidence; study plan includes acted-on evidence; signal report shows originating channel when project_application is present
4. **M15–M17 (Phase 4 — Observability)**: `tests/test_retrieval.py` (14 tests), `tests/test_evidence.py` (15 tests), `docs/memory_inspection.md` operator guide, memory CLI subcommands
