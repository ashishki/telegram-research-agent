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

The owner requested specification, Playbook update, commit and publication.
This change is NOT product implementation, live account consent, a production
migration, deployment, timer enablement, paid model work or release approval.
The exact feature design remains review_required until human approval through
the Playbook workflow. Do not forge approval or mark unimplemented slices done.

Implement directly in the assigned branch. Do not edit master directly, reset
another user's work, force-push, or rerun completed historical tasks. The old
instructions and task states are preserved in `*.before-pa-20260918.md` files;
read them only when resolving a specific historical boundary.

Use Codex Direct for implementation. Independent review is read-only and
risk-targeted; the four Feature Workflow review roles use the pinned Role
Runner. No child commits, pushes, fixes its own reviewed work, or grants human
completion authority. Use actual available model IDs; record observed identity.

## Verification

Run the smallest appropriate existing test tier plus new slice-specific tests.
Do not run the full historical pytest suite or weaken tests to make CI green.
Current baseline has a known focused UX test failure; PA-00 must diagnose it.
Fixture, CI, visual review, actual provider integration and operator usefulness
are distinct evidence. Preserve failures and unknowns. Before handoff record
changed files, exact commands/results, reviewed commit, remaining gates and the
next command. No private content, tokens or live account data in Git.
