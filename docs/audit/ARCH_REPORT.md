---
# ARCH_REPORT — Cycle 3
_Date: 2026-03-30_

---

## Component Verdicts

| Component | Verdict | Note |
|---|---|---|
| `src/ingestion/bootstrap_ingest.py` | PASS | No anthropic imports. Calls `llm/vision.py` only via `analyze_photo()`, which is routed through `llm/client.py` internals. WAL enabled. `message_url` stored as `https://t.me/{channel}/{message_id}`. |
| `src/ingestion/incremental_ingest.py` | PASS | Same profile as bootstrap; shares ingestion helpers; no LLM coupling. WAL enabled. |
| `src/processing/cluster.py` | PASS | Purely deterministic — TF-IDF + KMeans + silhouette score. No anthropic import. `random_state=42` ensures reproducibility. |
| `src/processing/score_posts.py` | DRIFT | No LLM calls (correct), but `cluster_coherence` sub-dimension is permanently stubbed at `0.5` (see ARCH-4 carry-forward). `scoring.yaml` documents it as "silhouette contribution from the post's cluster" — that data path does not exist per-post. |
| `src/llm/client.py` | PASS | All SDK calls (`Anthropic()`) are contained here. `_record_usage()` writes to `llm_usage` table. Cost estimated via `router.estimate_cost_usd()`. `_get_client()` and `_get_model()` are internal helpers, not exported as public API. |
| `src/llm/router.py` | DRIFT | `route()` function is implemented and exports CHEAP/MID/STRONG tier selection. Only `route("synthesis")` is wired in `generate_digest.py`. Per-post routing (score-based path) is implemented but has zero call sites. This constitutes partial Phase 3 pre-wiring introduced during Phase 1 — see ARCH-NEW-1. |
| `src/llm/vision.py` | DRIFT | Calls `client.messages.create()` directly using `_get_client()` imported from `llm/client.py`, bypassing the `complete()` wrapper. This is a structural violation: calling the SDK through an internal helper of `client.py` is not the same as routing through the module's public interface. Cost is recorded via `_record_usage()` so tracking is intact, but the call does not go through `complete()` and therefore bypasses retry logic. |
| `src/bot/handlers.py` | DRIFT | Handlers are primarily delivery-only (PASS for most). However: (1) `handle_ask` constructs an LLM prompt and calls `LLMClient.complete()` directly — this is business logic (context retrieval + synthesis) inside a bot handler, not pure delivery. (2) `generate_recommendations` is imported at line 15 but never called from this module (dead import introduced by T32 cleanup). |
| `src/bot/telegram_delivery.py` | PASS | Delivery-only. `send_text()` accepts optional `parse_mode` (CODE-2 fix confirmed). |
| `src/output/generate_digest.py` | PASS | `route("synthesis")` wired at line 480. `_store_quality_metrics()` called in both early-exit path (line 433) and normal path (line 512). CODE-5 open: no `time.sleep()` between digest send (line 534) and insights send (line 546). |
| `src/config/scoring.yaml` | DRIFT | `cluster_coherence` sub-weight (0.15) is documented as "Silhouette contribution from the post's cluster" but there is no per-post silhouette data path. The stub in `score_posts.py` hardcodes `0.5`. This misleads operators. See ARCH-4 carry-forward. |
| `src/config/settings.py` | PASS | `CHEAP_MODEL`, `MID_MODEL`, `STRONG_MODEL` env vars added with safe defaults (`claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-6`). Unset env vars fall back to named defaults. No unsafe behavior if vars are absent. |
| `src/db/migrate.py` | PASS | WAL mode enabled. All new tables (`llm_usage`, `study_plans`, `cluster_runs`, `quality_metrics`) present. Phase 19 scoring columns (`signal_score`, `bucket`, `project_matches`, `interpretation`) present. |

---

## Contract Compliance

| Rule | Verdict | Note |
|---|---|---|
| A — SQLite WAL mode always on | PASS | `PRAGMA journal_mode = WAL;` confirmed in all 14 DB-opening sites across ingestion, processing, output, bot, and migrate. |
| B — Clustering deterministic (TF-IDF + KMeans only) | PASS | `cluster.py` uses only `TfidfVectorizer` + `KMeans(random_state=42)`. No LLM import. |
| C — `message_url` stored as `t.me/channel/message_id` | DRIFT | Implementation stores `https://t.me/{normalized}/{message_id}` (with `https://` prefix). Contract says `t.me/channel/message_id`. The `https://` prefix is functionally correct and the intent is met, but it technically does not match the contract literal. Classify as minor drift requiring contract clarification, not a code fix. |
| D — Output files written to `data/output/` only | PASS | All output modules (`generate_digest.py`, `generate_recommendations.py`, `generate_insight.py`, `generate_study_plan.py`, `map_project_insights.py`) write under `PROJECT_ROOT / "data" / "output" / ...`. |
| E — systemd timers define the schedule | PASS | `telegram-ingest.timer`, `telegram-digest.timer`, `telegram-cleanup.timer`, `telegram-study-reminder-fri.timer`, `telegram-study-reminder-tue.timer` all present in `systemd/`. No cron references found. |
| F — Routing policy must expose tier usage and escalation rate | DRIFT | `llm_usage` table records model per call (supporting manual tier analysis), but no explicit tier label (`CHEAP`/`MID`/`STRONG`) is stored in the table. Escalation rate is not directly queryable without mapping model names to tiers. Contract compliance requires tier to be stored or derivable directly. |
| G — Personalization cannot suppress globally important signals without explicit rule trace | PASS | `score_posts.py` boost/downrank rules are loaded from `profile.yaml` and applied via explicit functions. No silent suppression. |

---

## Architecture Findings

### ARCH-1 [P2] — `vision.py` bypasses `complete()` retry wrapper

**Symptom:** `src/llm/vision.py` calls `client.messages.create()` directly via `_get_client()` rather than using the `complete()` function from `llm/client.py`.

**Evidence:** `src/llm/vision.py:36` — `response = client.messages.create(...)`. `_get_client()` and `_record_usage()` are imported from `llm.client` but `complete()` is not used.

**Root cause:** Vision calls require multimodal message structure (image content blocks) that `complete()` does not support. The author bypassed the wrapper to construct the message manually.

**Impact:** (1) Retry logic (`_should_retry`, exponential backoff) in `complete()` is absent for photo analysis calls. A transient API error during photo analysis will not be retried and will silently return `None`. (2) Structural: the IMPLEMENTATION_CONTRACT.md states "All LLM calls go through `src/llm/client.py` — never call Anthropic SDK directly from modules." While `vision.py` is within `src/llm/`, calling `_get_client()` directly and building SDK messages bypasses the canonical entry point contract intent.

**Fix:** Extend `complete()` or add a `complete_vision()` function in `client.py` that accepts image bytes and routes through the retry wrapper. Move vision-specific message construction into `client.py`.

---

### ARCH-2 [P2] — `handle_ask` embeds business logic (context retrieval + LLM synthesis) in bot handler

**Symptom:** `src/bot/handlers.py:handle_ask` performs FTS5 query construction, context assembly, and direct `LLMClient.complete()` call.

**Evidence:** `src/bot/handlers.py:287–330` — `_build_fts_query()`, DB query, prompt assembly, and `LLMClient.complete(category="bot_ask")` all inside the handler.

**Root cause:** No dedicated `src/output/` or `src/processing/` module exists for ad-hoc question answering. The logic was placed inline in the handler for convenience.

**Impact:** Bot handlers are documented as delivery-only ("Bot handlers only deliver — no business logic in src/bot/"). The violation makes the handler untestable in isolation, couples DB access directly to the bot layer, and creates a pattern inconsistency with every other handler that delegates to `src/output/` modules.

**Fix:** Extract context retrieval + synthesis into `src/output/generate_answer.py` (or equivalent). Handler calls the function and only sends the result.

---

### ARCH-3 [P3] — `docs/architecture.md` does not describe the scoring engine, new DB tables, or `src/llm/router.py`

**Symptom:** `architecture.md` describes the Scoring Layer conceptually but contains no mention of `score_posts.py`, `scoring.yaml`, `quality_metrics` table, `llm_usage` table, `cluster_runs` table, `study_plans` table, or `src/llm/router.py`.

**Evidence:** `grep quality_metrics docs/architecture.md` — NO MATCHES. `grep llm_usage docs/architecture.md` — NO MATCHES. `grep router docs/architecture.md` — NO MATCHES (only conceptual "Routing Layer" section with no implementation reference).

**Root cause:** Phase 19 and T34 added these components without updating architecture.md. Open finding from Cycle 2.

**Impact:** Phase 1 exit criterion "aligned docs" is not met. Operators and future reviewers cannot trace implementation to architectural contract.

**Fix:** Add subsections to architecture.md: (1) Component Map entry for `src/llm/router.py`; (2) Data Model entries for `quality_metrics`, `llm_usage`, `cluster_runs`, `study_plans`; (3) note that `scoring.yaml` + `profile.yaml` are the configuration surface for the Scoring Layer.

---

### ARCH-4 [P3] — `cluster_coherence` in `scoring.yaml` documents a non-existent per-post data path

**Symptom:** `scoring.yaml` documents `cluster_coherence: 0.15` as "Silhouette contribution from the post's cluster." `score_posts.py` stubs this permanently at `0.5` with comment "not available per-post cheaply."

**Evidence:** `src/processing/score_posts.py:215–216` — `coherence_score = 0.5` (hardcoded). `src/config/scoring.yaml:31` — `cluster_coherence: 0.15  # Silhouette contribution from the post's cluster`.

**Root cause:** The per-post silhouette data path was never built. The `cluster_runs` table records a global silhouette score per run, not per post or per cluster. The config key was left as a placeholder.

**Impact:** Operators tuning `cluster_coherence` in `scoring.yaml` will see no effect. The effective weight of `technical_depth` deviates from the advertised sum. This creates an invisible scoring bias and misleads operators about which levers are active.

**Fix:** Add a comment to `scoring.yaml` explicitly stating this sub-dimension is stubbed at 0.5 and will not respond to config changes until Phase 2 implements the per-cluster silhouette lookup.

---

### ARCH-5 [P3] — `docs/spec.md` section 19 artifact structure does not reflect actual `src/` tree

**Symptom:** `spec.md` section 19 lists `llm/client.py` only under `src/llm/`. Actual `src/llm/` contains `client.py`, `router.py`, and `vision.py`. `src/output/` in spec lists three files; actual directory has seven. `src/processing/` is missing `score_posts.py`. `src/reporting/` not listed. `src/integrations/` not listed. `src/bot/` not listed. Multiple systemd units absent from spec tree.

**Evidence:** `docs/spec.md:645–646` shows `llm/` with `client.py` only. Actual file listing shows 33 Python files across 9 directories vs. spec's partial listing.

**Root cause:** Spec artifact structure was not updated to reflect T27/T34 additions or any additions since Phase 18.

**Impact:** Reviewers and new contributors cannot use spec.md to understand the current module structure. Phase 1 exit criterion "aligned docs" is not met.

**Fix:** Update spec.md section 19 to reflect actual source tree. Minimum: add `router.py`, `vision.py` to `src/llm/`; add `score_posts.py` to `src/processing/`; add `src/bot/`, `src/reporting/`, `src/integrations/` directories; add all new systemd units.

---

### ARCH-NEW-1 [P2] — `src/llm/router.py` per-post routing is implemented but not wired; constitutes Phase 3 pre-wiring in Phase 1

**Symptom:** `router.route(task_type, signal_score)` supports score-based tier selection (CHEAP/MID/STRONG based on 0.45/0.75 thresholds), but no caller ever passes a `signal_score`. `generate_digest.py` calls only `route("synthesis")` which bypasses score-based routing entirely.

**Evidence:** `src/llm/router.py:15–25` — full `route()` implementation with score-based branching. `src/output/generate_digest.py:480` — `route("synthesis")` is the only call site. `grep -rn 'route(' src/` confirms one call site total.

**Root cause:** T34 introduced router as Phase 3 scaffolding during Phase 1. The per-post routing path has no wiring yet because the per-post interpretation loop does not exist.

**Impact:** (1) The per-post routing signature creates an ambiguous contract: the function implies per-post usage but the system does not use it. (2) The score-based dispatch path has no integration test coverage because no production caller exercises it. (3) The sequencing rule "routing must not be introduced before scoring is measurable" is satisfied (scoring exists), but the gap between implementation and wiring should be formally acknowledged.

**Resolution required:** Label `router.py` explicitly as Phase 3 pre-wiring scaffolding via inline comment or a dedicated ADR entry, and ensure a Phase 3 task entry exists to wire per-post `route(signal_score=score)` calls.

---

### ARCH-NEW-2 [P3] — LLM cost logging is DEBUG-only with no queryable cost-per-run summary

**Symptom:** `client.py` emits `est_cost_usd` at DEBUG level per call. `llm_usage` table stores cost per call. No cost-per-run aggregation exists in `quality_metrics` or any other queryable surface. The `quality_metrics` table has no `total_cost_usd` column.

**Evidence:** `src/llm/client.py:133–145` — DEBUG-level cost log per call. `src/db/migrate.py:129–143` — `quality_metrics` schema has no cost column. The `/costs` bot command queries `llm_usage` by category and month, not by digest run.

**Root cause:** Phase 1 scope did not include cost-per-run binding to the digest run artifact.

**Impact:** Phase 3 success criterion "cost per run bounded and explainable" cannot be verified without manual SQL joins. Acceptable as Phase 1 state but must be a Phase 3 entry requirement.

**Fix (Phase 3):** Add `week_label TEXT` column to `llm_usage` or add `total_cost_usd REAL` to `quality_metrics`. Wire digest run context to sum costs for that run window.

---

### ARCH-6 [P3] — Dead import `generate_recommendations` in `src/bot/handlers.py`

**Symptom:** `from output.generate_recommendations import generate_recommendations` is present at line 15 but `generate_recommendations` is never called anywhere in `handlers.py`.

**Evidence:** `src/bot/handlers.py:15` — import present. `grep -n "generate_recommendations" src/bot/handlers.py` returns only line 15.

**Root cause:** T32 removed the redundant `generate_recommendations()` call from `handle_run_digest` but did not remove the corresponding import.

**Impact:** (1) Misleads readers about delivery ownership — `handlers.py` importing `generate_recommendations` implies it may call it; this is the exact pattern that caused CODE-6. (2) Any future refactor that sees this import may re-introduce the call. (3) Minor: unused import may trigger linting failures.

**Fix:** Remove line 15 from `src/bot/handlers.py`.

---

### ARCH-7 [P3] — `spec.md` section 7 `quality_metrics` note states "population is a future step" — now stale

**Symptom:** `docs/spec.md:341` says "Created by migration (Phase 19); population is a future step." T33 added `_store_quality_metrics()` to `generate_digest.py`, which now populates the table in both exit paths.

**Evidence:** `src/output/generate_digest.py:345–385` — `_store_quality_metrics()` fully implemented. Lines 433 and 512 — called in both early-exit and normal paths. `docs/spec.md:341` — "population is a future step."

**Root cause:** T33 implementation not reflected in spec.md.

**Impact:** Spec.md misleads reviewers into believing `quality_metrics` is unpopulated. Phase 1 exit criterion requires aligned docs.

**Fix:** Update `spec.md` section 7 `quality_metrics` note to: "Population implemented in T33; `_store_quality_metrics()` is called after every `run_digest()` invocation in both early-exit and normal paths."

---

## Doc Patches Needed

| File | Section | Change |
|---|---|---|
| `docs/architecture.md` | Component Map | Add `src/llm/router.py` as a named component under the Routing Layer |
| `docs/architecture.md` | Data Model (new subsection) | Add tables: `quality_metrics`, `llm_usage`, `cluster_runs`, `study_plans`. Add new columns: `signal_score`, `bucket`, `project_matches`, `interpretation` on `posts`; `tier`, `rationale` on `post_project_links`; `message_url`, `image_description` on `raw_posts` |
| `docs/architecture.md` | Scoring Layer | Note that `src/config/scoring.yaml` and `src/config/profile.yaml` are the configuration surface for the Scoring Layer |
| `docs/spec.md` | Section 7 — `quality_metrics` | Update "population is a future step" to reflect T33 implementation |
| `docs/spec.md` | Section 19 — Repository Artifact Structure | Update `src/llm/` to list `router.py`, `vision.py`; update `src/processing/` to add `score_posts.py`; add `src/bot/`, `src/reporting/`, `src/integrations/` directories; update `src/output/` to full list; update systemd unit list |
| `docs/spec.md` | Section 3 — AD-03 | Update "Current routing" description to include `CHEAP/MID/STRONG` tier model names and note that `src/llm/router.py` implements score-based dispatch (Phase 3 pre-wiring) |
| `docs/IMPLEMENTATION_CONTRACT.md` | Rule C | Clarify whether `message_url` should include `https://` prefix or be stored as bare `t.me/channel/message_id` — current implementation uses `https://` prefix |

---

_End of ARCH_REPORT — Cycle 3_
