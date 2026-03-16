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
| P4-01 | Create `src/processing/cluster.py` (TF-IDF + K-Means, outputs keyword sets per cluster) | Codex | `[ ]` | P3-01 | Create `src/processing/normalize_posts.py` (reads raw_posts, writes posts) | Codex | `[x]` | P1-04 |
| P4-02 | Implement elbow heuristic or fixed-k config for cluster count | Codex | `[ ]` | P4-01 |
| P4-03 | Create `src/processing/detect_topics.py` (matches clusters to existing topics or creates new via LLM) | Codex | `[ ]` | P4-01, P1-05 |
| P4-04 | Implement overlap check between new cluster keywords and existing topic keywords | Codex | `[ ]` | P4-03 |
| P4-05 | Implement LLM call for new topic label generation using `docs/prompts/rubric_discovery.md` | Codex | `[ ]` | P4-03, P0-06 |
| P4-06 | Write results to `topics` and `post_topics` tables | Codex | `[ ]` | P4-05 |

**Phase 4 Review Criteria:**
- Clusters contain sensible keyword groupings.
- LLM called only for new/unmatched clusters, not for every run.
- Topics table grows incrementally; no duplicates.
- Prompt loaded from `docs/prompts/rubric_discovery.md`, not hardcoded.

---

## Phase 5 — Weekly Incremental Pipeline

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P5-01 | Create `src/ingestion/incremental_ingest.py` (delta pull since MAX(posted_at) per channel) | Codex | `[ ]` | P2-01, P1-04 |
| P5-02 | Wire `ingest` subcommand to run: incremental → normalize → cluster → detect_topics | Codex | `[ ]` | P5-01, P3-06, P4-06 |
| P5-03 | Create `systemd/telegram-ingest.service` | Codex | `[ ]` | P5-02 |
| P5-04 | Create `systemd/telegram-ingest.timer` (Monday 07:00, Persistent=true) | Codex | `[ ]` | P5-03 |
| P5-05 | Create `scripts/run_weekly.sh` (manual trigger for full weekly pipeline) | Codex | `[ ]` | P5-02 |

**Phase 5 Review Criteria:**
- Incremental run after bootstrap fetches only new posts.
- Pipeline steps run in correct order.
- Systemd unit runs as `oc_you`, not root.
- `Persistent=true` on timer (catches missed runs).

---

## Phase 6 — Digest Generation

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P6-01 | Write `docs/prompts/digest_generation.md` (prompt template) | Codex | `[ ]` | P0-06 |
| P6-02 | Create `src/output/generate_digest.py` (query posts + topics, call LLM, write output) | Codex | `[ ]` | P4-06, P1-05 |
| P6-03 | Implement week_label computation (ISO week format `YYYY-WXX`) | Codex | `[ ]` | P6-02 |
| P6-04 | Implement digest output to `data/output/digests/YYYY-WXX.md` | Codex | `[ ]` | P6-02 |
| P6-05 | Implement digest storage in `digests` table | Codex | `[ ]` | P6-02 |
| P6-06 | Create `systemd/telegram-digest.service` | Codex | `[ ]` | P6-02 |
| P6-07 | Create `systemd/telegram-digest.timer` (Monday 09:00) | Codex | `[ ]` | P6-06 |

**Phase 6 Review Criteria:**
- Digest file created at correct path with correct week label.
- Digest stored in DB with correct week_label.
- Prompt loaded from file; not hardcoded in Python.
- LLM response is valid Markdown (basic structure check).

---

## Phase 7 — Recommendations

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P7-01 | Write `docs/prompts/recommendations.md` (prompt template) | Codex | `[ ]` | P0-06 |
| P7-02 | Create `src/output/generate_recommendations.py` | Codex | `[ ]` | P6-02, P1-05 |
| P7-03 | Implement recurring topic query (topics appearing in last 4 weeks) | Codex | `[ ]` | P7-02 |
| P7-04 | Implement project context loading from `projects` table | Codex | `[ ]` | P7-02 |
| P7-05 | Implement output to `data/output/recommendations/YYYY-WXX.md` | Codex | `[ ]` | P7-02 |
| P7-06 | Wire recommendations generation into `digest` subcommand | Codex | `[ ]` | P7-02 |

**Phase 7 Review Criteria:**
- Recommendations reference topics from this and prior weeks.
- Output Markdown conforms to format defined in prompt template.
- `projects` table is loaded (even if empty; graceful no-op).

---

## Phase 8 — Project Insight Mapping

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P8-01 | Write `docs/prompts/project_insights.md` (prompt template) | Codex | `[ ]` | P0-06 |
| P8-02 | Create `src/output/map_project_insights.py` | Codex | `[ ]` | P3-05, P1-05 |
| P8-03 | Implement FTS5 keyword search against current week's posts per project | Codex | `[ ]` | P8-02 |
| P8-04 | Implement relevance scoring (keyword overlap + view_count weighting) | Codex | `[ ]` | P8-02 |
| P8-05 | Implement batched LLM call for relevance rationale per project | Codex | `[ ]` | P8-02 |
| P8-06 | Write results to `post_project_links` | Codex | `[ ]` | P8-05 |
| P8-07 | Append project insights section to current week's digest file | Codex | `[ ]` | P8-06 |

**Phase 8 Review Criteria:**
- FTS5 query returns plausible matches for test projects.
- LLM called once per project (batched excerpts), not once per post.
- `post_project_links` populated correctly.
- Digest file extended, not replaced.

---

## Phase 9 — Hardening

| ID | Task | Owner | Status | Depends On |
|---|---|---|---|---|
| P9-01 | Add retry logic to OpenClaw WS client (max 3 attempts, exponential backoff) | Codex | `[ ]` | P1-05 |
| P9-02 | Add `FloodWaitError` handling with configurable max wait ceiling | Codex | `[ ]` | P2-03 |
| P9-03 | Add structured logging throughout all pipeline stages | Codex | `[ ]` | All prior |
| P9-04 | Add healthcheck script (`scripts/healthcheck.sh`) validating DB, gateway, session | Codex | `[ ]` | All prior |
| P9-05 | Add graceful shutdown handling (SIGTERM) in main process | Codex | `[ ]` | P1-07 |
| P9-06 | Validate all systemd units with `systemd-analyze verify` | Codex | `[ ]` | P5-03, P6-06 |
| P9-07 | Ensure DB WAL mode enabled for concurrent reads during timer runs | Codex | `[ ]` | P1-04 |
| P9-08 | Set DB file permissions to 640, owner oc_you:oc_you | Codex | `[ ]` | P1-09 |

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
