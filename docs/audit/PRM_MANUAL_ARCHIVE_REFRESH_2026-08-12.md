# PRM Manual Archive Refresh - 2026-08-12

Status: manual test refresh, not PRM-19 dogfood

## Boundary

The operator instruction "делай" on 2026-08-12 was treated as approval to
refresh the local Telegram archive so freshness-scoped RAG questions can use
recent retained posts.

This was not a legacy service/timer restart and not PRM-19 dogfood evidence.
No `telegram-bot.service`, weekly report timer, Radar, Frontier, report
generation, reaction sync, migrations, production schema migration, live web
research, external embeddings, hosted vector service, full archive LLM
backfill, provider synthesis, media download, vision LLM, source-event write,
compatibility cleanup, release claim, or dogfood start was run.

The refresh did write the canonical local SQLite archive (`raw_posts`, `posts`,
and `posts_fts`) and rebuilt the approved local gitignored vector sidecar.
Private database backups and vector sidecar files remain gitignored and were
not committed.

## Implementation

Added `memory refresh-archive` as a safer manual PRM path instead of using the
legacy `bootstrap` or `ingest` commands.

The command:

- requires `--confirm-canonical-write`;
- creates a SQLite backup before writing;
- calls bounded Telegram bootstrap ingestion with `days=N`;
- disables media download and vision analysis;
- disables source-event JSONL writes;
- does not run migrations;
- does not run reaction sync;
- normalizes newly inserted raw posts into `posts`/FTS;
- optionally rebuilds the approved local vector sidecar.

## Receipt

Command:

```text
set -a; source /srv/openclaw-you/.env; set +a; PYTHONPATH=src python3 src/main.py memory refresh-archive --days 21 --confirm-canonical-write --json
```

Result:

```text
status=ok
days=21
backup_path=data/backups/agent-prm-refresh-21d-20260811T221511Z.db
raw_posts: 3709 -> 4166
posts: 3709 -> 4166
posts_fts: 3709 -> 4166
max_posted_at: 2026-07-26T22:40:28+00:00 -> 2026-08-11T21:47:37+00:00
inserted_raw_posts=457
skipped_raw_posts=170
ingest_errors=0
normalized_posts=457
normalization_errors=0
vector_index_status=ok
vector_index_path=data/vector/archive_vector.sqlite
```

Privacy flags from the command receipt:

```text
live_telegram_ingestion=true
canonical_db_write=true
local_vector_sidecar_write=true
reaction_sync=false
migrations_run=false
media_download=false
vision_llm=false
provider_egress=false
source_events_written=false
dogfood_evidence=false
release_claim=false
```

The first attempted run did not have Telegram API env vars in the shell and
failed before Telegram connection or archive mutation. It created an additional
pre-write backup under `data/backups/`, which is gitignored.

## Post-refresh smoke

Command:

```text
set -a; source /srv/openclaw-you/.env; set +a; PYTHONPATH=src python3 src/main.py memory research --hybrid --limit 4 "Что было интересного по моделям за последние две недели?"
```

Result summary:

```text
Fresh local model-related archive sources were found inside 2026-07-28–2026-08-11.
Examples included local Telegram citations from @data_secrets, @codecamp, and @llm_under_hood.
No live web, provider call, reaction sync, migration, source-event write, or durable memory write occurred during the smoke.
```

## Validation

```text
python3 -m py_compile src/main.py src/ingestion/bootstrap_ingest.py
pass
```

```text
PYTHONPATH=src python3 -m pytest tests/test_cli.py tests/test_ingestion.py -q
31 passed in 37.53s
```

```text
PYTHONPATH=src python3 -m pytest tests/test_cli.py tests/test_ingestion.py tests/test_memory_research.py tests/test_handlers.py -q
97 passed in 23.72s
```

```text
python3 tools/test_tiers.py focused-prm
199 passed in 44.46s
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
<no output>
```
