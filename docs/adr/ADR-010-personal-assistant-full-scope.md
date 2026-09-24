# ADR-010: Full Personal Assistant Direction and Playbook Refresh

Date: 2026-09-18
Status: owner-requested planning/tooling scope; exact feature design and runtime approvals pending.

## Context and authority

The owner explicitly requested a complete specification of the discussed
personal assistant (not an MVP), publication through commit/push, and adoption
of the updated owner-maintained AI_workflow_playbook. This records that request,
not an invented approval of unseen implementation or private-data access.

## Decision

Register the full Chat/Search/Brief/Watch/Act programme as PA-00..PA-18.
Weekly reports are first-class user outcomes, produced from common evidence
and available in Telegram/HTML/PDF/Markdown; not a restart of the old report
pipeline. Academic Inbox is a module of the same assistant and keeps its
independent source-consent and minimization requirements.

Pin development tooling to Playbook d570163ab17ec3b4245187c778f1e8d89af9690f
via a Git submodule and verified entrypoint. Use Standard governance with
proposed designed_slices depth, bounded context, exact design approval and
risk-targeted Role Runner reviews. Do not copy the entire upstream policy
into every prompt or silently replace project-specific contracts with templates.

Preserve pre-PA task/handoff/review documents as byte-identical dated snapshots.
The active PA task graph supersedes previous NEXT-TASK instructions, not their
historical evidence or existing data/runtime permissions. The implementation
contract remains the safety floor. Existing architecture describes existing
code; PA design describes the proposed target.

## Non-authorizations

No live accounts, paid calls, unlimited spend, deployment, ingestion, timers,
production migrations, raw-corpus egress, external skill/hook enablement or
release is approved by this ADR. Model availability/scopes/retention must be
checked when implementing. The feature registry remains review_required;
Playbook interactive hash-bound approval cannot be set by the drafting agent.

## Alternatives and consequences

Rejected: wholesale copy/--force of new templates (would erase local rules);
unchanged old tool copies with only a version label (not a real upgrade);
latest/unpinned checkout (not reproducible); mandatory multi-agent fan-out for
every edit (unnecessary token cost); MVP-only roadmap (contradicts the request).

The submodule requires initialization in developer and CI checkouts. It is not
an application runtime dependency. Missing/mismatched/dirty pin blocks new
tooling; it never silently falls back to the old version. Upstream license
status is preserved, not relicensed by copying the Git reference.

## Evidence and rollback

See `docs/PLAYBOOK_ADOPTION.md` and `docs/audit/PA_PLANNING_HANDOFF_2026-09-18.md`.
Revert the planning/tooling commits to restore the prior state; no application
or production data migration is introduced here. Keep user-specific evidence
private. Token savings for this repository require a matched measurement.
