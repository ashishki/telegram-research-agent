# ADR-011: Retire report-era legacy surfaces (bounded)

Date: 2026-09-23
Status: owner-directed; bounded retirement. Supersedes the RFX-8/RFX-9/PRM-20
cleanup gates only for the items accepted below. Everything else stays frozen.

## Context and authority

Owner direction 2026-09-23: stop carrying dead report-era code, but keep the
active Personal Assistant path green. `docs/legacy_surfaces.md` and
`docs/legacy_runtime_inventory.md` require an explicit delete proposal with
replacement, callers, migration risk, focused verification and operator
approval before any compatibility cleanup. This ADR records that owner approval
and the required fields for the items actually retired.

## Verified inventory result

An independent sweep (owner session 2026-09-23) found that most "dead" files are
entangled and are **not** safe to delete yet:

- `tools/rag_eval_*.py` — used by `tools/playbook_validate.py`, which CI and
  Playbook tooling invoke. Not dead.
- `scripts/run_bootstrap.sh` — used by `tests/test_cli.py`, `src/main.py` and
  `src/ingestion/bootstrap_ingest.py`. Not dead.
- `src/bot/legacy_handlers.py` — retained deliberately by the PA-00 design
  (`docs/design/PA.md`) as the tested `_prm_post_answer_markup` no-controls path
  and by in-tier tests (`tests/test_prm_bot_dispatch.py`,
  `tests/test_assistant_egress.py`, `tests/test_retrofit_boundaries.py`).
  Removing it would change a documented safety contract, so it is out of scope.
- `src/output/*`, `src/assistant/semantic_retrieval.py` — named in
  `docs/legacy_runtime_inventory.md` as retained until replacements exist.

## Decision

Retired now (zero live callers):

| File | Replacement | Current callers | Migration risk | Verification |
| --- | --- | --- | --- | --- |
| `tools/utd_capture_once.py` | none needed; one-off historical capture | none | none (no importer) | `python tools/test_tiers.py focused-prm` |
| `tools/verify_project_legacy.py` | `tools/verify_project.py` | none (only a historical audit mention) | none (no importer) | `python tools/test_tiers.py focused-prm` |

Approved in this session's earlier commits and unchanged here:

- Compatibility dispatch facades (`bot.bot.dispatch_command`,
  `bot.handlers.dispatch_command`) now default to the gated `prm_assistant`
  mode; `run_bot`'s legacy branch passes its mode explicitly.

Actively decoupled (import hygiene, no deletion):

- `assistant/__init__.py` and `external_watch/__init__.py` are lazy package
  facades, so the active path no longer import-loads `output.*`/`semantic_retrieval`
  or the collector engine.

## Explicitly deferred (not forgotten)

- `src/bot/legacy_handlers.py` bundle and the `legacy` runtime mode: removal is
  a dedicated slice that must replace the PA-00 no-controls contract and its
  tests, then delete the file, its report-era imports and the legacy-only
  tests. Not done here because it changes a documented safety behavior.
- `src/output/*` report-era modules and `src/assistant/pi_intent.py`: block on
  the inventory's replacement rule.
- Legacy UTD systemd watch units outside `systemd/archive/`: not touched; their
  host enablement state is unverified and out of scope.

## Non-authorizations

No host systemd change, no production DB migration, no live account, timer,
provider or release action. This ADR does not mark any PA slice accepted and
does not change the mechanically `review_required` design status.

## Evidence and rollback

`git log` on the retirement commits; `python3 tools/check_personal_assistant_plan.py`;
`python3 tools/test_tiers.py focused-prm`. Rollback is a straight `git revert`
of the bounded deletion commits; no data or runtime state is affected.
