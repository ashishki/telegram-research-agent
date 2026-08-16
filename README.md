# Telegram Research Memory

Private, local-first research assistant over one operator's Telegram reading archive.

The product is no longer a weekly-report generator. The active path is:

```text
Telegram text or voice
  -> PRM request/router
  -> local archive retrieval
  -> evidence and claim checks
  -> grounded answer with Telegram links
  -> optional confirmed save/watch/action
```

## What works

- retained Telegram posts are searchable through SQLite FTS;
- an optional local hash-vector sidecar is available as fallback;
- the measured OpenAI embedding sidecar remains an evaluation adapter, not the default;
- source-backed research, editor briefs, project-decision clarification and current-fact boundaries are implemented;
- primary-source fetching is explicit, bounded and disabled without approval;
- durable memory/actions require confirmation;
- Eval V2 exercises the real route, retrieval and final renderer without sending Telegram messages.

## Current maturity

Manual private-alpha. Engineering regression evidence exists; operator usefulness still requires a controlled 15-20 question smoke session and later longitudinal use. No public release or production-value claim is made.

## Daily use

Send a normal message to the private Telegram assistant:

```text
Что в моём архиве было про agent evaluation?
Что из найденного применимо к telegram-research-agent?
Собери редакторский бриф про enterprise AI adoption.
Какая сейчас актуальная цена этой модели?
```

The assistant should search the archive, cite sources, clarify an unnamed project and refuse unsupported current facts.

## Active code boundaries

- `src/prm/` — active application boundary introduced by the repository retrofit;
- `src/bot/prm_handlers.py` — active Telegram PRM command surface;
- `src/assistant/` and `src/db/` — current retrieval, evidence, memory and verification implementation;
- `src/bot/legacy_handlers.py`, report-era output modules and `src/main.py` — compatibility surfaces pending caller migration;
- `docs/archive/` — historical product and implementation material.

## Quick start

```bash
PYTHONPATH=src python3 -m prm.cli research "что есть про eval gates?"
PYTHONPATH=src python3 -m prm.cli brief "собери бриф про agent reliability"
PYTHONPATH=src python3 -m prm.cli assistant
```

Legacy CLI commands remain available through `src/main.py` during the compatibility window.

## Quality checks

```bash
python tools/test_tiers.py focused-prm
python tools/test_tiers.py retrofit-boundaries
python tools/prm_mat_eval.py --check safety
python tools/playbook_validate.py --root . --check tasks --check references
```

The complete historical pytest suite is intentionally not part of the normal loop.

## Documentation

- [Operator quickstart](docs/operator_quickstart.md)
- [Current architecture](docs/ARCHITECTURE.md)
- [Active retrofit tasks](docs/tasks.md)
- [Implementation contract](docs/IMPLEMENTATION_CONTRACT.md)
- [Privacy threat model](docs/PRIVACY_THREAT_MODEL.md)
- [Repository retrofit plan](docs/retrofit/RFX_REPOSITORY_RETROFIT.md)
- [Legacy and compatibility surfaces](docs/legacy_surfaces.md)

## Privacy

The canonical archive stays in local SQLite. Raw Telegram bodies, private eval questions, vector sidecars and generated outputs are gitignored. Provider-backed synthesis receives bounded cited snippets only when explicitly enabled.
