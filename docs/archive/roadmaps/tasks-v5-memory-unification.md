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
| M3 | Define target schemas for `signal_evidence_items`, `decision_journal`, and evolved project snapshots | `[x]` | M2 |
| M4 | Add migration notes: how existing `channel_memory`, `project_context_snapshots`, `signal_feedback`, and triage tables map into the new model | `[x]` | M3 |
| M5 | Define debug/eval requirements for retrieval inspection and report usefulness checks | `[x]` | M2 |

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
| M6 | Add DB migrations for `signal_evidence_items` and `decision_journal` | `[x]` | M4 |
| M7 | Populate evidence items from strong/watch posts, explicit tags, and triaged insights with source provenance | `[x]` | M6 |
| M8 | Write decision-journal rows from feedback actions and insight triage outcomes | `[x]` | M6 |
| M9 | Add retrieval helpers that filter by project, topic, week range, source channel, and status before fallback search | `[x]` | M7 M8 |
| M10 | Add CLI/debug output to inspect scoped evidence and recent decision history | `[x]` | M9 |

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
| M11 | Replace ad hoc prompt context assembly in `preference_judge.py` with scoped retrieval helpers | `[x]` | M9 |
| M12 | Update recommendations generation to consult `decision_journal` and evidence items before surfacing ideas | `[x]` | M8 M9 |
| M13 | Update study-plan generation to use project snapshots plus recent acted-on evidence | `[x]` | M7 M9 |
| M14 | Improve report sections to preserve concise provenance where evidence is materially important | `[x]` | M11 |

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
| M15 | Add tests for scoped retrieval precision and provenance completeness | `[x]` | M14 |
| M16 | Add tests for decision continuity: acted-on, skipped, deferred, and rejected flows | `[x]` | M12 |
| M17 | Add CLI/operator docs for memory inspection and weekly troubleshooting | `[x]` | M10 M15 |

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

## Phase 5 — Autonomous Signal Discovery (zero-tag fallback)

**Goal**

The weekly brief must produce useful content even when there are no recent manual tags. The preference judge already has everything it needs (GitHub project context, channel memory, previous rated examples, post content) — but its output is filtered out by an overly strict `include=True` gate and a "prefer fewer" prompt instruction.

**Root cause (confirmed in W17 analysis)**

- `strong_count = 0` for three consecutive weeks (W15–W17): the scoring engine never assigned a "strong" bucket to any post.
- The preference judge ran 6 batches on 24 candidates and correctly classified posts — but `_build_auto_watch_lines` requires `judged.get("include") is True`, which the judge almost never sets because its prompt says "Be selective. Prefer fewer items."
- Result: "Additional Signals: No additional high-confidence auto-selected signals this week." — every week, unless the user has manually tagged posts that very week.
- `run_recommendations` (implementation brief) silently failed for W17 — no `insight` LLM call in `llm_usage` after the preference_judge runs, no W17 entry in `recommendations` table. Failed before the LLM call, caught by a bare `except Exception`. The implementation brief was not delivered.
- "No comparison baseline" — `AGENT_DB_PATH` env var not available when `_load_previous_quality_metrics()` runs in `signal_report.py`.

**What this phase implements**

1. Relax preference judge prompt: replace "Be selective. Prefer fewer items." with an explicit policy about when to set `include=True`.
2. Soften the `_build_auto_watch_lines` gate: drop the hard `include=True` requirement; use `category` + `confidence` as the primary filter.
3. Fix silent `run_recommendations` failure: add minimal error surfacing so the cause is logged clearly; fix the underlying crash point.
4. Fix "No comparison baseline": pass `db_path` through `format_signal_report` to `_load_previous_quality_metrics`, or read it from `settings` directly.

**What this phase does not implement**

- No changes to the ingestion or scoring layers yet (strong_count=0 is a separate calibration issue, tracked in A6).
- No UI changes.

**Success criteria**

- Weekly review contains at least 3 auto-selected signals when 10+ watch/cultural posts exist, without any manual tagging.
- Implementation brief is generated every week alongside the digest.
- "What Changed" section shows numeric delta vs previous week.

---

### Tasks

| ID | Task | Status | File |
|---|---|---|---|
| A5-1 | Relax preference judge prompt | `[x]` | `src/output/preference_judge.py` |
| A5-2 | Soften `_build_auto_watch_lines` gate | `[x]` | `src/output/signal_report.py` |
| A5-3 | Fix silent `run_recommendations` failure | `[x]` | `src/output/generate_digest.py` + `src/output/generate_recommendations.py` |
| A5-4 | Fix "No comparison baseline" | `[x]` | `src/output/signal_report.py` |

---

#### A5-1: Relax preference judge prompt

**File:** `src/output/preference_judge.py`  
**Function:** `_judge_batch_once`

**Problem:** The instruction "Be selective. Prefer fewer items." causes the judge to return `include=False` for nearly all posts, even when they are genuinely relevant to the user's active projects.

**Change:** In the prompt string (around line 275), replace:

```
"Be selective. Prefer fewer items. Ignore generic hype, broad news and shallow benchmarking unless it clearly fits the user's tagged taste.\n"
```

With:

```
"Use 'ignore' for category only when the post is clearly generic hype, meme, or pure benchmark announcement with no application to the user's projects. Set include=true whenever the post has a concrete takeaway for any active project, signals a tool or approach the user is building with, or matches a pattern from the tagged examples — even if only moderately relevant. A marginal actionable signal is better than a silent week. Do not suppress posts just because similar topics appeared before; surface the most actionable angle.\n"
```

Also update the `include` field description in the prompt from `"- include: boolean\n"` to:

```
"- include: boolean — true if the user would benefit from seeing this in the weekly brief (be generous: default true unless it is pure noise or clearly irrelevant)\n"
```

**Tests:** `tests/test_generate_digest.py`, `tests/test_personalize.py` — run existing suite, add one test that mocks judge returning `confidence=0.7, category='interesting', include=False` and verifies it still appears in auto_watch output after A5-2.

---

#### A5-2: Soften `_build_auto_watch_lines` gate

**File:** `src/output/signal_report.py`  
**Function:** `_build_auto_watch_lines` (line ~403)

**Problem:** Current gate:
```python
if judged.get("include") is not True:
    continue
if str(judged.get("category") or "") not in {"strong", "try_in_project", "interesting"}:
    continue
```
This filters out all posts unless `include=True` AND category is strong/try/interesting. Because the judge rarely sets `include=True`, the section is always empty without manual tags.

**Change:** Replace both conditions with:
```python
category = str(judged.get("category") or "")
if category not in {"strong", "try_in_project", "interesting"}:
    continue
confidence = float(judged.get("confidence") or 0.0)
# Show if judge explicitly approved, OR if it has a strong category with decent confidence
if not judged.get("include") and confidence < 0.65:
    continue
```

**Rationale:** Category is the substantive classification; `include` is a secondary flag. If the judge assigned a meaningful category with ≥0.65 confidence, the post is worth showing. The confidence floor prevents low-certainty noise from leaking in.

**Tests:** Add a unit test in `tests/test_signal_report.py` that verifies a post with `category='interesting', include=False, confidence=0.7` appears in auto_watch output, and a post with `category='interesting', include=False, confidence=0.5` does NOT appear.

---

#### A5-3: Fix silent `run_recommendations` failure

**Files:** `src/output/generate_digest.py`, `src/output/generate_recommendations.py`

**Problem:** In `generate_digest.py` line 724, `run_recommendations` is wrapped in a bare `except Exception` with only a warning log. When it fails before the LLM call (no `insight` entry in `llm_usage` for W17), the failure is invisible. No implementation brief is generated or delivered.

**Confirmed:** W17 `recommendations` table has no entry; `llm_usage` has no `insight` category call after the preference_judge calls at 05:02:28.

**Likely crash point:** `_load_project_context_snapshots` in `generate_recommendations.py` calls `refresh_all_project_context_snapshots(connection)` which writes to the DB. This is called on a fresh connection while the outer generate_digest connection is still open (inside the `with` block). In WAL mode this should be safe, but if `refresh_all_project_context_snapshots` raises (e.g., GitHub API rate limit, network error), the exception propagates uncaught through `_load_project_context_snapshots` to `run_recommendations`, which has no internal guard at that point.

**Change 1 — `generate_recommendations.py`:** Wrap `_load_project_context_snapshots` call inside `run_recommendations` in a try/except:

```python
try:
    project_context_snapshots = _load_project_context_snapshots(connection)
except Exception:
    LOGGER.warning("Project context snapshot refresh failed; using empty context", exc_info=True)
    project_context_snapshots = "No project context snapshots available yet."
```

**Change 2 — `generate_digest.py`:** Improve the exception log at line 724 to include traceback details explicitly:

```python
except Exception:
    LOGGER.warning("Insights generation failed, skipping", exc_info=True)
```

(Change `exc` parameter capture to `exc_info=True` without the positional `%s` so the full traceback is always logged.)

**Tests:** Add a test in `tests/test_generate_recommendations.py` that patches `_load_project_context_snapshots` to raise `RuntimeError` and verifies `run_recommendations` catches it gracefully and still attempts the LLM call with a fallback context string.

---

#### A5-4: Fix "No comparison baseline"

**File:** `src/output/signal_report.py`  
**Function:** `_load_previous_quality_metrics` (line ~67)

**Problem:** The function reads `AGENT_DB_PATH` from env. If not set, returns `None` → "No comparison baseline available." The `db_path` is available via `settings` object passed to `format_signal_report`, but it is not threaded through to `_load_previous_quality_metrics`.

**Change:** Thread `db_path` through the call stack:

1. `format_signal_report(posts, settings, ...)` already has `settings`.
2. Derive `db_path` at the top of the reader_mode branch:
   ```python
   db_path = str(getattr(settings, "db_path", "") or "").strip() if settings is not None else ""
   if not db_path:
       db_path = os.environ.get("AGENT_DB_PATH", "").strip()
   ```
3. Pass `db_path` to `_build_what_changed_lines(bucket_counts, db_path=db_path)`.
4. Update `_build_what_changed_lines` signature and `_load_previous_quality_metrics` call to accept and use `db_path` instead of reading env.
5. Do the same for `_format_legacy_signal_report` (legacy path) to avoid regression.

**Tests:** Add a test in `tests/test_signal_report.py` that passes a mock settings object with a valid `db_path` and verifies "What Changed" produces numeric comparison lines.

---

## Phase 6 — Fix SQLite Transaction Conflicts

**Goal**

Fix two interrelated SQLite errors that prevent `run_recommendations` and `generate_study_plan` from completing every week.

**Root cause (confirmed in W17 live log, 2026-04-20)**

```
sqlite3.OperationalError: database is locked           ← llm/client.py _record_usage
sqlite3.OperationalError: cannot start a transaction within a transaction  ← generate_recommendations.py:531
sqlite3.OperationalError: cannot start a transaction within a transaction  ← generate_study_plan.py:379
```

**Sequence that causes the crash:**

1. `run_recommendations` opens its own connection: `with sqlite3.connect(db_path) as connection`.
2. `_load_project_context_snapshots` → `refresh_all_project_context_snapshots` executes UPSERT statements. Python's `sqlite3` module auto-begins an implicit transaction on the first DML.
3. The LLM call (`complete(...)`) fires. Inside `_record_usage` in `llm/client.py`, a **third** connection opens and tries to INSERT into `llm_usage`. The second connection's implicit write transaction is still open → `database is locked`.
4. Back in `run_recommendations`, line 531 does `connection.execute("BEGIN")` explicitly. The second connection already has an implicit transaction → `cannot start a transaction within a transaction`. Crash. Same pattern in `generate_study_plan.py:379`.

**Fix strategy**

Python's `sqlite3` module auto-begins a transaction when isolation_level is non-None (the default). Explicit `connection.execute("BEGIN")` is correct only when `isolation_level=None` (autocommit). Mixing both causes the crash.

The right fix is to commit the implicit transaction before doing additional write batches, not to issue a redundant `BEGIN`. Replace the explicit `BEGIN` → `COMMIT` pairs with just `connection.commit()` calls, relying on Python's auto-transaction.

For `_record_usage`: add `timeout=5` to `sqlite3.connect()` so it waits up to 5 s for any write lock to clear instead of immediately failing.

**What this phase implements**

1. Remove explicit `connection.execute("BEGIN")` from `generate_recommendations.py` (lines 531, 539) — replace with `connection.commit()` where the intent is to flush a batch.
2. Remove explicit `connection.execute("BEGIN")` from `generate_study_plan.py` (line 379) — same pattern.
3. Add `timeout=5` to `sqlite3.connect(db_path)` in `llm/client.py:_record_usage`.

**What this phase does not implement**

- No changes to other files that use explicit `BEGIN` (they operate on isolated connections that don't mix implicit and explicit transactions in the same path).
- No connection pooling or refactoring of the outer connection in `generate_digest.py`.

**Success criteria**

- `run_recommendations` completes and writes a row to the `recommendations` table every week.
- `generate_study_plan` completes without "cannot start a transaction" error.
- `_record_usage` no longer logs `database is locked` warnings.
- Full test suite passes.

---

### Tasks

| ID | Task | Status | File |
|---|---|---|---|
| A6-1 | Remove explicit `BEGIN` from `generate_recommendations.py` | `[x]` | `src/output/generate_recommendations.py` |
| A6-2 | Remove explicit `BEGIN` from `generate_study_plan.py` | `[x]` | `src/output/generate_study_plan.py` |
| A6-3 | Add `timeout=5` to `_record_usage` connection | `[x]` | `src/llm/client.py` |

---

#### A6-1: Remove explicit BEGIN from generate_recommendations.py

**File:** `src/output/generate_recommendations.py`

**Problem:** Lines 531 and 539 call `connection.execute("BEGIN")` explicitly on a connection that already has an implicit transaction open from prior UPSERT operations. This raises `cannot start a transaction within a transaction`.

**Change:** Remove both `connection.execute("BEGIN")` calls. The `connection.commit()` calls that follow are correct and sufficient — Python auto-begins the next transaction after each commit.

Before (line 530–533):
```python
# Triage: classify ideas and apply rejection memory before rendering
connection.execute("BEGIN")
triaged = triage_insights(insights_text, connection, week_label)
connection.commit()
```

After:
```python
# Triage: classify ideas and apply rejection memory before rendering
triaged = triage_insights(insights_text, connection, week_label)
connection.commit()
```

Before (line 539–541):
```python
connection.execute("BEGIN")
_store_recommendations(connection, week_label, delivery_text)
connection.commit()
```

After:
```python
_store_recommendations(connection, week_label, delivery_text)
connection.commit()
```

**Tests:** Add a test in `tests/test_generate_recommendations.py` that runs `run_recommendations` against a real in-memory or temp-file SQLite DB (with all required tables) without patching the connection, and verifies no transaction exception is raised and the recommendations row is stored.

---

#### A6-2: Remove explicit BEGIN from generate_study_plan.py

**File:** `src/output/generate_study_plan.py`

**Problem:** Line 379 calls `connection.execute("BEGIN")` explicitly after `complete()` has triggered `_record_usage` which may have left a write lock contention, and after implicit DML transactions from context refresh. Same pattern as A6-1.

**Change:** Remove `connection.execute("BEGIN")` at line 379. Keep the `connection.commit()` that follows.

Before:
```python
connection.execute("BEGIN")
connection.execute(
    """
    INSERT INTO study_plans ...
    """,
    ...
)
connection.commit()
```

After:
```python
connection.execute(
    """
    INSERT INTO study_plans ...
    """,
    ...
)
connection.commit()
```

**Tests:** Add a test in `tests/test_generate_digest.py` or a new `tests/test_generate_study_plan.py` that verifies `generate_study_plan` does not raise a transaction error when called after a context-refreshing operation.

---

#### A6-3: Add timeout to _record_usage connection

**File:** `src/llm/client.py`

**Problem:** `sqlite3.connect(db_path)` with no timeout immediately raises `database is locked` if another connection holds a write lock. This makes LLM usage logging unreliable during heavy pipeline runs.

**Change:** Add `timeout=5`:

Before:
```python
with sqlite3.connect(db_path) as conn:
```

After:
```python
with sqlite3.connect(db_path, timeout=5) as conn:
```

**Tests:** Existing test suite is sufficient. Confirm no regressions.

---

## First Recommended Implementation Phase

Execute Phase 5 tasks in this order:

1. **A5-3** — fix silent failure first so we can see what actually breaks
2. **A5-1** — relax judge prompt so it produces more `include=True` signals
3. **A5-2** — soften the auto_watch gate to use category+confidence
4. **A5-4** — fix "No comparison baseline"

Run the full test suite after each task.
