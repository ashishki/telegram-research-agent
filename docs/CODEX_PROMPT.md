# Codex Handoff

Status: active
Last updated: 2026-08-16
Repository retrofit baseline: `5dfd38660b7d8d24998b4dcdf801c419c1dc8f7c`
Active integration branch: `master`
Archive ref: `origin/archive/pre-prm-retrofit-2026-08-16`

## Product

Private Personal Telegram Research Memory and Grounded Assistant. Search and grounded answers are primary; report-era surfaces are compatibility-only.

## Current phase

RFX repository retrofit. Follow `docs/tasks.md` in dependency order. Do not add product features while restructuring.

## Rules

- preserve SQLite migrations and privacy/safety tests;
- do not move executable history into `src/archive`;
- keep old code only behind explicit compatibility adapters;
- separate pure moves, import rewrites and behavior changes;
- do not run the complete pytest suite;
- use focused PRM, retrofit-boundary, MAT safety and Playbook checks;
- do not claim operator value before the 15-20 question smoke review;
- no force push or history rewrite.

## Verification

```bash
python3 tools/test_tiers.py focused-prm
python3 tools/test_tiers.py retrofit-boundaries
PYTHONPATH=src python3 tools/prm_mat_eval.py --check safety
python3 tools/playbook_validate.py --root . --check tasks --check references
git diff --check
```

## Next task

Continue from the first `planned` RFX task in `docs/tasks.md`. Update task status and current evidence in the same bounded commit.

## Canonical references

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/IMPLEMENTATION_CONTRACT.md`
- `docs/tasks.md`
- `docs/retrofit/RFX_REPOSITORY_RETROFIT.md`
- `docs/retrofit/RFX_DEEP_REVIEW.md`
