# Assistant runtime runbook

Updated10 October2026. Current code proof0fbcfd1. This runbook describes available explicit local paths and missing live setup; it does not assert an installed/active service. Historical August runtime observations remain in dated receipts/Git.

## Inspect first

```bash
PYTHONPATH=src python -m prm.cli --help
python tools/playbook.py --check-pin
python tools/check_pai_plan.py
```

The CLI contains assistant/job-status/job-cancel/job-result/job-worker and runtime-install/status/tick/research-worker/backup/drain/kill/domain-export/domain-import/state-manifest/restore. Help is read-only; actual runtime commands need complete explicit target/config/owner/artifact arguments. Inspect each subcommand's --help rather than guessing parameters.

## Target and configuration

Current durable adapter accepts only an identified SyntheticTarget. Its file has backend/host/port/database/user/instance_id/target, exact local pa-synthetic marker and nonprivileged pa_test roles. Reject ambient PG variables, default port5432 and a live database. Test fixture helper creates these values; never fill a real target with fake marker/roles to bypass the guard.

runtime_from_config requires owner_ref/owner_chat_id/budget_refs/job_budget. Models/transports/sources use declared references and task-specific credential environment names, not raw credentials in JSON. Reader/media roots and selected accounts/providers are explicit. Missing provider/credential is unavailable, not consent or fallback to another private provider.

## Foreground procedure

1. Select the actual target/config and authenticated owner tuple.
2. Check status/readiness and current grants/expiry/budgets.
3. Accept intake durably; worker handles bounded computation.
4. Observe immutable result version and its separate delivery state.
5. Render/private-read only the owner-authorized artifact.
6. On unknown effect, stop dispatch/repeat; use matching scoped evidence through reconcile.

A local developer benchmark used controlled Go parameter translation/30s model timeout on wholly synthetic data; do not copy that into an unapproved production profile or change the ordinary8s default silently.

## Watch and Act

Watch preview includes source/cadence/quiet/cap/timezone/expiry. Confirmed intent is not a running daemon. Observe actual tick/collection/provider receipt separately. Pause/revoke/cancel stops future work; previously started effects may remain unknown. Resume needs a later actual tick to prove activity.

Mail/calendar/Telegram writes require exact current preview/owner/version/expiry/one-use confirmation and separate execute/reconcile grants. 202 alone is unknown; SentItems is not recipient delivery. Multipart sends and reconcile share exact stored payloads. Do not resend an ambiguous aggregate or modify its digest to make reconciliation pass.

## Stop and recovery

Available primitives: runtime-drain stops new intake, runtime-kill disables egress, backup/restore and domain export/import preserve selected state/manifests/unknown/consumed fences. They require the actual explicit arguments and scopes. Missing/unknown provider outcome is preserved; stale snapshot cannot re-enable an effect. RPO/RTO/production rollback owner remain unmeasured.

Do not restart historical report/UTD timers or mutate systemd/.env/production DB as part of documentation/merge. Worker/service templates are inactive examples, not a deployed state claim. One-shot synthetic tests/recorders are not timers.

## Move to real accounts

Use [pilot access packet](../verification/PAI-pilot-access-20261010.md) and [prepared cutover package](../verification/PAI-28-cutover-packet.md). Needed: selected private bot/chat/owner/destination, test mailbox/folder/calendar, source/operation/model scopes, retention/duration/caps/budgets, secure credential references, stop/cleanup. UTD/API owner-deferred; Brave key not selected.

Source read, private-model egress, write and background work are separate. A mailbox filter does not narrow provider OAuth token. Private-data storage and production target are separate from SyntheticTarget. This packet contains no guessed connect-all, prod DSN or deploy command.

## Evidence

Current398/69/10 proof, engineering117 closure, native model/control captures and portable artifacts: [PRODUCT_STATUS](../PRODUCT_STATUS.md), [Go report](../verification/PAI-go-pilot-20261010.md). Private receipts/screenshots stay outside Git; public examples contain only synthetic data. Git master integration does not start this runtime.
