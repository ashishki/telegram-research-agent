# Telegram Research Agent — System Specification

**Version:** 1.1.0
**Date:** 2026-03-30
**Status:** Updated (Phase 19 — Signal Intelligence Redesign)

---

## 1. Executive Summary

The Telegram Research Agent is a private, server-side AI assistant that ingests posts from curated Telegram technology channels, structures the raw stream into persistent knowledge artifacts, and surfaces actionable outputs:

- Weekly digests (what happened, what matters)
- Study recommendations (what to learn next)
- Topic clusters (recurring themes over time)
- Project insight mappings (connections to ongoing work)
- Experiment proposals (ideas worth prototyping)

The system runs on a private VPS. There are no public-facing endpoints. LLM calls go through the `anthropic` Python SDK using `LLM_API_KEY` from the environment. The pipeline is deterministic except where LLM interpretation is explicitly invoked.

---

## 2. Verified Runtime Baseline and Architectural Invariants

### OpenClaw Runtime

| Property | Value |
|---|---|
| Version | 2026.3.13 |
| Commit | 61d171ab0b2fe4abc9afe89c518586274b4b76c2 |
| Binary | `/usr/local/bin/openclaw` |
| Source | `/opt/openclaw/src` (READ-ONLY — never modified) |
| Config | `/srv/openclaw-you/openclaw.json5` |
| Env | `/srv/openclaw-you/.env` |
| State dir | `/srv/openclaw-you/state` |
| Secrets dir | `/srv/openclaw-you/secrets` |
| LLM transport | `anthropic` Python SDK |
| Service | `openclaw-you.service` |

### Invariants That Must Never Be Violated

1. OpenClaw source (`/opt/openclaw/src`) must never be modified.
2. Gateway must remain bound to `127.0.0.1` only, never `0.0.0.0`.
3. Project state must not be stored in `/srv/openclaw-you/state`.
4. All project artifacts must live under `/srv/openclaw-you/workspace/telegram-research-agent`.
5. Secrets must be stored under `/srv/openclaw-you/secrets` with permission `600`.
6. `OPENCLAW_CONFIG_PATH` env var is the config mechanism; the deprecated `--config` flag is not used.

---

## 3. Assumptions and Architecture Decisions

### AD-01: Telegram Ingestion via Telethon (MTProto)

**Decision:** Use [Telethon](https://docs.telethon.dev/) (Python, MTProto protocol) to read channel history as a user account.

**Rationale:**
- The Telegram Bot API cannot read channel history unless the bot is an admin of the channel.
- Public Telegram channels can be read with a regular user account via MTProto without joining them.
- Telethon is the most mature Python MTProto client; it supports async, offset-based pagination, and stable session management.

**Tradeoff:** Requires storing a Telegram user API credential (api_id, api_hash, phone) and a persistent session file. These are security-sensitive and must be isolated in the secrets directory.

**Rejected alternative:** Telegram Bot API — insufficient for reading arbitrary channel history.

### AD-02: SQLite as the Canonical Database

**Decision:** Use SQLite (via Python's `sqlite3` stdlib) as the primary data store for all pipeline stages.

**Rationale:**
- 8 GB RAM / 4-core VPS; no need for a full database server.
- SQLite is file-based, transactional, and requires zero infrastructure.
- Expected data volume: tens of thousands of posts per year — well within SQLite's capable range.
- FTS5 extension enables full-text search without additional tooling.

**Upgrade path:** Schema can be migrated to PostgreSQL without logic changes if volume or concurrency demand it.

**Database location:** `/srv/openclaw-you/workspace/telegram-research-agent/data/agent.db`

### AD-03: LLM Calls via Anthropic Python SDK Directly

**Decision:** LLM calls use the `anthropic` Python SDK. API key loaded from `LLM_API_KEY` env var. Category-specific model routing is implemented in `src/llm/client.py`.

**Rationale:** The OpenClaw gateway at `ws://127.0.0.1:18789` implements a custom TypeScript WebSocket protocol (RequestFrame, EventFrame, session management) designed for the OpenClaw plugin ecosystem — not for external Python clients. No Python SDK exists for this protocol. Implementing a conformant client would be fragile and undocumented. The Anthropic API key is already present in the environment and is the authoritative credential. Direct SDK usage is simpler, tested, and well-documented.

**Credential source:** `/srv/openclaw-you/.env` loaded via `EnvironmentFile=` in systemd. Key: `LLM_API_KEY`.

**Current routing:** `topic_detection` and `project_insights` use Haiku. `digest`, `recommendations`, `study_plan`, `insight`, and `bot_ask` use Sonnet. Environment overrides such as `LLM_MODEL_DIGEST` remain supported.

**Future option:** A gateway migration remains possible later if OpenClaw exposes a stable Python-facing interface, but it is not the current transport.

### AD-04: Deterministic Pipelines, LLM Only Where Necessary

**Decision:** Ingestion, normalization, deduplication, and storage are fully deterministic. LLM is invoked only for:
- Topic label generation (per cluster)
- Rubric/category discovery
- Weekly digest composition
- Study recommendation generation
- Project insight mapping
- Experiment idea generation

**Rationale:** Reduces cost, latency, and non-determinism. Raw Telegram history is never passed wholesale into an LLM.

### AD-05: No Web Server in MVP

**Decision:** No HTTP API, no web frontend in MVP.

**Output artifacts are:**
- Markdown files committed to the repo or written to a designated output directory.
- Future evolution may add a simple read interface.

### AD-06: Systemd Timers for Scheduling

**Decision:** Use systemd `.service` + `.timer` units for all scheduled tasks.

**Rationale:** No additional scheduler (cron, Celery, Airflow) needed; systemd is already present and used for OpenClaw.

### AD-07: Channel Configuration via Config File

**Decision:** Target channel list is defined in a YAML config file (`src/config/channels.yaml`), not hardcoded.

---

## 4. Telegram Ingestion Strategy Options

### Option A: Telethon User Client (MTProto)

- Read public and private (if member) channels directly.
- Supports full history pagination with `iter_messages`.
- Requires API credentials and phone number; produces a `.session` file.
- Best for reading arbitrary channels at scale.

### Option B: Telegram Bot API

- Simple HTTPS-based REST API.
- Can only read channels where the bot is admin.
- No history access; only real-time updates via webhook or polling.
- Unsuitable for bootstrap ingestion or historical analysis.

### Option C: Third-Party Scrapers / Export Tools

- Tools like `telegram-export` or manual JSON exports via Telegram Desktop.
- Non-automated; requires manual re-runs; brittle.
- Acceptable for one-time bootstrap but not for incremental automation.

**Selected:** Option A (Telethon).

---

## 5. Recommended Ingestion Approach

### Bootstrap Phase (one-time)

- Run `scripts/bootstrap_ingest.py` manually after setup.
- Pulls last 90 days of posts from each configured channel.
- Uses Telethon's `iter_messages` with `offset_date` parameter.
- Stores raw posts (JSON fields) into `raw_posts` table with `ingested_at` timestamp.
- Idempotent: skips already-stored `message_id` per channel.

### Incremental Phase (weekly, automated)

- Run by `systemd` timer, weekly on Monday 07:00.
- Pulls posts since `MAX(posted_at)` per channel from the database.
- Same normalization and storage pipeline as bootstrap.
- Triggers downstream processing (topic detection, digest generation) after ingestion completes.

---

## 6. Target System Architecture

```
┌───────────────────────────────────────────────────────┐
│              Telegram Channels (external)              │
└───────────────────────┬───────────────────────────────┘
                        │ MTProto (Telethon)
                        ▼
┌───────────────────────────────────────────────────────┐
│              Ingestion Layer (Python)                  │
│  bootstrap_ingest.py / incremental_ingest.py           │
│  - Pagination, deduplication, raw storage              │
└───────────────────────┬───────────────────────────────┘
                        │ SQLite writes
                        ▼
┌───────────────────────────────────────────────────────┐
│              SQLite Database (agent.db)                │
│  Tables: raw_posts, posts, topics, clusters,           │
│          digests, recommendations, projects            │
└──────┬────────────────┬────────────────────┬──────────┘
       │                │                    │
       ▼                ▼                    ▼
┌──────────────┐ ┌──────────────┐  ┌────────────────────┐
│ Normalizer   │ │ Topic        │  │ Digest Generator   │
│ (Python,     │ │ Detector     │  │ (LLM via           │
│ deterministic│ │ (LLM via     │  │ anthropic SDK)     │
│ )            │ │ anthropic SDK)│ └────────┬───────────┘
└──────┬───────┘ └──────┬───────┘           │
       │                │                   │
       └────────────────┴───────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────┐
│              Output Layer                              │
│  data/output/digests/YYYY-WXX.md                       │
│  data/output/recommendations/YYYY-WXX.md               │
│  data/output/experiments/YYYY-WXX.md                   │
└───────────────────────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────┐
│              Anthropic API via SDK                     │
│              authenticated with LLM_API_KEY            │
└───────────────────────────────────────────────────────┘
```

---

## 7. Data Model Draft

### Table: `raw_posts`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | auto |
| channel_username | TEXT | e.g. `@sometech` |
| channel_id | INTEGER | Telegram internal ID |
| message_id | INTEGER | Telegram message ID |
| posted_at | DATETIME | UTC |
| text | TEXT | raw message text |
| media_type | TEXT | `photo`, `video`, `document`, `none` |
| media_caption | TEXT | if applicable |
| forward_from | TEXT | original channel if forwarded |
| view_count | INTEGER | at time of ingestion |
| raw_json | TEXT | full Telethon message JSON |
| ingested_at | DATETIME | UTC, set on insert |

**Unique constraint:** `(channel_id, message_id)`

---

### Table: `posts`

Normalized, processed view of `raw_posts`.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | auto |
| raw_post_id | INTEGER FK | → raw_posts.id |
| channel_username | TEXT | |
| posted_at | DATETIME | UTC |
| content | TEXT | cleaned text |
| url_count | INTEGER | extracted URL count |
| has_code | BOOLEAN | code block detected |
| language_detected | TEXT | en/ru/other |
| word_count | INTEGER | |
| normalized_at | DATETIME | |
| signal_score | REAL | Composite score 0.0–1.0; written by score_posts.py (Phase 19) |
| bucket | TEXT | `strong`, `watch`, `cultural`, or `noise` (Phase 19) |
| project_matches | TEXT | JSON list of matching project names (Phase 19) |
| interpretation | TEXT | Free-text scoring rationale (Phase 19) |

---

### Table: `topics`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| label | TEXT | LLM-generated label |
| description | TEXT | LLM summary |
| first_seen | DATETIME | |
| last_seen | DATETIME | |
| post_count | INTEGER | |

---

### Table: `post_topics`

| Column | Type | Notes |
|---|---|---|
| post_id | INTEGER FK | → posts.id |
| topic_id | INTEGER FK | → topics.id |
| confidence | REAL | 0.0–1.0 |

---

### Table: `digests`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| week_label | TEXT | e.g. `2026-W11` |
| generated_at | DATETIME | |
| content_md | TEXT | full Markdown digest |
| post_count | INTEGER | posts included |

---

### Table: `recommendations`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| week_label | TEXT | |
| generated_at | DATETIME | |
| content_md | TEXT | Markdown recommendations |

---

### Table: `projects`

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | project identifier |
| description | TEXT | free text |
| keywords | TEXT | comma-separated |
| active | BOOLEAN | |

---

### Table: `post_project_links`

| Column | Type | Notes |
|---|---|---|
| post_id | INTEGER FK | |
| project_id | INTEGER FK | |
| relevance_score | REAL | |
| note | TEXT | LLM-generated rationale |
| tier | TEXT | Inference tier from three-tier project insight mapping (Phase 19) |
| rationale | TEXT | LLM-generated relevance rationale (Phase 19) |

---

### Table: `quality_metrics` — added Phase 19

Observability table for per-week scoring statistics. Created by migration (Phase 19); population is a future step.

| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | auto |
| week_label | TEXT UNIQUE | e.g. `2026-W13` |
| computed_at | TEXT | UTC ISO timestamp |
| total_posts | INTEGER | |
| strong_count | INTEGER | |
| watch_count | INTEGER | |
| cultural_count | INTEGER | |
| noise_count | INTEGER | |
| avg_signal_score | REAL | |
| project_match_count | INTEGER | |
| output_word_count | INTEGER | |

---

## 8. Bootstrap Ingestion Pipeline

```
bootstrap_ingest.py
│
├── Load channel list from src/config/channels.yaml
├── Connect to Telegram via Telethon
│   └── Session file from /srv/openclaw-you/secrets/telegram.session
│
├── For each channel:
│   ├── Resolve channel entity
│   ├── Compute cutoff_date = NOW - 90 days
│   ├── Paginate via iter_messages(offset_date=cutoff_date)
│   ├── For each message:
│   │   ├── Check if (channel_id, message_id) exists in raw_posts → SKIP if yes
│   │   └── Insert into raw_posts (text, media_type, view_count, raw_json, ...)
│   └── Log progress: channel, count inserted, count skipped
│
└── Print summary: total inserted, total skipped, duration
```

**Idempotency guarantee:** The unique constraint on `(channel_id, message_id)` ensures re-runs are safe.

---

## 9. Weekly Incremental Ingestion Pipeline

```
incremental_ingest.py
│
├── Load channel list
├── Connect to Telegram via Telethon
│
├── For each channel:
│   ├── Query: SELECT MAX(posted_at) FROM raw_posts WHERE channel_username = ?
│   ├── If no previous posts: fall back to 7-day window
│   ├── Paginate since last_post_date
│   └── Insert new posts (same dedup logic as bootstrap)
│
├── On success: trigger normalize_posts.py
├── On success: trigger detect_topics.py
└── On success: trigger generate_digest.py
```

Triggered by: `telegram-ingest.timer` (Monday 07:00)

---

## 10. Rubric Discovery Mechanism

Rubrics are persistent topic categories that emerge from the data over time.

**Process:**

1. After normalization, cluster posts by TF-IDF similarity (deterministic, no LLM).
2. For each cluster: extract top N keywords.
3. Submit keyword sets to LLM via the `anthropic` SDK for label and description generation.
4. Store generated rubrics in `topics` table.
5. On subsequent runs: compare new clusters to existing rubrics; extend or create new ones.

**LLM prompt contract:**
- Input: `{top_keywords: [...], sample_posts: [...3 excerpts...], existing_rubrics: [...]}`
- Output (structured JSON): `{label: str, description: str, is_new: bool, merged_into: str | null}`

**Why TF-IDF first:** Prevents sending raw post corpus to LLM. Keyword extraction is deterministic. LLM only labels, does not cluster.

---

## 11. Weekly Digest Pipeline

```
generate_digest.py
│
├── Determine week_label (ISO week of current date)
├── Query pre-scored posts via _fetch_scored_posts() — posts must already have
│   signal_score and bucket set by score_posts.py
├── Group posts by bucket: strong, watch, cultural, noise
├── Build scored_posts list: strong + watch + cultural (≤6 posts total)
├── Build noise_summary from noise bucket posts + topic counts
│
├── Assemble digest prompt:
│   ├── {scored_posts}: JSON list of up to 6 pre-scored posts with bucket labels
│   ├── {noise_count}: integer count of noise-bucket posts
│   ├── {noise_summary}: text summary of filtered content
│   ├── {topic_summary}: top topics with post counts
│   ├── {week_label}, {date_range}, {total_post_count}, {channel_count}
│
├── Submit to LLM via anthropic SDK
├── Receive HTML digest response
│
├── Insert into digests table
└── Write to data/output/digests/YYYY-WXX.md
```

**LLM prompt contract (updated Phase 19 / T27):**
- Input: `{week_label: str, date_range: str, total_post_count: int, channel_count: int, scored_posts: [...], noise_count: int, topic_summary: [...], noise_summary: str}`
- Output: HTML document with value-based bucket sections — **Strong Signal / For My Projects / Watch List / Filtered Out** (replaces the previous 5-section taxonomy)

_Note: the pre-Phase 19 contract `{week: str, topics: [...], notable_posts: [...], signal_threshold: int}` is no longer active._

---

## 12. Learning Recommendation Generation

```
generate_recommendations.py
│
├── Load this week's digest (from DB or file)
├── Load active projects from projects table
├── Query recurring topics (last 4 weeks, min 3 appearances)
│
├── Assemble recommendation prompt:
│   ├── This week's top topics
│   ├── Recurring topics (multi-week)
│   ├── Active projects and their keywords
│   └── Instruction: suggest 3-5 concrete study items with rationale
│
├── Submit to LLM via anthropic SDK
├── Receive structured Markdown
│
├── Insert into recommendations table
└── Write to data/output/recommendations/YYYY-WXX.md
```

**Output format (enforced via prompt):**
```markdown
## Study Recommendations — 2026-W11

### 1. [Topic Name]
**Why:** ...
**Resources hint:** ...
**Effort:** 2-3 hours

### 2. ...
```

---

## 13. Project Insight Mapping

```
map_project_insights.py
│
├── Load active projects from projects table
├── For each project:
│   ├── Retrieve project keywords
│   ├── Query posts from last 7 days matching keywords (SQLite FTS5)
│   ├── Score matches by keyword overlap + view_count
│   └── Insert top 10 matches into post_project_links
│
├── For linked posts: submit to LLM for relevance rationale
│   └── Prompt: "Given project X, explain how this post is relevant"
│
└── Write structured project insights report to `data/output/project_insights/YYYY-WXX.md`
```

**Keyword match is deterministic (FTS5). LLM only writes the rationale sentence.**

---

## 14. Operational Model

### Services

| Unit | Type | Purpose |
|---|---|---|
| `openclaw-you.service` | Service | OpenClaw runtime on host (not used for current LLM transport) |
| `telegram-ingest.service` | Service | Runs incremental ingestion |
| `telegram-digest.service` | Service | Runs digest + recommendations |

### Timers

| Unit | Schedule | Triggers |
|---|---|---|
| `telegram-ingest.timer` | Monday 07:00 | `telegram-ingest.service` |
| `telegram-digest.timer` | Monday 09:00 | `telegram-digest.service` |

Two-hour gap ensures ingestion completes before digest runs.

### Log Management

All services log to journald. Access via:

```bash
journalctl -u telegram-ingest.service -f
journalctl -u telegram-digest.service --since "1 week ago"
```

### Output Artifacts

```
data/output/
├── digests/
│   └── YYYY-WXX.md
├── recommendations/
│   └── YYYY-WXX.md
├── project_insights/
│   └── YYYY-WXX.md
└── experiments/
    └── YYYY-WXX.md
```

---

## 15. Security Model

See `docs/ops-security.md` for full detail.

Summary:
- All credentials in `/srv/openclaw-you/secrets/` with mode `600`, owned by `oc_you`.
- No secrets in source code or config files committed to any repo.
- No public network ports opened.
- OpenClaw gateway bound to `127.0.0.1` only.
- Telethon session file (`telegram.session`) stored in secrets dir, never in project workspace.
- SQLite database not world-readable (mode `640`).
- Systemd services run as `oc_you` user.

---

## 16. AI Development Workflow

See `docs/dev-cycle.md` for full process.

Summary:
1. **Strategist (Claude):** produces spec, architecture, task graph.
2. **Codex Implementer:** implements tasks from task graph.
3. **Claude Reviewer:** reviews each phase output against spec and architecture.
4. **Codex Fixer:** applies review corrections.
5. Living docs (`docs/*.md`) updated after each phase.

---

## 17. Phase Implementation Plan

| Phase | Name | Deliverables |
|---|---|---|
| 0 | Architecture | All 5 living docs written |
| 1 | Project Scaffold | `src/` structure, config loader, DB schema migration, Anthropic client wrapper |
| 2 | Bootstrap Ingestion | `bootstrap_ingest.py`, Telethon client, raw_posts table |
| 3 | Normalization | `normalize_posts.py`, posts table population |
| 4 | Topic Detection | TF-IDF clustering, LLM rubric labeling, topics + post_topics tables |
| 5 | Weekly Pipeline | `incremental_ingest.py`, systemd units |
| 6 | Digest Generation | `generate_digest.py`, digest output files |
| 7 | Recommendations | `generate_recommendations.py`, recommendations output |
| 8 | Project Mapping | `projects` table, `map_project_insights.py` |
| 9 | Hardening | Error handling, retry logic, monitoring, log rotation |

---

## 18. Codex Task Graph

See `docs/tasks.md` for full graph with dependencies.

---

## 19. Repository Artifact Structure

```
/srv/openclaw-you/workspace/telegram-research-agent/
├── docs/
│   ├── spec.md              ← this file
│   ├── architecture.md
│   ├── tasks.md
│   ├── dev-cycle.md
│   └── ops-security.md
├── docs/prompts/
│   ├── rubric_discovery.md
│   ├── digest_generation.md
│   ├── recommendations.md
│   └── project_insights.md
├── src/
│   ├── config/
│   │   └── channels.yaml
│   ├── db/
│   │   ├── schema.sql
│   │   └── migrate.py
│   ├── ingestion/
│   │   ├── bootstrap_ingest.py
│   │   └── incremental_ingest.py
│   ├── processing/
│   │   ├── normalize_posts.py
│   │   ├── detect_topics.py
│   │   └── cluster.py
│   ├── output/
│   │   ├── generate_digest.py
│   │   ├── generate_recommendations.py
│   │   └── map_project_insights.py
│   ├── llm/
│   │   └── client.py          ← Anthropic SDK client wrapper
│   └── main.py
├── scripts/
│   ├── setup.sh
│   ├── run_bootstrap.sh
│   └── run_weekly.sh
├── systemd/
│   ├── telegram-ingest.service
│   ├── telegram-ingest.timer
│   ├── telegram-digest.service
│   └── telegram-digest.timer
└── data/
    ├── agent.db               ← SQLite (gitignored)
    └── output/
        ├── digests/
        ├── recommendations/
        ├── project_insights/
        └── experiments/
```

---

## 20. Claude Review Checklist

Per phase, the Claude Reviewer must verify:

**Architecture adherence:**
- [ ] No writes to `/srv/openclaw-you/state`
- [ ] No modifications to `/opt/openclaw/src`
- [ ] All LLM calls via `anthropic` SDK using `LLM_API_KEY`
- [ ] No hardcoded secrets in source code
- [ ] Secrets referenced from environment variables or secrets directory

**Data integrity:**
- [ ] Deduplication enforced at DB layer (unique constraints)
- [ ] All DB writes are transactional
- [ ] Bootstrap is idempotent

**Security:**
- [ ] No world-readable files containing sensitive data
- [ ] Systemd services run as `oc_you`, not root
- [ ] No external ports opened

**Code quality:**
- [ ] Error handling present for Telegram API calls and LLM calls
- [ ] Logging present and structured
- [ ] No raw Telegram corpus passed to LLM in a single call

**Documentation:**
- [ ] Living docs updated after phase
- [ ] New modules have corresponding task entries marked complete

---

## 21. Final Recommendations

1. **Start with Phase 1 (scaffold) before any network calls.** Validate schema migration and the Anthropic client before touching Telegram.

2. **Treat the Telethon session as a secret.** One leaked session = full account read access. Store in `/srv/openclaw-you/secrets/telegram.session`, never in the workspace.

3. **Validate the Anthropic client in isolation first.** Write a standalone test that sends a minimal prompt and receives a response before wiring it into any pipeline.

4. **Bootstrap ingestion is one-shot; make it resumable.** If it fails midway, re-running must not duplicate posts. The unique constraint handles this, but logging the last successfully ingested message ID per channel is recommended.

5. **Keep LLM prompts in `docs/prompts/`.** This makes them reviewable, versionable, and separable from code. Codex loads prompt templates; it does not inline them.

6. **Don't generate experiments until digest and recommendations are validated.** Experiment generation depends on quality upstream output.

7. **Phase 9 (hardening) is not optional.** Retry logic for Telegram rate limits (FloodWaitError) is essential for production operation.
