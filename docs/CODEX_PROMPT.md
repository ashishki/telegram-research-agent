# Current Session Handoff

Updated: 2026-09-18
Workstream: PA — full Personal AI Assistant
Scope completed in this publication: specification and development-method integration only.
Baseline: cc105b0024b3e7aa6768ee29acc105b4c682376c
Playbook: d570163ab17ec3b4245187c778f1e8d89af9690f

## Goal

Implement the complete `docs/PERSONAL_ASSISTANT_SPEC.md`, not a minimal demo:
natural conversation, real archive/web AI search, beautiful weekly/topic
briefings, subscriptions, mail/calendar/Canvas, confirmed actions, memory,
multimodality, model-quality/cost controls and reliable operations.

No PA implementation task is completed yet. The paired design is
`docs/design/PA.md` and `docs/design/PA.design.json`, status review_required.
The owner approved preparing/publishing this direction and updating Playbook,
not the final hash of a design the owner has not yet reviewed. Do not self-approve.

## Next session

Follow `docs/prompts/personal_assistant_implementer.md`. Preserve the branch and
all historical state. First establish Git identity and initialize only the
pinned development submodule, then run:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git submodule update --init --checkout -- .playbook/upstream
python tools/playbook.py --check-pin
python tools/check_personal_assistant_plan.py
python tools/feature_workflow.py --root . plan --task PA-00
```

Inspect resulting planning recommendation and design through the current
Playbook review/approval workflow. High-risk design approval is interactive and
hash-bound. Once authorized, select the first dependency-ready PA slice and
continue through the assigned programme after each applicable gate; do not ask
again for already-assigned safe steps. Stop only at genuine safety, scope,
credential, exact-design or human release/acceptance gates.

PA-00 must first reproduce/diagnose the baseline failure:
`tests/test_prm_product_ux_eval.py::test_product_ux_keeps_project_context_for_confirmation_followups`.
Baseline GitHub run 35328205490 failed with 302 passed and 1 failed. This is not
proof that a live bot loses context; distinguish evaluator from application.
Do not remove the test or change expected results merely to green CI.

## Boundaries and evidence

No .env, production database, account, subscription, service or timer was
changed by this planning publication. No independent model review or real-user
pilot is claimed. The submodule is development tooling, not an application
runtime or authorization to install external skills/hooks. Existing archive
and UTD data permissions remain separate from future connectors.

`docs/tasks.md` is the active PA queue. Historic PRM-SN/RFX/UTD statuses remain
in `docs/tasks.before-pa-20260918.md`; do not restart that queue. Current
architecture docs describe existing implementation; PA design describes the
future target. Specific checks in the slice registry are regression floors;
add and wire new acceptance tests before accepting any new feature.

Read `docs/PLAYBOOK_ADOPTION.md` for verification commands, token discipline,
review routing and rollback. Record fresh evidence in `docs/verification/` and
private machine receipts under `.playbook-artifacts/`. Keep the handoff short.

## Reviewer execution contract

The primary implementer uses the current session's default Codex
model/reasoning mode; it does not self-pin and must not review its own changes.
Every independent reviewer is a fresh, separate, read-only process using
`gpt-5.6-terra` with `high` reasoning. Use
`python3 tools/run_codex_role.py run` for each role supported by the Playbook
Role Runner; use a fresh read-only `codex exec` for every other required review
role. Reviewers do not alter code or fix their own findings. The implementer or
a separate scoped fix agent resolves P0/P1 findings, and an independent
reviewer rechecks the affected evidence before dependent work proceeds.

Batch Deep Review at the PA phase boundaries in `docs/REVIEW_POLICY.md`, rather
than after each small change, unless an immediate safety boundary requires it.
Record the requested and observed reviewer model/effort, command, SHA/diff,
scope, findings and recheck result.
