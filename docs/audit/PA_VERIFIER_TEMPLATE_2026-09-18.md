# Pinned Project Verifier Template Integration

Observed upstream source at d570163ab17ec3b4245187c778f1e8d89af9690f:
`tools/init_playbook_project.py`, function `verify_project_script()` (line 723).
The verifier is a literal generated script, not an upstream standalone file.

The bridge now extracts only that literal with Python AST, without importing
or executing the initializer and without writing template files over the repo.
The exact pinned generated verifier code supplies both the canonical CLI and
its helper API. A changed/nonliteral template shape fails closed. All actual
project verification checks and their approval gates remain unchanged.

The preceding CI run 35334447820 proved: pin identity, 9 focused tests, all 19
PA slice/task/schema/reference checks, expected draft-approval rejection, and
delivery/readiness bindings. It then correctly exposed the missing standalone
verifier assumption in the added CLI smoke test; this commit fixes that wiring.

Four regression tests cover literal extraction without initializer execution,
rejection of executable generation, symlink rejection and exact argv handling.
Local command over authored files:
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_playbook_bridge.py tests/test_pa_approval_guard.py -q`
Result: 13 passed on Python 3.13.5. Read the published CI result for full
checkout integration evidence; no future pass or product release is asserted.
