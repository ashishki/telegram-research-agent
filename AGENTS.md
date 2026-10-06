# Repository Instructions

Current workstream: Personal AI Assistant (PA), registered 2026-09-18.

## Read narrowly

1. Read `docs/CODEX_PROMPT.md` for current scope and stop point.
2. Read the assigned block in `docs/tasks.md` and its Design/Context refs.
3. Follow `docs/ASSISTANT_BOUNDARIES.md` and `docs/IMPLEMENTATION_CONTRACT.md`.
4. Use `docs/PLAYBOOK_ADOPTION.md` and the pinned `tools/playbook.py` entrypoint.

The full target is `docs/PERSONAL_ASSISTANT_SPEC.md`: Chat, real AI Search,
beautiful weekly Briefs, Watch, and confirmed Act in one assistant. The complete
programme must not be reduced to an MVP. Read the full specification at design
review; during implementation load the relevant sections and current slice,
not the entire historical archive. `docs/design/PA.md` is the compact programme
map and `docs/design/PA.design.json` is its machine-readable slice registry.

## Authority

Current scope and stop point come from the owner's active assignment and
`docs/CODEX_PROMPT.md`. The 2026-10-06 assignment authorizes sequential safe
local PAI implementation, synthetic fixtures and scoped tests, including an
isolated test PostgreSQL in PAI-02. It does not approve the exact design or
live accounts, paid egress, production migrations, services, timers or release.
Prepare a concrete design before requesting a missing human decision; continue
independent authorized work. Never forge approval or mark missing slices done.

Implement directly in the assigned branch. Do not edit master directly, reset
another user's work, force-push, or rerun completed historical tasks. The old
instructions and task states are preserved in `*.before-pa-20260918.md` files;
read them only when resolving a specific historical boundary.

Use Codex Direct in the active session's default model/reasoning mode; do not
pin or override the implementer. `docs/REVIEW_POLICY.md` is the current role,
runner and cadence policy, with the 2026-09-23 owner amendment taking precedence
over the older Terra prescription. Reviews are independent and read-only;
reviewers do not fix, commit/push or grant human acceptance. Fix P0/P1 and get
an independent recheck before dependent work. Deep Review is batched at PAI
phase boundaries unless an immediate safety trigger applies. Record requested
and observed model/effort, reviewed SHA/diff and runner/receipt provenance.

## Verification

Run the smallest appropriate existing test tier plus new slice-specific tests.
Do not run the full historical pytest suite or weaken tests to make CI green.
The historical PA-00 UX failure is repaired; use dated evidence and reproduce
current failures. See `docs/verification/PAI-00-reconciliation.md` for this baseline.
Fixture, CI, visual review, actual provider integration and operator usefulness
are distinct evidence. Preserve failures and unknowns. Before handoff record
changed files, exact commands/results, reviewed commit, remaining gates and the
next command. No private content, tokens or live account data in Git.
