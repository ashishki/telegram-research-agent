# PA Intake and Verifier Compatibility

The current pinned Feature Workflow reads `docs/PROJECT_BRIEF.md` for project
intake. That file now describes the new full assistant target, with approval
pending; the previous brief is preserved as a byte-identical dated snapshot.
The feature brief remains the compact source in PA.design.json. No old approval
marker is inherited as new approval.

The current upstream validator intentionally recognizes the public verifier
filename `tools/verify_project.py`. Preserve the existing valid delivery contract
and provide that name as a guarded forwarding facade to the pinned upstream
implementation. The previous verifier source is preserved as
`tools/verify_project_legacy.py`, not invoked by the active facade. Imported
helper APIs resolve to the pinned version; a missing pin fails closed.

Planning CI verifies delivery/readiness bindings and the verifier CLI along
with schema/context and explicit missing-approval negative checks. The real
project verifier still uses the ordinary upstream approval check and actual
product test tiers; planning-only expected rejection is not a release bypass.

The captured-stream ordering correction was tested locally: 9 bridge/guard
checks passed. Actual CI status must be read at the corresponding published
commit; this record does not invent future results. Application files, accounts,
services and runtime state remain unchanged.
