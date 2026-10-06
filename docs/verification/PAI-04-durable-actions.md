# PAI-04 — durable exact confirmation and attempt ledger

Engineering: local_verified; accumulated phase-B review pending.

The existing execute_action entrypoint now supports an explicit PostgreSQL
DurableActionStore. Proposal/account/resource/content/version and private owner
bindings are persisted and checked; confirmation consumption and an unknown
prepared receipt commit before provider I/O. Shared policy rechecks grants under
locks through dispatch. Retries/double clicks return the durable receipt, never
repeat an unknown external effect. Proposal edits are refused while an unknown
attempt remains unresolved. Default in-memory behavior is preserved for existing
callers; this backend requires the explicit shared policy.

Real two-process test executes one fake effect. Another test kills the worker
immediately after that fake effect and before receipt settlement; restart returns
unknown and the effect file still contains exactly one entry. Tests cover foreign
actor/account/proposal, changed version, cancellation, revocation and expiry.
No actual mail/calendar/account send occurred.

Acceptance:
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q tests/test_pai_durable_actions.py tests/test_assistant_actions.py tests/test_prm_post_answer_actions.py

Result: 36 passed in 32.02 s, zero skips/failures. Next PAI-05 durable
conversation/result versions, then PAI-06 queue and accumulated phase-B review.
