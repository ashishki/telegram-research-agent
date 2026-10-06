# PAI-05 — durable conversation and exact results

Engineering: local_verified; phase-B review pending.

DurableConversationStore implements the existing ConversationStore interface.
Each call loads owner-scoped state under PostgreSQL serialization, invokes the
existing dialogue semantics and persists the new navigation version atomically.
Immutable response versions live separately in PAI-02's result repository.
Confirmation bindings, expiry, pending/cancelled request IDs and topic reset
survive process restart without inheriting a later object/project.

History retention is an explicit constructor choice (0 disables history), not
an implicit private-data permission. Expired history is physically purged from
its own table; source data and saved result objects remain distinct. Full
source/result deletion propagation belongs to PAI-21/25. Default global
ConversationStore is still ephemeral until PAI-07 composition selects this
backend; actual application injection is tested here.

Acceptance:
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python tools/run_pai_acceptance.py -q tests/test_pai_durable_conversation.py tests/test_assistant_conversation.py tests/test_assistant_report_dialogue.py
26 passed in 9.03 s; zero skips/failures. Includes PostgreSQL restart, two-process
updates, immutable item identity, owner isolation, two pending confirmations,
expiry, cancellation, history purge and real application /new entrypoint.

Next PAI-06: durable jobs/worker/checkpoints, then accumulated phase-B review.
