# Telegram Research Agent — Architecture

**Version:** 1.0.0
**Date:** 2026-03-16
**Status:** Baseline

---

## Overview

This document defines the structural and behavioral architecture of the Telegram Research Agent. It is the authoritative reference for component boundaries, data flow, contracts, and integration points.

It does not contain implementation code. It is the contract that Codex implements and Claude reviews against.

---

## Component Map

```
┌────────────────────────────────────────────────────────────────┐
│                     Runtime Host (VPS)                         │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           Anthropic Python SDK client                    │  │
│  │           authenticated with LLM_API_KEY                 │  │
│  └─────────────────────────┬────────────────────────────────┘  │
│                            │ HTTPS API calls                  │
│  ┌─────────────────────────┴────────────────────────────────┐  │
│  │           Telegram Research Agent                        │  │
│  │                                                          │  │
│  │  ┌─────────────┐    ┌──────────────┐  ┌──────────────┐  │  │
│  │  │  Ingestion  │    │  Processing  │  │   Output     │  │  │
│  │  │  Layer      │───▶│  Layer       │─▶│   Layer      │  │  │
│  │  └─────────────┘    └──────────────┘  └──────────────┘  │  │
│  │         │                  │                  │           │  │
│  │         └──────────────────┴──────────────────┘           │  │
│  │                            │                              │  │
│  │                     ┌──────┴──────┐                       │  │
│  │                     │  agent.db   │                       │  │
│  │                     │  (SQLite)   │                       │  │
│  │                     └─────────────┘                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  /srv/openclaw-you/secrets/                              │  │
│  │    telegram.session  (600)                               │  │
│  │    telegram_api.env  (600)                               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
         │
         │ MTProto (outbound, Telegram servers)
         ▼
  Telegram API (external)
```

---

## Layer Definitions

### Ingestion Layer

**Responsibility:** Retrieve raw Telegram posts and store them verbatim.

**Components:**
- `src/ingestion/bootstrap_ingest.py` — one-time historical pull
- `src/ingestion/incremental_ingest.py` — weekly delta pull
- Telethon client (MTProto)

**Contracts:**
- Must not perform any transformation beyond extracting fields.
- Must write to `raw_posts` table only.
- Must deduplicate on `(channel_id, message_id)`.
- Must log inserted count and skipped count per channel.
- Must handle `FloodWaitError` by sleeping the required time, then retrying.
- Must not call the LLM transport from ingestion.

**Failure behavior:**
- On Telegram connection failure: log error, exit with code 1. Timer will retry next scheduled run.
- On DB write failure: rollback transaction, log error, continue to next channel.

---

### Processing Layer

**Responsibility:** Transform raw posts into structured, analyzable data. Invoke LLM only for interpretation tasks.

**Sub-components:**

#### Normalizer (`src/processing/normalize_posts.py`)

- Reads unprocessed rows from `raw_posts` (those with no corresponding entry in `posts`).
- Cleans text: strip Markdown artifacts, normalize whitespace.
- Extracts metadata: URL count, code block presence, word count.
- Detects language (lightweight heuristic; no LLM).
- Writes to `posts` table.
- **No LLM calls.**

#### Clusterer (`src/processing/cluster.py`)

- Reads from `posts` for the current processing window.
- Builds TF-IDF matrix over `content` field.
- Runs K-Means clustering (k determined by elbow heuristic or fixed MVP config).
- Outputs: cluster ID → list of post IDs, cluster → top keywords.
- **No LLM calls.**
- Stores cluster assignments temporarily in memory; passed to topic detector.

#### Topic Detector (`src/processing/detect_topics.py`)

- Receives cluster keyword sets from clusterer.
- Loads existing topics from DB.
- For each new cluster:
  - If keywords overlap significantly with existing topic: assign cluster posts to that topic.
  - If no match: call LLM to generate new topic label + description.
- Writes to `topics` and `post_topics` tables.
- **LLM calls: topic labeling only (keyword sets, not full post text).**

---

### Output Layer

**Responsibility:** Synthesize processed data into human-readable artifacts using LLM reasoning.

**Components:**

#### Digest Generator (`src/output/generate_digest.py`)

- Queries posts + topics for the target week.
- Assembles structured prompt from `docs/prompts/digest_generation.md`.
- Calls LLM via the Anthropic Python SDK.
- Parses response as Markdown.
- Writes to `digests` table and `data/output/digests/YYYY-WXX.md`.

#### Recommendation Generator (`src/output/generate_recommendations.py`)

- Reads current week's digest from DB.
- Reads recurring topics (last 4 weeks).
- Reads active projects from `projects` table.
- Calls LLM via the Anthropic Python SDK.
- Writes to `recommendations` table and `data/output/recommendations/YYYY-WXX.md`.

#### Project Insight Mapper (`src/output/map_project_insights.py`)

- For each active project: FTS5 keyword search against current week's posts.
- Scores and ranks matches.
- Calls LLM for relevance rationale (one call per project, batched post excerpts).
- Writes to `post_project_links` table.
- Calls LLM via the Anthropic Python SDK.
- Writes `post_project_links` and `data/output/project_insights/YYYY-WXX.md`.

---

### LLM Client (`src/llm/client.py`)

**Responsibility:** Encapsulate all LLM calls via the Anthropic Python SDK.

**Interface contract:**

```python
def complete(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    """
    Send a completion request to the Anthropic API.
    Returns the response text.
    Raises LLMError on failure.
    """

def complete_json(prompt: str, system: str = "", schema: dict = None) -> dict:
    """
    Send a request expecting a JSON response.
    Parses response as JSON. Raises LLMError or LLMSchemaError on failure.
    """
```

**Behavior:**
- Uses `anthropic.Anthropic(api_key=os.environ["LLM_API_KEY"])`.
- Category routing from `src/llm/client.py` with env overrides such as `LLM_MODEL_DIGEST`.
- Implements retry with exponential backoff (max 3 attempts) on rate limit / 5xx errors.
- Logs every call at DEBUG level (prompt length, model, response length).
- Never logs the API key or full response content at INFO or above.

**Configuration:**
- `LLM_API_KEY` — Anthropic API key (from `/srv/openclaw-you/.env`)
- `LLM_API_KEY` — Anthropic API key
- `LLM_MODEL_<CATEGORY>` — optional per-category override

---

### Database Layer (`src/db/`)

**Schema file:** `src/db/schema.sql`
**Migration runner:** `src/db/migrate.py`

**Rules:**
- All schema changes go through `schema.sql` and `migrate.py`.
- Migration is idempotent (uses `CREATE TABLE IF NOT EXISTS`, column existence checks).
- Database file path: configured via `AGENT_DB_PATH` environment variable.
- Default: `data/agent.db` relative to project root.
- FTS5 virtual table created for `posts.content` to support keyword search.

---

### Configuration (`src/config/`)

**`channels.yaml` schema:**

```yaml
channels:
  - username: "@channelname"
    label: "Human-readable label"
    language: "en"          # en | ru | mixed
    priority: high          # high | medium | low
    active: true
```

**`settings.py`:**
- Reads environment variables.
- Provides typed config object.
- No secrets in this file.

---

## Data Flow: Weekly Cycle

```
Monday 07:00
    │
    ▼
telegram-ingest.service
    │
    ├─ incremental_ingest.py
    │   ├─ Fetch new posts (Telethon)
    │   └─ Write → raw_posts
    │
    ├─ normalize_posts.py
    │   └─ Read raw_posts → Write → posts
    │
    ├─ cluster.py → detect_topics.py
    │   ├─ TF-IDF cluster
    │   └─ LLM label → Write → topics, post_topics
    │
    └─ [exit 0 → triggers telegram-digest.service via After= dependency]

Monday 09:00
    │
    ▼
telegram-digest.service
    │
    ├─ generate_digest.py
    │   ├─ Query posts + topics (this week)
    │   ├─ LLM → Markdown digest
    │   └─ Write → digests table + data/output/digests/
    │
    ├─ generate_recommendations.py
    │   ├─ LLM → Markdown recommendations
    │   └─ Write → recommendations table + data/output/recommendations/
    │
    └─ map_project_insights.py
        ├─ FTS5 keyword match
        ├─ LLM → rationale per project
        └─ Write → post_project_links + data/output/project_insights/
```

---

## Integration Points and Contracts

### LLM Transport

The LLM client (`src/llm/client.py`) uses the `anthropic` Python SDK directly and authenticates with `LLM_API_KEY` from the environment.

Current routing is category-based:
- `topic_detection`, `project_insights` → Haiku
- `digest`, `recommendations`, `study_plan`, `insight`, `bot_ask` → Sonnet

Per-category overrides remain available through environment variables such as `LLM_MODEL_DIGEST`.

Gateway migration is a future option only. It is not part of the current runtime contract.

### Telethon Session Management

- Session file: `/srv/openclaw-you/secrets/telegram.session`
- API credentials: `/srv/openclaw-you/secrets/telegram_api.env`
- The `TelegramClient` is initialized with the session path as its first argument.
- Session must not be stored inside the project workspace.
- Initial authentication (interactive phone + code) is run manually via `scripts/setup.sh`. Subsequent runs are non-interactive.

---

## Systemd Unit Contracts

### `telegram-ingest.service`

```ini
[Service]
User=oc_you
WorkingDirectory=/srv/openclaw-you/workspace/telegram-research-agent
EnvironmentFile=/srv/openclaw-you/.env
ExecStart=/usr/bin/python3 src/main.py ingest
```

### `telegram-ingest.timer`

```ini
[Timer]
OnCalendar=Mon *-*-* 07:00:00
Persistent=true
```

### `telegram-digest.service`

```ini
[Service]
User=oc_you
WorkingDirectory=/srv/openclaw-you/workspace/telegram-research-agent
EnvironmentFile=/srv/openclaw-you/.env
ExecStart=/usr/bin/python3 src/main.py digest
```

### `telegram-digest.timer`

```ini
[Timer]
OnCalendar=Mon *-*-* 09:00:00
Persistent=true
```

---

## Dependency Graph (Runtime)

```
telegram-digest.service
         ▲
         │ (timer trigger)
telegram-digest.timer

telegram-ingest.service  (ingestion is pure Telethon + SQLite)
         ▲
telegram-ingest.timer
```

---

## Architectural Constraints Summary

| Constraint | Rule |
|---|---|
| LLM transport | `anthropic` SDK with `LLM_API_KEY` |
| Secrets location | `/srv/openclaw-you/secrets/` |
| DB location | `data/agent.db` (project workspace) |
| Output location | `data/output/` (project workspace) |
| Service user | `oc_you` |
| OpenClaw source | Read-only |
| Public ports | None |
| Raw corpus to LLM | Never |
| Session file location | `/srv/openclaw-you/secrets/` |

---

## Evolution Notes (Post-MVP)

The following are explicitly out of MVP scope but architecturally prepared for:

1. **PostgreSQL migration** — Schema is normalized; no SQLite-specific features used except FTS5 (has PG equivalent via tsvector).
2. **Web reader interface** — `data/output/` Markdown files can be served by a static site generator or simple HTTP server without schema changes.
3. **Multi-instance support** — Config and DB path are environment-driven; multiple agent instances could run against different channel sets.
4. **Experiment tracking table** — Schema includes a placeholder for `experiments` table; generation logic is Phase-9+.
