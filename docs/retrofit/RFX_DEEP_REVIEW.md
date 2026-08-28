# RFX Deep Review

Status: complete with residual human-only gates

Date: 2026-08-28

Scope: read-only architecture, privacy, test-boundary, repository-truth, and
documentation review after the active PRM retrofit. This is not operator-useful
evidence, a deployment-parity receipt, PRM-19 dogfood, or a release claim.

## Evidence reviewed

- active request path: `src/prm/`, `src/bot/prm_handlers.py`,
  `src/bot/bot.py`, `src/prm/cli.py`;
- safety-sensitive actions: `src/assistant/prm_post_answer_actions.py`,
  `src/assistant/pi_memory.py`, `src/prm/application.py`;
- runtime templates and archive policy: `systemd/`,
  `docs/retrofit/RFX_REPOSITORY_RETROFIT.md`;
- active versus compatibility tests: `tools/test_tiers.py`;
- generated/private tracking: `git ls-files data/output .playbook-artifacts`;
- active documentation, ADR names, refs and deployment-parity runbook.

## Findings and disposition

| Area | Finding | Disposition |
| --- | --- | --- |
| Active boundary | PRM Telegram commands route through `PersonalResearchAssistant`; the active application package has no direct report/Radar/Frontier import. | Resolved by RFX-2--RFX-7; verified by the retrofit tier. |
| Compatibility leakage | `/status`, `/refresh`, and `/reactions` deliberately lazy-import legacy handlers from `prm_handlers.py`. They are explicit compatibility operations, but prevent an honest claim of zero legacy runtime dependency. | Residual RFX-9 candidate; retain until operator smoke and caller/use audit permit replacement or removal. |
| Confirmation/idempotency | Post-answer actions draft first and persist only through confirmation; saved memory is append-only. | Covered by focused PRM tests; no change required. |
| Current facts and egress | Current facts remain fail-closed. The UTD preparation adds no fetcher, provider call, timer, sidecar, or notification route. | Resolved for P0; future work is constrained by ADR-008. |
| Test tier truth | `focused-prm` referenced missing `tests/test_prm_private_traces.py`, so it could not execute. Existing trace coverage is in post-answer action/interaction-ledger tests. | Fixed by removing the stale path; tier is rerun below. |
| Generated/private artifacts | `data/output` retains only `.gitkeep`; `.playbook-artifacts` has no tracked entry. Untracked local database backup is not staged. | Resolved; preserve local untracked data. |
| Documentation truth | Active docs named a nonlocal retrofit/archive branch, deployment runbook named a historical candidate branch, retrofit README linked nonexistent files, and three ADRs used number 005. | Fixed: current integration ref is `master`, archive is the remote ref, links are real, and decisions are numbered 005/006/007. |
| Product truth | Automated checks and generated evals do not demonstrate usefulness. No private RFX-8 labels, parity receipt, UTD live samples, or shadow results exist in Git. | Human-only residual gate; do not delete compatibility code, start collector/dogfood, or claim readiness. |

## Verification

Run from the repository root on 2026-08-28:

```text
PYTHONPATH=src python3 -m pytest tests/test_external_watch_eval_manifest.py \
  tests/test_prm_post_answer_actions.py tests/test_prm_application.py \
  tests/test_prm_bot_dispatch.py tests/test_prm_cli.py \
  tests/test_retrofit_boundaries.py -q
python3 tools/test_tiers.py focused-prm
python3 tools/test_tiers.py retrofit-boundaries
PYTHONPATH=src python3 tools/prm_mat_eval.py --check safety
python3 tools/playbook_validate.py --root . --check tasks --check references
python3 tools/validate_external_watch_eval.py \
  --manifest evals/external_watch/manifest.v1.json --json
git diff --check
```

The external-watch manifest is structurally valid but intentionally reports
`operator_reviewed_cases=0`, `labelled_cases=0`, `shadow_ready=false`, and
`launch_ready=false`. That is the correct result until human-reviewed evidence
exists.

## Residual gates and next safe action

1. RFX-8: operator runs and privately labels 15--20 smoke questions; no
   synthetic replacement is acceptable.
2. RFX-9: after that evidence and a zero-active-caller audit, remove only the
   compatibility code proven unused. Do not delete migrations, privacy tests,
   or archive history.
3. UTD P0: operator captures real, sanitized source schemas/headers/filter IDs
   and reviews/labels all 50 cases. The blind 15 remain out of policy tuning.
4. P1: requires a new explicit operator approval for an offline shadow
   collector. P2 delivery and PRM-19 dogfood require later approvals and real
   measured evidence.
