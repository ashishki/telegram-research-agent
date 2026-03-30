---
# ARCH_REPORT — Cycle 2
_Date: 2026-03-30_

---

## Component Verdicts

| Component | Verdict | Note |
|-----------|---------|------|
| Ingestion layer (`src/ingestion/`) | PASS | No `anthropic` imports found in `bootstrap_ingest.py` or `incremental_ingest.py`. |
| Clusterer (`src/processing/cluster.py`) | PASS | No `anthropic` imports; TF-IDF + KMeans only (per earlier baseline; not changed in Phase 19). |
| LLM transport discipline | PASS | No direct `anthropic.Anthropic()` calls found outside `src/llm/client.py`. All LLM calls route through `complete()` in `src/llm/client.py`. |
| Bot handlers (`src/bot/`) | DRIFT | `handle_run_digest` in `handlers.py:426–439` calls `run_digest()` and then `generate_recommendations()` directly — triggering full pipeline execution and Telegram delivery from the bot layer. This exceeds the "delivery only" contract. See ARCH-1. |
| Scoring pipeline (`src/processing/score_posts.py`) | PASS | Deterministic; no LLM calls; reads only from `posts`, `raw_posts`, `post_topics`, `topics`. Config loaded via `yaml.safe_load`. Writes scores back via `executemany`. Layer boundary respected. |
| Digest generator rewire (`src/output/generate_digest.py`) | DRIFT | T27 embedded the `run_recommendations` call and a second `send_text` delivery inside `run_digest()` — blurring the digest generator into an orchestrator. See ARCH-2. |
| Schema migration (`src/db/migrate.py`) | PASS | All T23 columns (`signal_score`, `bucket`, `project_matches`, `interpretation` on `posts`; `tier`, `rationale` on `post_project_links`; `quality_metrics` table) present with idempotent `ALTER TABLE ... ADD COLUMN` guards catching `duplicate column name`. |
| Prompt redesign (`docs/prompts/digest_generation.md`, `docs/prompts/project_insights.md`) | PASS | Variables `{scored_posts}`, `{noise_count}`, `{noise_summary}` present in prompt template and substituted at all call sites in `generate_digest.py:399–406`. `project_insights.md` uses three-tier inference. |
| NO_OVERLAP_NOTE elimination (`src/output/generate_digest.py`, `src/integrations/github_crossref.py`) | PASS | Guard at `generate_digest.py:145` skips repos where `matched_topics == [NO_OVERLAP_NOTE]` or is empty. Sentinel string is never concatenated into output lines. No surface-through risk detected. |
| Config files (`src/config/profile.yaml`, `src/config/scoring.yaml`) | PASS | See Contract Compliance Rule B detail below. Weight sums valid; bucket thresholds ordered. |

---

## Contract Compliance

| Rule | Verdict | Note |
|------|---------|------|
| Rule A: SQLite WAL mode enabled | PASS | `PRAGMA journal_mode = WAL;` present in `migrate.py:30`, `score_posts.py:334`, `generate_digest.py:363`, and all other DB-touching modules. |
| Rule B: Clustering deterministic (TF-IDF + KMeans only) | PASS | `cluster.py` unchanged; no LLM in scoring engine. Scoring is a weighted heuristic, not a probabilistic/LLM step. |
| Rule C: `message_url` stored as `t.me/channel/message_id` | PASS | `bootstrap_ingest.py:51` constructs `https://t.me/{normalized}/{message_id}`. Format complies. `incremental_ingest.py` reuses the same helper. |
| Rule D: Output files written to `data/output/` only | PASS | All output modules use `PROJECT_ROOT / "data" / "output" / <subdir>`. No output written outside this tree. |
| Rule E: systemd timers define the schedule | PASS | `telegram-ingest.timer`, `telegram-digest.timer`, `telegram-cleanup.timer`, `telegram-study-reminder-tue.timer`, `telegram-study-reminder-fri.timer` all present in `systemd/`; schedules defined via `OnCalendar=`. |

---

## Architecture Findings

### ARCH-1 [P2] — Bot handler `handle_run_digest` violates delivery-only contract

**Symptom:** `handle_run_digest` in `src/bot/handlers.py:426–439` calls `run_digest(settings)` (which internally triggers scoring, LLM synthesis, file write, DB write, and Telegram delivery) and then redundantly calls `generate_recommendations(settings)`.

**Evidence:** `src/bot/handlers.py:426–429`

**Root cause:** `handle_run_digest` was designed as a manual trigger shortcut for testing. Because `run_digest()` now embeds orchestration logic (scoring + recommendations delivery), any bot-triggered call re-executes the full pipeline including a second Telegram send from inside `run_digest`.

**Impact:** Bot handlers are architecturally defined as delivery-only (query DB, format, send). Placing pipeline orchestration calls in `handlers.py` means the pipeline can be triggered from two paths (systemd timer via `main.py digest` and bot `/run_digest`), each with subtly different behavior: `handle_run_digest` calls `generate_recommendations()` again after `run_digest()` already called `run_recommendations()` internally (see ARCH-2), risking duplicate recommendations delivery.

**Fix:** Extract a thin `run_pipeline(settings)` orchestrator function in `src/output/` or `src/main.py`. Bot handler calls orchestrator; orchestrator handles sequencing. Bot handler returns only a status message.

---

### ARCH-2 [P2] — `run_digest` has become a covert orchestrator

**Symptom:** `src/output/generate_digest.py:452–462` embeds a call to `run_recommendations(settings)` and a second `send_text()` delivery inside `run_digest()`. The digest generator is defined in `docs/architecture.md` as responsible only for: query posts + topics, call LLM, write digest, write file.

**Evidence:** `src/output/generate_digest.py:452–462`

**Root cause:** The T27 "insights second-message" feature was implemented directly inside `run_digest` for expediency. This is the same root cause as ARCH-1 — absence of an explicit orchestration layer.

**Impact:** `DigestResult` is returned as successful even when `run_recommendations` fails silently (bare `except Exception as e`). The caller (systemd service via `main.py`) has no visibility into whether insights were generated. This is CODE-4 from META_ANALYSIS (still open). Additionally, calling `run_recommendations` from inside `generate_digest` creates a circular responsibility: the output layer module now orchestrates another output layer module.

**Fix:** Move the `run_recommendations` call and its delivery to the pipeline orchestrator (e.g., `src/main.py handle_digest`). `run_digest` should return `DigestResult` only. The orchestrator sequence should be: `score_posts` → `run_digest` → `run_recommendations` → deliver each result.

---

### ARCH-3 [P2] — Scoring engine is not reflected in `docs/architecture.md`

**Symptom:** `docs/architecture.md` (version 1.0.0, date 2026-03-16) has no mention of `src/processing/score_posts.py`, `src/config/scoring.yaml`, `src/config/profile.yaml`, the `signal_score`/`bucket` columns, or the `quality_metrics` table. The Processing Layer section lists only Normalizer, Clusterer, and Topic Detector.

**Evidence:** `docs/architecture.md` — Processing Layer section (lines 85–118); `src/processing/score_posts.py` (entire file, T24).

**Root cause:** Phase 19 (T22–T27) was implemented without a doc update step. `docs/architecture.md` reflects the Phase 0 baseline.

**Impact:** Architecture document is stale. The document is the authoritative review contract; any future reviewer relying on it will miss the scoring layer entirely. `docs/spec.md` section 11 (Weekly Digest Pipeline) still references `{notable_posts}` as the prompt input variable — this variable was replaced by `{scored_posts}` in T27.

**Fix:** See Doc Patches Needed section below.

---

### ARCH-4 [P3] — `scoring.yaml` `cluster_coherence` sub-weight references non-existent per-post data

**Symptom:** `scoring.yaml` defines `technical_depth_weights.cluster_coherence: 0.15`. The `_score_technical_depth()` function in `score_posts.py:216` hardcodes `coherence_score = 0.5` with comment "not available per-post cheaply, default to 0.5". The config weight is consumed but the underlying signal is permanently stubbed.

**Evidence:** `src/processing/score_posts.py:215–216`, `src/config/scoring.yaml:31`

**Root cause:** `cluster_coherence` was included in the scoring design for Phase 2 but is not populated in Phase 1. The config implies the weight is live.

**Impact:** The `technical_depth` score is biased by a constant 0.075 (0.15 × 0.5) on every post regardless of actual cluster quality. This is not a correctness bug but makes the config misleading — `cluster_coherence: 0.15` implies it is an active signal. Misled future operators may tune this weight expecting effect.

**Fix:** Either populate `cluster_coherence` from the `cluster_runs` silhouette data, or annotate the config entry with `# STUB: always 0.5 until Phase 2` and add a TODO in `score_posts.py`.

---

### ARCH-5 [P3] — `docs/spec.md` prompt contract (section 11) not updated for T27 variable rename

**Symptom:** `docs/spec.md:419` still specifies the digest LLM prompt input as `{week: str, topics: [...], notable_posts: [...], signal_threshold: int}`. The actual input after T27 is `{week_label, date_range, total_post_count, channel_count, noise_count, scored_posts, topic_summary, noise_summary}`.

**Evidence:** `docs/spec.md:419`, `docs/prompts/digest_generation.md` (User Prompt Template), `src/output/generate_digest.py:396–406`

**Root cause:** Same as ARCH-3 — spec not updated after T27 rewire.

**Impact:** Spec section 11 is the reference for anyone reasoning about what the LLM receives. The stale contract creates confusion about what variables drive the digest and makes it harder to audit prompt injection risk.

**Fix:** See Doc Patches Needed section.

---

## Doc Patches Needed

| File | Section | Change |
|------|---------|--------|
| `docs/architecture.md` | Processing Layer | Add "Scorer (`src/processing/score_posts.py`)" sub-section: reads from `posts`/`raw_posts`/`post_topics`/`topics`; loads `scoring.yaml` + `profile.yaml`; computes `signal_score` and `bucket`; writes to `posts`; no LLM calls. |
| `docs/architecture.md` | Database Layer | Document new columns: `posts.signal_score`, `posts.bucket`, `posts.project_matches`, `posts.interpretation`; `post_project_links.tier`, `post_project_links.rationale`; new `quality_metrics` table. |
| `docs/architecture.md` | Configuration | Add `scoring.yaml` and `profile.yaml` to the Config section with their roles (scoring weights, personal interest profile). |
| `docs/architecture.md` | Output Layer / Digest Generator | Note that digest now uses scoring-first flow: `score_posts()` runs before `_fetch_scored_posts()`. Document new prompt variables `{scored_posts}`, `{noise_count}`, `{noise_summary}`. |
| `docs/spec.md` | Section 11 (Weekly Digest Pipeline) | Update LLM prompt contract: replace `{notable_posts: [...], signal_threshold: int}` with `{scored_posts: [...], noise_count: int, noise_summary: str, topic_summary: [...]}`. |
| `docs/spec.md` | Section 7 (Data Model) | Add `signal_score REAL`, `bucket TEXT`, `project_matches TEXT`, `interpretation TEXT` to `posts` table. Add `tier TEXT`, `rationale TEXT` to `post_project_links`. Add `quality_metrics` table definition. |

---
