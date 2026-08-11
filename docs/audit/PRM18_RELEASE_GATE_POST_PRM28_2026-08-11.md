# PRM-18 Release Gate Post-PRM28 Refresh - 2026-08-11

Status: implementation evidence
Scope: PRM-18 release/dogfood gate after PRM-24, PRM-26, and PRM-28

## Gate

The post-PRM28 release-gate receipt records that the accepted no-vector product
RAG path now has deterministic local gate evidence. It does not start PRM-19,
does not start Telegram services, and does not claim release readiness.

PRM-19 remains blocked until explicit human dogfood-start approval is recorded.
The current operator hard stop against starting PRM-19 remains in force.

## Scope

- Added sanitized post-PRM28 receipt
  `evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json`.
- Kept historical 2026-07-29 receipt unchanged.
- Updated PRM release-gate tests so the post-PRM28 receipt is valid and still
  blocks dogfood.
- Updated handoff, final acceptance, evidence, privacy, dogfood, and audit
  docs to cite the current post-PRM28 gate state.

## Release Gate Receipt

Current post-PRM28 receipt summary:

- schema: `prm_release_gate.v1`;
- dogfood gate: `blocked`;
- dogfood started: `false`;
- release claimed: `false`;
- acceptance scenarios: 11 passed, 0 failed, 0 blocked;
- deterministic evaluation areas: all passed;
- active stop-ship blockers: none in the post-PRM28 receipt;
- active dogfood blockers:
  - `review_unresolved:human-dogfood-approval`;
  - `missing_human_dogfood_start_approval`.

This receipt classifies deterministic local readiness evidence only. It is not
PRM-19 dogfood evidence and not a release claim.

## Boundary Evidence

- No live Telegram ingestion, reaction sync, Frontier, Radar, report
  generation, full archive indexing, embeddings/vector backend, external web
  research, provider egress, service start, migration, production database
  write, dogfood start, release claim, or compatibility-file archive/delete/move
  was performed.
- No raw Telegram text, source URLs, snippets, prompts, completions, provider
  payloads, generated private reports, credentials, or production database
  contents were committed.
- PRM-27 remains blocked unless a future successor vector/backend ADR is
  explicitly approved.
- PRM-20 remains blocked until real PRM-19 dogfood evidence exists and the
  human operator explicitly approves any compatibility archive/delete/move.

## Verification

```text
PYTHONPATH=src python3 -m pytest tests/test_prm_release_gate.py -q
6 passed in 0.09s
```

```text
PYTHONPATH=src python3 -m pytest tests/test_public_evidence.py -q
6 passed in 0.20s
```

```text
python3 tools/test_tiers.py focused-prm
131 passed in 35.29s
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
<no output>
```
