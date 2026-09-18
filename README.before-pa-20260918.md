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

Manual private-alpha. Engineering regression evidence exists; operator usefulness
still requires a controlled 15–20-question smoke session and longitudinal
feedback. No public release or production-value claim is made.

Personal Search and News is implemented locally in this same bot: final-answer
integrity, dialogue continuity, controlled public verification, on-demand topic
editions, and confirmation-gated subscriptions with bounded delivery. All five
engineering gates have passed on fixture-only evidence. The implementation is
ready for a separate human pilot decision, not a production/release claim; see
the [integrated replay](docs/audit/PRM_SN_INTEGRATED_REPLAY_2026-09-17.md) and
[pilot/rollback packet](docs/PRM_SEARCH_NEWS_PILOT_PACKET.md).

UTD remains a specific external-watch scenario. The 2026-09-03 receipt records
bounded timer enablement, failing closed until profile confirmation. The
2026-09-17 audit did not observe the current service or profile state. Its
existing official-source, daily-cap, receipt and kill-switch boundaries remain;
the new task queue does not extend those permissions. This is not PRM-19 dogfood.

An optional UTD Academic Inbox (read-only university email, Canvas and public
UTD context) is documented as a **research-only** handoff. It is not connected,
does not expand the current watch, and cannot access personal accounts without
separate approval: [research handoff](docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md).

PRM archive research remains available for operator-controlled manual testing.
PRM-19 requires separate explicit dogfood-start approval; PRM-20 requires real
PRM-19 evidence and separate approval for compatibility cleanup. Details and
the exact next step are in [the active task queue](docs/tasks.md) and the
[UTD enablement receipt](docs/audit/UTD_LIVE_DOGFOOD_START_2026-09-03.md).

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
- [Current operating model](docs/PRODUCT_OPERATING_MODEL.md)
- [Current evidence index](docs/EVIDENCE_INDEX.md)
- [PRM-SN integrated replay](docs/audit/PRM_SN_INTEGRATED_REPLAY_2026-09-17.md)
- [PRM-SN pilot and rollback packet](docs/PRM_SEARCH_NEWS_PILOT_PACKET.md)
- [Visual UX-evaluation packet](docs/PRM_VISUAL_EVAL.md)
- [Local combat-evaluation evidence](docs/audit/PRM_COMBAT_EVAL_2026-09-18.md)
- [UTD Academic Inbox research handoff](docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md)
- [Implementation contract](docs/IMPLEMENTATION_CONTRACT.md)
- [Privacy threat model](docs/PRIVACY_THREAT_MODEL.md)
- [Repository retrofit plan](docs/retrofit/RFX_REPOSITORY_RETROFIT.md)
- [Legacy and compatibility surfaces](docs/legacy_surfaces.md)
