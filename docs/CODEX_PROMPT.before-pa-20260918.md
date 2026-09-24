# Codex Handoff

Status: local PRM-SN implementation complete; human pilot decision pending
Last updated: 2026-09-18
Audited code baseline: `cee8baae3b8a41f571bd689f2dadf7e6e981863f`
Active integration branch: `master`

## Product and current task

One personal Telegram bot: archive research, useful grounded answers, controlled
public verification and topic news. UTD remains a specific watch scenario.
The owner assigned and the repository completed the end-to-end PRM-SN goal:
all twelve implementation tasks, DR-1 through DR-5, fixes, integrated local
checks and a concrete pilot packet. The exact final engineering evidence is
`docs/audit/PRM_SN_INTEGRATED_REPLAY_2026-09-17.md` and
`docs/audit/PRM_SN_DR5_2026-09-17.md`.

`docs/tasks.md` is the task graph. `docs/PRM_SEARCH_NEWS_PLAN.md` supplies detailed
scope and rollback. ADR-009 supersedes the old RFX-only instruction for explicitly
assigned PRM-SN work; it does not waive privacy, runtime or human release gates.
Existing RFX/UTD statuses are preserved. Do not resume the first old planned RFX
or UTD task instead of the PRM-SN goal. Cards are bounded steps inside one goal;
continue through the assigned phases after engineering review, without a new
permission request per card. That local Definition of Done is now met; the next
step is not implementation but a separately approved human pilot decision.

## Working boundaries

- Implement directly in a separate local branch/copy; preserve existing working
  documentation and unrelated untracked files. Do not reset the user's tree.
- Use inspected synthetic/public fixtures, fake providers/search/Telegram and
  disposable DBs. Inspect imports and I/O before running checks.
- Do not change real DBs, `.env`, profiles, subscriptions, services, timers or
  production migrations. No live ingestion, bot-provider jobs, external
  embeddings, backfill, legacy cleanup or release/dogfood claims.
- A task assignment may include bounded read-only Codex exec review of code and
  synthetic evidence. That is not permission to send the private archive.
- Record task-specific evidence and status only as assigned; commit/push/merge
  require explicit scope. Human remains final completion authority.

## Review and completion

Use `docs/REVIEW_POLICY.md` and `docs/PRM_SEARCH_NEWS_DEEP_REVIEW.md`.
A fresh exec reviewer requests `gpt-5.6-terra`, reasoning `high`, read-only;
record the exact command, reviewed SHA/diff and observed effective model/effort.
The reviewer does not fix code or approve human gates.

Focused critics cover individual changes. The accumulated first-phase gate
`PRM-SN-DR-1` runs after PRM-SN-1A/1B/1C; equivalent gates separate all five
phases. Immediate review applies before continuing through changed write,
confirmation, egress, schema, source-safety or delivery boundaries. Fix P0/P1,
re-verify the changed scope, and preserve unresolved evidence gaps. A task
critic or fixture PASS does not close a phase or authorize production.

For future PRM-SN maintenance, use the affected claim/synthesis/application/
intent tests after I/O preflight; add only meaningful missing regressions and
positive controls.
For docs/task edits, the deterministic validator is read-only with these checks:

```bash
python3 tools/playbook_validate.py --root . --check tasks --check references
git diff --check
```

Do not run the full pytest suite. Preserve historical/advisory labels as such;
see `docs/PRM_SEARCH_NEWS_EVAL.md` for planned independent evaluation.

## Read on demand

- `docs/audit/PRM_SEARCH_NEWS_BASELINE_2026-09-17.md` — verified defects and limits;
- `docs/PRM_INTENT_AND_ANSWER_CONTRACT.md` — archive-first intent semantics;
- `docs/PRIVACY_THREAT_MODEL.md` — actual privacy/egress changes;
- `docs/IMPLEMENTATION_CONTRACT.md` — persistent/compatibility boundaries.
- `docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md` — research-only handoff for a
  possible UTD mail/Canvas/public-source inbox; it grants no account, runtime
  or egress authority.

The UTD timer receipt from 2026-09-03 is historical. Current deployed SHA,
profile confirmation, archive/index freshness and service state were not
observed in the audit; never infer them from this handoff.
