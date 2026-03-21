# Telegram Research Agent — Task Graph

**Version:** 1.0.0
**Date:** 2026-03-16
**Status:** Baseline

---

## Task Status Legend

| Symbol | Meaning |
|---|---|
| `[ ]` | Not started |
| `[~]` | Implemented, pending review (set by orchestrator after Codex completes) |
| `[x]` | Complete (implemented + reviewed, set by orchestrator after PASS) |
| `[!]` | Blocked — needs human input before loop can continue |

---

## Phase 0 — Architecture (Strategist)

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P0-01 | Write `docs/spec.md` | Strategist | `[x]` | — |
| P0-02 | Write `docs/architecture.md` | Strategist | `[x]` | P0-01 |
| P0-03 | Write `docs/tasks.md` | Strategist | `[x]` | P0-01 |
| P0-04 | Write `docs/dev-cycle.md` | Strategist | `[x]` | P0-01 |
| P0-05 | Write `docs/ops-security.md` | Strategist | `[x]` | P0-01 |
| P0-06 | Write LLM prompt templates in `docs/prompts/` | Strategist | `[ ]` | P0-02 |

---

## Phase 1 — Project Scaffold

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P1-01 | Create `src/config/channels.yaml` with placeholder entries | Codex | `[x]` | P0-02 |
| P1-02 | Create `src/config/settings.py` (env var config loader) | Codex | `[x]` | P1-01 |
| P1-03 | Create `src/db/schema.sql` (all tables: raw_posts, posts, topics, post_topics, digests, recommendations, projects, post_project_links) | Codex | `[x]` | P0-02 |
| P1-04 | Create `src/db/migrate.py` (idempotent migration runner) | Codex | `[x]` | P1-03 |
| P1-05 | Create `src/llm/client.py` (Anthropic SDK wrapper with `complete()` and `complete_json()`, reads LLM_API_KEY and MODEL_PROVIDER from env) | Codex | `[x]` | P0-02 |
| P1-06 | Create `requirements.txt` with pinned deps: anthropic, telethon, scikit-learn, pyyaml | Codex | `[x]` | P1-05 |
| P1-07 | Create `src/main.py` (CLI entry point with subcommands: `ingest`, `digest`, `bootstrap`) | Codex | `[x]` | P1-02 |
| P1-08 | Create `scripts/setup.sh` (interactive Telethon auth, first-run schema migration) | Codex | `[x]` | P1-04 |
| P1-09 | Create `data/` directory structure (agent.db excluded from git, output dirs present) | Codex | `[x]` | P1-04 |
| P1-10 | Create `.gitignore` for `data/agent.db`, `*.session`, `*.env`, `__pycache__` | Codex | `[x]` | P1-09 |

**Phase 1 Review Criteria:**
- `src/db/migrate.py` runs without error on a fresh environment.
- `src/llm/client.py` correctly implements the OpenClaw wire protocol (verified against source).
- `src/main.py` parses subcommands correctly.
- No secrets or session files present in workspace.

---

## Phase 2 — Bootstrap Ingestion

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P2-01 | Create `src/ingestion/telegram_client.py` (Telethon session factory, credential loading) | Codex | `[x]` | P1-02 |
| P2-02 | Create `src/ingestion/bootstrap_ingest.py` (90-day historical pull, all channels) | Codex | `[x]` | P2-01, P1-04 |
| P2-03 | Implement `FloodWaitError` handling in ingestion client | Codex | `[x]` | P2-01 |
| P2-04 | Implement idempotency check (`(channel_id, message_id)` unique constraint) | Codex | `[x]` | P1-03 |
| P2-05 | Implement per-channel progress logging (inserted, skipped, errors) | Codex | `[x]` | P2-02 |
| P2-06 | Wire `bootstrap` subcommand in `src/main.py` to `bootstrap_ingest.py` | Codex | `[x]` | P2-02, P1-07 |
| P2-07 | Create `scripts/run_bootstrap.sh` (wrapper to run bootstrap with env loaded) | Codex | `[x]` | P2-06 |

**Phase 2 Review Criteria:**
- Bootstrap script runs end-to-end on at least one test channel.
- Deduplication verified: second run inserts 0 rows.
- Telethon session file created in `/srv/openclaw-you/secrets/`, not in workspace.
- `FloodWaitError` handled gracefully (waits, does not crash).

---

## Phase 3 — Normalization

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P3-01 | Create `src/processing/normalize_posts.py` (reads raw_posts, writes posts) | Codex | `[x]` | P1-04 |
| P3-02 | Implement text cleaning (whitespace, Markdown artifacts) | Codex | `[x]` | P3-01 |
| P3-03 | Implement metadata extraction (URL count, code block detection, word count) | Codex | `[x]` | P3-01 |
| P3-04 | Implement lightweight language detection (heuristic: character set analysis) | Codex | `[x]` | P3-01 |
| P3-05 | Implement FTS5 virtual table population for `posts.content` | Codex | `[x]` | P1-03 |
| P3-06 | Wire `normalize` step into `ingest` subcommand pipeline in `main.py` | Codex | `[x]` | P3-01, P1-07 |

**Phase 3 Review Criteria:**
- All `raw_posts` rows without a `posts` entry are processed.
- FTS5 table is queryable after normalization.
- No LLM calls made during normalization.
- Language detection does not crash on non-Latin text.

---

## Phase 4 — Topic Detection

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P4-01 | Create `src/processing/cluster.py` (TF-IDF + K-Means, outputs keyword sets per cluster) | Codex | `[x]` | P3-01 |
| P4-02 | Implement elbow heuristic or fixed-k config for cluster count | Codex | `[x]` | P4-01 |
| P4-03 | Create `src/processing/detect_topics.py` (matches clusters to existing topics or creates new via LLM) | Codex | `[x]` | P4-01, P1-05 |
| P4-04 | Implement overlap check between new cluster keywords and existing topic keywords | Codex | `[x]` | P4-03 |
| P4-05 | Implement LLM call for new topic label generation using `docs/prompts/rubric_discovery.md` | Codex | `[x]` | P4-03, P0-06 |
| P4-06 | Write results to `topics` and `post_topics` tables | Codex | `[x]` | P4-05 |

**Phase 4 Review Criteria:**
- Clusters contain sensible keyword groupings.
- LLM called only for new/unmatched clusters, not for every run.
- Topics table grows incrementally; no duplicates.
- Prompt loaded from `docs/prompts/rubric_discovery.md`, not hardcoded.

---

## Phase 5 — Weekly Incremental Pipeline

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P5-01 | Create `src/ingestion/incremental_ingest.py` (delta pull since MAX(posted_at) per channel) | Codex | `[x]` | P2-01, P1-04 |
| P5-02 | Wire `ingest` subcommand to run: incremental → normalize → cluster → detect_topics | Codex | `[x]` | P5-01, P3-06, P4-06 |
| P5-03 | Create `systemd/telegram-ingest.service` | Codex | `[x]` | P5-02 |
| P5-04 | Create `systemd/telegram-ingest.timer` (Monday 07:00, Persistent=true) | Codex | `[x]` | P5-03 |
| P5-05 | Create `scripts/run_weekly.sh` (manual trigger for full weekly pipeline) | Codex | `[x]` | P5-02 |

**Phase 5 Review Criteria:**
- Incremental run after bootstrap fetches only new posts.
- Pipeline steps run in correct order.
- Systemd unit runs as `oc_you`, not root.
- `Persistent=true` on timer (catches missed runs).

---

## Phase 6 — Digest Generation

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P6-01 | Write `docs/prompts/digest_generation.md` (prompt template) | Codex | `[x]` | P0-06 |
| P6-02 | Create `src/output/generate_digest.py` (query posts + topics, call LLM, write output) | Codex | `[x]` | P4-06, P1-05 |
| P6-03 | Implement week_label computation (ISO week format `YYYY-WXX`) | Codex | `[x]` | P6-02 |
| P6-04 | Implement digest output to `data/output/digests/YYYY-WXX.md` | Codex | `[x]` | P6-02 |
| P6-05 | Implement digest storage in `digests` table | Codex | `[x]` | P6-02 |
| P6-06 | Create `systemd/telegram-digest.service` | Codex | `[x]` | P6-02 |
| P6-07 | Create `systemd/telegram-digest.timer` (Monday 09:00) | Codex | `[x]` | P6-06 |

**Phase 6 Review Criteria:**
- Digest file created at correct path with correct week label.
- Digest stored in DB with correct week_label.
- Prompt loaded from file; not hardcoded in Python.
- LLM response is valid Markdown (basic structure check).

---

## Phase 7 — Recommendations

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P7-01 | Write `docs/prompts/recommendations.md` (prompt template) | Codex | `[x]` | P0-06 |
| P7-02 | Create `src/output/generate_recommendations.py` | Codex | `[x]` | P6-02, P1-05 |
| P7-03 | Implement recurring topic query (topics appearing in last 4 weeks) | Codex | `[x]` | P7-02 |
| P7-04 | Implement project context loading from `projects` table | Codex | `[x]` | P7-02 |
| P7-05 | Implement output to `data/output/recommendations/YYYY-WXX.md` | Codex | `[x]` | P7-02 |
| P7-06 | Wire recommendations generation into `digest` subcommand | Codex | `[x]` | P7-02 |

**Phase 7 Review Criteria:**
- Recommendations reference topics from this and prior weeks.
- Output Markdown conforms to format defined in prompt template.
- `projects` table is loaded (even if empty; graceful no-op).

---

## Phase 8 — Project Insight Mapping

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P8-01 | Write `docs/prompts/project_insights.md` (prompt template) | Codex | `[x]` | P0-06 |
| P8-02 | Create `src/output/map_project_insights.py` | Codex | `[x]` | P3-05, P1-05 |
| P8-03 | Implement FTS5 keyword search against current week's posts per project | Codex | `[x]` | P8-02 |
| P8-04 | Implement relevance scoring (keyword overlap + view_count weighting) | Codex | `[x]` | P8-02 |
| P8-05 | Implement batched LLM call for relevance rationale per project | Codex | `[x]` | P8-02 |
| P8-06 | Write results to `post_project_links` | Codex | `[x]` | P8-05 |
| P8-07 | Append project insights section to current week's digest file | Codex | `[x]` | P8-06 |

**Phase 8 Review Criteria:**
- FTS5 query returns plausible matches for test projects.
- LLM called once per project (batched excerpts), not once per post.
- `post_project_links` populated correctly.
- Digest file extended, not replaced.

---

## Phase 9 — Hardening

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P9-01 | Add retry logic to OpenClaw WS client (max 3 attempts, exponential backoff) | Codex | `[x]` | P1-05 |
| P9-02 | Add `FloodWaitError` handling with configurable max wait ceiling | Codex | `[x]` | P2-03 |
| P9-03 | Add structured logging throughout all pipeline stages | Codex | `[x]` | All prior |
| P9-04 | Add healthcheck script (`scripts/healthcheck.sh`) validating DB, gateway, session | Codex | `[x]` | All prior |
| P9-05 | Add graceful shutdown handling (SIGTERM) in main process | Codex | `[x]` | P1-07 |
| P9-06 | Validate all systemd units with `systemd-analyze verify` | Codex | `[x]` | P5-03, P6-06 |
| P9-07 | Ensure DB WAL mode enabled for concurrent reads during timer runs | Codex | `[x]` | P1-04 |
| P9-08 | Set DB file permissions to 640, owner oc_you:oc_you | Codex | `[x]` | P1-09 |

---

## Phase 10 — GitHub Integration

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P10-01 | Add `github_repo`, `last_commit_at`, `github_synced_at` columns to `projects` table via idempotent migration in `src/db/migrate.py` | Codex | `[x]` | P1-04 |
| P10-02 | Create `src/integrations/__init__.py` (empty) | Codex | `[x]` | P1-02 |
| P10-03 | Create `src/integrations/github_sync.py` — fetches all repos for GITHUB_USERNAME, weekly commit activity, languages and topics per repo; syncs to `projects` table | Codex | `[x]` | P10-01 |
| P10-04 | Create `src/integrations/github_crossref.py` — matches repo languages/topics against Telegram topic clusters; returns per-repo relevance map | Codex | `[x]` | P10-03 |
| P10-05 | Write `docs/prompts/github_insights.md` — LLM prompt for retroactive insight (posts × project relevance) | Codex | `[x]` | P10-03 |
| P10-06 | Create `src/output/generate_insight.py` — FTS5 search posts for each project over configurable lookback window; batched LLM call; outputs `data/output/insights/YYYY-WXX.md` | Codex | `[x]` | P10-04, P10-05 |
| P10-07 | Add `github-projects` section to `src/output/generate_digest.py` — calls github_sync + crossref, appends "## Your Projects × Telegram" to digest | Codex | `[x]` | P10-04 |
| P10-08 | Add `insight` subcommand to `src/main.py` with `--since-bootstrap` flag (lookback 90 days) and `--weeks N` flag | Codex | `[x]` | P10-06 |

**Phase 10 Review Criteria:**
- `github_sync.py` reads GITHUB_USERNAME and GITHUB_TOKEN from os.environ (token optional, graceful degradation to unauthenticated).
- No credentials hardcoded anywhere.
- `projects` table populated from GitHub without wiping manually added rows (INSERT OR IGNORE on name).
- Digest appends GitHub section without replacing existing content.
- `insight` subcommand runs without error even if `projects` table is empty.
- All HTTP calls to GitHub API have error handling (rate limit, 404, network error).

---

## Phase 14 — Architecture Quick Wins (from review 2026-03-17)

Source: `docs/reviews/architecture-modernization-review-2026-03-17.md`, Section 6 (Quick wins).

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P14-01 | Fix `_fetch_topics_this_week()` in `src/output/generate_study_plan.py` to filter by current week bounds — add `week_label` param, join `post_topics` → `posts` with `WHERE posts.posted_at >= ? AND posts.posted_at < ?` (same pattern as `_fetch_top_posts`). Pass `week_label` at call site (line 257). | Codex | `[x]` | P13 |
| P14-02 | Fix `_split_keywords()` in `src/output/map_project_insights.py` to parse JSON-encoded arrays first (try `json.loads(keywords)`), falling back to comma-split only when the value is not valid JSON. `github_sync.py` stores keywords as `json.dumps(list)` but `_split_keywords` splits on commas — they disagree. | Codex | `[x]` | P14-01 |
| P14-03 | Fix `_extract_recommendation_labels()` in `src/output/generate_recommendations.py` (line 75) to match both `## N.` and `### N.` heading shapes. Current regex `^###\s+\d+\.\s+` misses `##`-level headings that the LLM actually generates. Pattern should be: `^##\s+\d+\.\s+(.+?)\s*$` (accepts both levels). | Codex | `[x]` | P14-01 |
| P14-04 | Strengthen digest validation in `src/output/generate_digest.py` (line 288): after the existing heading check, also assert that all five required subsections are present — `### Overview`, `### Top Topics`, `### Signal Posts`, `### Noise Patterns`, `### One Thing to Act On`. Log a `WARNING` for each missing section (do not raise, just warn). | Codex | `[x]` | P14-01 |
| P14-05 | Strengthen recommendations validation in `src/output/generate_recommendations.py` (line 241): after the heading check, assert that at least one `### [N].` or `## [N].` recommendation block is present. Log `WARNING` if none found. | Codex | `[x]` | P14-03 |

**Phase 14 Review Criteria:**
- `generate_study_plan` uses date-bounded topic query; running it in week X returns only topics active that week.
- `_split_keywords` correctly parses both `'["python","ml"]'` (JSON) and `'python, ml'` (CSV) inputs.
- `_extract_recommendation_labels` returns labels from `## 1. Foo` headings (not only `### 1. Foo`).
- Digest generation logs a WARNING for each missing required section, not just for a mismatched heading.
- Recommendations generation logs a WARNING when zero recommendation blocks are found in the output.
- No new external dependencies introduced.
- All changed functions have correct type annotations consistent with the rest of the file.

---

## Phase 15 — Short-term Improvements + Code Consolidation (from review 2026-03-17)

Source: `docs/reviews/architecture-modernization-review-2026-03-17.md`, Section 6 (Short-term) + Section 7 (Concrete Refactoring suggestions 2, 5, 6, 11, 12).

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P15-01 | Fix project insights delivery in `src/output/map_project_insights.py`: instead of appending a free-text block after the fact (`_append_digest_project_insights`, line 217), build the `## Project Insights` section as a structured part of the main report assembly inside `run_map_project_insights()` before the file is written. The section must use a consistent template: `### {project_name}` heading + bullet notes. Remove the post-hoc file-append path. | Codex | `[x]` | P14 |
| P15-02 | Extract a `src/bot/telegram_delivery.py` module with three public functions: `send_text(chat_id, text, token)`, `send_document(chat_id, file_path, caption, token)`, `send_report_preview(chat_id, title, summary_lines, week_label, token)`. Replace all inline chunking + HTTP send logic in `src/bot/handlers.py` (lines 52+), `src/output/generate_digest.py` (lines 87+), and `src/output/generate_study_plan.py` (lines 206+) with calls to this module. No new external dependencies — use `urllib` only. | Codex | `[x]` | P15-01 |
| P15-03 | Add `message_url` column to `raw_posts` table via idempotent migration in `src/db/migrate.py`. Populate it during ingestion: `https://t.me/{channel_username}/{message_id}` for public channels, `None` for private. Update `src/ingestion/bootstrap_ingest.py` (line 46) and `src/ingestion/incremental_ingest.py` to set this column on insert. Pass `message_url` through `posts` view/query so report assembly can reference it. | Codex | `[x]` | P15-01 |
| P15-04 | Move the duplicated `_extract_markdown_section(text, heading)` helper into a new `src/output/report_utils.py` module. Remove the local copies from `src/output/generate_digest.py` (line 60), `src/output/generate_recommendations.py` (line 32), `src/output/generate_study_plan.py` (line 47), and `src/output/map_project_insights.py` (line 38). Import from `report_utils` in each. | Codex | `[x]` | P15-01 |
| P15-05 | Fix `src/output/generate_recommendations.py`: remove `del settings` and any `get_db_path()` calls (line 203 area); accept the `Settings` object as the single source of truth for DB path and config, consistent with all other output modules. | Codex | `[x]` | P15-01 |
| P15-06 | Add a `tests/` directory with focused unit tests (use `unittest`, no new test framework dependencies): `tests/test_report_utils.py` — tests for `_extract_markdown_section` edge cases; `tests/test_keyword_parsing.py` — tests that JSON-encoded and CSV-encoded keyword strings both parse correctly after P14-02; `tests/test_week_bounds.py` — tests for `_week_bounds` and the study plan week query filter. Each test file must be runnable via `python3 -m pytest tests/` or `python3 -m unittest discover tests/`. | Codex | `[x]` | P15-04 |
| P15-07 | Rewrite stale sections in `docs/spec.md` (line 19 area) and `docs/architecture.md` (line 126 area) to reflect the actual runtime: LLM calls go through the `anthropic` Python SDK with `LLM_API_KEY`, not through an OpenClaw WebSocket gateway. Document the current model routing (haiku for topic detection, sonnet for digest/recommendations/study plan) and note that gateway migration is a future option, not current state. | Codex | `[x]` | P15-01 |

**Phase 15 Review Criteria:**
- `map_project_insights.py` no longer appends to an already-written file; insights section is written in the initial output pass.
- `telegram_delivery.py` exists and exports `send_text`, `send_document`, `send_report_preview`; no inline HTTP/chunk logic remains in handlers.py, generate_digest.py, or generate_study_plan.py.
- `raw_posts` has `message_url` column; bootstrap and incremental ingest set it on every insert.
- `_extract_markdown_section` exists only in `report_utils.py`; no local copies remain in other modules.
- `generate_recommendations.py` does not use `del settings` or `get_db_path()`.
- `tests/` directory exists with at least 3 test files; `python3 -m unittest discover tests/` exits 0.
- `docs/spec.md` and `docs/architecture.md` mention `anthropic` SDK, not OpenClaw gateway, as the LLM transport.

---

## Phase 16 — Medium Refactors: Report Schema + Topic Quality (from review 2026-03-17)

Source: `docs/reviews/architecture-modernization-review-2026-03-17.md`, Sections 4.2, 4.3, 6 (Medium refactor), Section 7 (suggestions 1, 7, 8, 9).

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P16-01 | Create `src/output/report_schema.py` with a `ResearchReport` dataclass (or `TypedDict`) matching this shape: `meta` (week_label, date_range, generated_at, post_count, channel_count), `executive_summary` (list[str] bullets), `key_findings` (list[dict] with title, body, evidence_ids), `sections` (list[dict] with heading, body), `evidence` (list[dict] with id `S1..Sn`, channel, date, excerpt, url), `project_relevance` (list[dict] with name, score, notes), `confidence_notes` (str). No rendering logic in this file — schema only. | Codex | `[x]` | P15 |
| P16-02 | Update `src/output/generate_digest.py` to produce a `ResearchReport` JSON object first (`report.json` in `data/output/digests/`), then render Markdown from the structured object. The LLM prompt should request JSON output (update `docs/prompts/digest_generation.md` to specify JSON schema). Validate with `report_schema.py`. Store `content_json` in the `digests` table (add column via idempotent migration). The existing Markdown file output path must still be produced (render from JSON). | Codex | `[x]` | P16-01 |
| P16-03 | Replace the raw `dict` return of `run_digest()` in `src/output/generate_digest.py` (line 196) with a typed `DigestResult` dataclass: fields `week_label: str`, `output_path: str`, `post_count: int`, `json_path: str`. Update all call sites in `src/main.py` and `src/bot/handlers.py` to use the typed result. | Codex | `[x]` | P16-02 |
| P16-04 | Improve multilingual topic detection in `src/processing/cluster.py` (line 79): replace the English-only `stop_words="english"` in `TfidfVectorizer` with a combined stopword list covering Russian and English (use `sklearn`'s built-in lists plus a hardcoded Russian stopword list — no new NLP library). In `src/processing/detect_topics.py` (line 15), replace the ASCII-only tokenizer with a Unicode-aware word tokenizer (`re.findall(r'\b\w+\b', text)` with `re.UNICODE` flag). Log the ratio of posts falling into "Unlabeled" bucket after each clustering run. | Codex | `[x]` | P16-01 |
| P16-05 | Persist cluster run diagnostics in `src/processing/cluster.py` (line 93): after each clustering run, insert a row into a new `cluster_runs` table (add via migration: `id`, `run_at`, `post_count`, `cluster_count`, `unlabeled_count`, `inertia`, `silhouette_score` nullable). This makes topic quality debuggable over time without re-running the pipeline. | Codex | `[x]` | P16-01 |
| P16-06 | Add JSON schema validation in `src/processing/detect_topics.py` (line 212) and `src/output/map_project_insights.py` (line 287) around all `complete_json()` consumer call sites: after parsing the LLM JSON response, assert that required keys are present (log WARNING and fall back gracefully if not, do not crash). | Codex | `[x]` | P16-01 |

**Phase 16 Review Criteria:**
- `report_schema.py` exists and imports cleanly; `ResearchReport` can be instantiated with sample data.
- `generate_digest.py` writes a `YYYY-WXX.json` file alongside the `.md`; JSON validates against `ResearchReport`.
- `run_digest()` returns a `DigestResult` dataclass, not a plain dict.
- Topic clustering uses a combined Russian+English stopword list; `detect_topics.py` tokenizer is Unicode-aware.
- After a clustering run, a row is inserted into `cluster_runs` table.
- `detect_topics.py` and `map_project_insights.py` do not crash on malformed LLM JSON — log WARNING and return empty/default value.
- No new pip dependencies beyond what is already in `requirements.txt`.

---

## Phase 17 — Larger Redesign: HTML/PDF Renderer + Evidence Appendix (from review 2026-03-17)

Source: `docs/reviews/architecture-modernization-review-2026-03-17.md`, Sections 4.5, 5, 6 (Larger redesign).

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P17-01 | Add `jinja2` and `weasyprint` to `requirements.txt`. Create `src/reporting/` package with: `src/reporting/__init__.py` (empty), `src/reporting/renderer.py` (functions `render_html(report: ResearchReport) -> str` and `render_pdf(report: ResearchReport, output_path: Path) -> Path`), `src/reporting/templates/digest.html.j2` (Jinja2 template: cover section, exec summary, findings, evidence table, project scorecard, confidence/risks, sources appendix). CSS must be inline or in a `<style>` block — no external files. | Codex | `[x]` | P16 |
| P17-02 | Wire PDF rendering into `generate_digest.py`: after producing `YYYY-WXX.json` and `YYYY-WXX.md`, call `render_pdf()` to produce `data/output/digests/YYYY-WXX.pdf`. Log a WARNING (do not crash) if WeasyPrint fails — PDF is optional, Markdown is always the fallback. Store `pdf_path` in the `digests` table (add column via migration). | Codex | `[x]` | P17-01 |
| P17-03 | Update `src/bot/telegram_delivery.py` (`send_report_preview` and add `send_digest_bundle`): when a PDF exists, send a short executive summary text message followed by the PDF as a document attachment via Telegram `sendDocument`. When PDF is absent, fall back to chunked Markdown text. Update `/digest` handler in `src/bot/handlers.py` to use `send_digest_bundle`. | Codex | `[x]` | P17-02 |
| P17-04 | Extend the Jinja2 digest template with a Sources Appendix section: ordered `S1..Sn` list, each entry with channel name, date, excerpt (first 200 chars), and `message_url` (from the `message_url` column added in P15-03). Pull evidence items from `ResearchReport.evidence`. Add a basic topic distribution bar chart rendered as an inline SVG (Python string generation, no matplotlib dependency). | Codex | `[x]` | P17-01 |

**Phase 17 Review Criteria:**
- `src/reporting/` package exists and imports cleanly.
- `render_html(report)` returns a non-empty string containing `<html`.
- `render_pdf(report, path)` produces a file at the given path when WeasyPrint is installed.
- `generate_digest.py` writes `YYYY-WXX.pdf` when rendering succeeds; gracefully skips on WeasyPrint error.
- `/digest` bot command sends PDF as attachment when available, chunked text otherwise.
- Sources appendix lists evidence items with `S1..Sn` ids and `message_url` links.
- Inline SVG bar chart is present in the HTML output.
- `jinja2` and `weasyprint` are pinned in `requirements.txt`.

---

## Prompt Template Tasks (docs/prompts/)

| ID | Task | Owner | Status |
|---|---|---|---|
| PT-01 | `docs/prompts/rubric_discovery.md` — topic labeling prompt | Strategist | `[ ]` |
| PT-02 | `docs/prompts/digest_generation.md` — weekly digest prompt | Strategist | `[ ]` |
| PT-03 | `docs/prompts/recommendations.md` — study recommendations prompt | Strategist | `[ ]` |
| PT-04 | `docs/prompts/project_insights.md` — project relevance prompt | Strategist | `[ ]` |

---

## Task Dependency Graph (Critical Path)

```
P0 (Architecture)
  └─▶ P1 (Scaffold)
        ├─▶ P2 (Bootstrap Ingestion)
        │     └─▶ P3 (Normalization)
        │           └─▶ P4 (Topic Detection)
        │                 └─▶ P5 (Weekly Pipeline)
        │                       └─▶ P6 (Digest)
        │                             ├─▶ P7 (Recommendations)
        │                             └─▶ P8 (Project Mapping)
        │                                   └─▶ P9 (Hardening)
        │                                         └─▶ P10 (GitHub)
        │                                               └─▶ P11 (Bot)
        │                                                     └─▶ P12 (Cost Tracking)
        │                                                           └─▶ P13 (Study Plan)
        │                                                                 └─▶ P14 (Quick Wins)
        │                                                                       └─▶ P15 (Short-term)
        │                                                                             └─▶ P16 (Medium Refactor)
        │                                                                                   └─▶ P17 (PDF Renderer)
        └─▶ P1-05 (LLM Client) ──▶ P4, P6, P7, P8 (all LLM phases)
```

---

## Notes for Codex

- Complete each phase fully before starting the next.
- After each phase, update the status column in this file.
- If a task is blocked, mark `[!]` and note the blocker in a comment below the table.
- Never modify OpenClaw source at `/opt/openclaw/src`.
- Read `/opt/openclaw/src` to understand the gateway wire protocol before implementing `client.py`.
- Session and API credential files go in `/srv/openclaw-you/secrets/`, not in this workspace.

---

## Phase 18 — Focused Intel Redesign

_Owner: codex · Date: 2026-03-21 · Depends on: P17_

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| T18 | Curated projects config (`projects.yaml` + github_sync refactor) | codex | `[x]` | — |
| T19 | New digest format (5 categories, Telegram HTML, no PDF) | codex | `[x]` | T18 |
| T20 | New insights prompt (Implement + Build types, separate message) | codex | `[x]` | T19 |
| T21 | Remove PDF from delivery path, text-primary | codex | `[x]` | T20 |

### T18 — Curated projects config

**Objective:** Replace "all repos" GitHub sync with curated 4-project config. Each project has a context card used by the insights prompt.

**Acceptance Criteria:**
- [ ] `src/config/projects.yaml` exists with 4 projects: gdev-agent, telegram-research-agent, film-school-assistant, ai-workflow-playbook
- [ ] Each project has: `name`, `repo`, `description`, `focus` fields
- [ ] `github_sync.py` reads from `projects.yaml` instead of fetching all user repos
- [ ] Projects table still populated correctly (existing schema unchanged)
- [ ] 12 tests still pass

**Files:**
- Create: `src/config/projects.yaml`
- Modify: `src/integrations/github_sync.py`

---

### T19 — New digest format

**Objective:** Replace 400-700 word essay digest with 5-category Telegram-native format. Target: 1-2 messages (~3500 chars max).

**Acceptance Criteria:**
- [ ] `docs/prompts/digest_generation.md` updated with new 5-category prompt
- [ ] Categories: 🤖 Агенты/подходы, 🛠️ Инструменты, 💡 Идеи, 🧠 Психология/культура, 📰 Индустрия
- [ ] Each category: 1-2 items, format: `<b>Заголовок</b>\nСуть в 2 строки\n<a href="...">источник</a>`
- [ ] Output is Telegram HTML (not MarkdownV2)
- [ ] Total output ≤ 3500 characters
- [ ] `generate_digest.py` passes `parse_mode="HTML"` to send_message
- [ ] 12 tests still pass

**Files:**
- Modify: `docs/prompts/digest_generation.md`
- Modify: `src/output/generate_digest.py`

---

### T20 — New insights prompt (Implement + Build)

**Objective:** Replace generic study recommendations with project-specific insights. Two types: Implement (idea for existing project) and Build (new portfolio idea). Sent as separate message after digest.

**Acceptance Criteria:**
- [ ] `docs/prompts/insights.md` created with Implement/Build format
- [ ] Each insight: type tag + project name + idea title + 3-4 sentence justification + source
- [ ] Max 3 insights total per week
- [ ] `generate_recommendations.py` uses new prompt and reads from `projects.yaml` for project context
- [ ] Weekly automation sends insights as second message, 1 minute after digest
- [ ] 12 tests still pass

**Files:**
- Create: `docs/prompts/insights.md`
- Modify: `src/output/generate_recommendations.py`
- Modify: `src/output/generate_digest.py` (add second message send)

---

### T21 — Remove PDF from delivery path

**Objective:** Text-first delivery. Remove PDF dependency from weekly automation and `/digest` command. PDF generation can remain as dead code for now — just not called automatically.

**Acceptance Criteria:**
- [ ] Weekly digest send uses `send_message(..., parse_mode="HTML")` not `send_digest_bundle()`
- [ ] `/digest` bot command returns formatted HTML text, not PDF bundle
- [ ] No WeasyPrint import errors block the digest pipeline
- [ ] `handle_digest` in `handlers.py` works without PDF file present
- [ ] 12 tests still pass

**Files:**
- Modify: `src/bot/handlers.py`
- Modify: `src/output/generate_digest.py`
