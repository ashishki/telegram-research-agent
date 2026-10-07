# PAI-28 prepared production package — deployment not performed

Status: draft. Requires PAI-25 rehearsal, PAI-26 review and PAI-27 observations.
No production target/DSN/service/timer was read or changed in this pass.

Freeze one reviewed SHA and dependency/artifact hashes. Inventory the agreed
host/process/database scope only after operator authority. The current runtime
storage target intentionally accepts identified synthetic databases; production
target selection must be implemented/reviewed within the separately authorized
cutover scope rather than removing that guard during local work.

Cutover sequence: stop new intake; drain active leases; fresh private snapshot;
verify manifest/counts/digests; restore into isolated target; apply latest
tombstones and consumed/unknown receipt delta; verify one writer and supported
schema versions; start with new epoch, egress off and intake draining. Reconcile
the lost interval before enabling the exact account/job/delivery scopes.

Candidate commands exist in prm CLI/runtime.operations/runtime.migration;
the service template is systemd/pai-worker.service.example and is inactive.
Do not fill production argv/paths/budgets from guesses. Attach measured rehearsal
RPO/RTO, actual backup location/retention, rollback decision and operator window.

Rollback after new writes uses the implemented complete selected-domain
export/import, with an exact locked target manifest and monotone effect/budget
fences, or a forward fix. Receipt-only transfer does not substitute for domain
state transfer. A stale snapshot cannot re-enable confirmation
or clear unknown fences. Existing report timers stay disabled. Hosting a reader
and exposing owner authentication also require the explicit reviewed deployment.
