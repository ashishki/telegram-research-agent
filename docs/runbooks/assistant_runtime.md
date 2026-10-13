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

D01 (13 October): `assistant` now defaults explicitly to `--mode durable` and
requires target, runtime config and the complete matching owner tuple before
loading settings. The previous PRM bot route is selected only by
`assistant --mode compatibility`; it refuses durable arguments. This is the
existing PRM compatibility path, separate from the legacy report runtime.

```bash
PYTHONPATH=src .venv-pai/bin/python -m prm.cli runtime-check --help
PYTHONPATH=src .venv-pai/bin/python -m prm.cli runtime-check --mode compatibility
```

For durable checks pass `--synthetic-target PUBLIC_TARGET_JSON` and
`--runtime-config PUBLIC_RUNTIME_JSON`, optionally the owner tuple to compare.
The checker reads only those bounded files. It performs no environment/key
lookup, DB connection/migration or adapter/service startup. Its `valid` field
reports offline configuration validation; observed process/schema/grants stay
unknown. It does not establish account access, credential binding, egress
permission or daily readiness. The systemd file is an inactive synthetic
template with explicit durable arguments; it was not installed or enabled.

Current durable adapter accepts only an identified SyntheticTarget. Its file has backend/host/port/database/user/instance_id/target, exact local pa-synthetic marker and nonprivileged pa_test roles. Reject ambient PG variables, default port5432 and a live database. Test fixture helper creates these values; never fill a real target with fake marker/roles to bypass the guard.

runtime_from_config requires owner_ref/owner_chat_id/budget_refs/job_budget. Models/transports/sources use declared references and task-specific credential environment names, not raw credentials in JSON. Reader/media roots and selected accounts/providers are explicit. Missing provider/credential is unavailable, not consent or fallback to another private provider.

## Foreground procedure

D56 (13 October): the durable polling profile normalizes message/edited_message/
callback_query, stores a decision and cursor before advancing, quarantines poison
or conflicting updates, and retains the cursor on storage failure. Immediate
replies and final deliveries have separate no-repeat attempts; timeout is unknown.
Actual chat/thread/message receipts bind replies/buttons to a job/result/version.
The configured bot_ref namespaces inputs; real bot identity/client support must
still be observed in D27/D40. Foreign/business/native Stop updates cannot become
owner controls; unsupported topics receive only an explanatory reply in that route.

Reply to an older answer selects its immutable version and bounded request
context. It does not borrow a newer confirmation or replace another focus.
Quote verification uses UTF-16 offsets against an available exact message
snapshot; unknown/hidden source identity remains unknown. Forwarded content is
untrusted data. Editing an owner input saves a revision and invalidates old
controls and prepared/consumed proposals. Consumed confirmations and unknown
attempt receipts remain; they cannot be reopened or retried. An edit winning
before final transport/action dispatch blocks it; if dispatch wins first, its
receipt remains authoritative. Explicitly request a new computation if needed.
Existing v1/multipart payloads retain their original checksums and no-replay state.

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

D02/D03: text “Что с задачей?”, “Стоп”, “Останови обзор”, “Верни результат”
uses the same job controls as `/status`, `/cancel`, `/result`. A reply selects
the exact bound input/message; several candidates require a short named choice
with owner-bound opaque expiring buttons. Unknown replies do not guess a job.
The queue fence cancels one computation and preserves unrelated dialogue.
Started effects remain available for reconciliation. Returning a result still
requires its separate delivery scope. Fixed phrase coverage is limited; D04
adds the planner/focus, D56 completes outbound receipt/reply routing.

Available primitives: runtime-drain stops new intake, runtime-kill disables egress, backup/restore and domain export/import preserve selected state/manifests/unknown/consumed fences. They require the actual explicit arguments and scopes. Missing/unknown provider outcome is preserved; stale snapshot cannot re-enable an effect. RPO/RTO/production rollback owner remain unmeasured.

Do not restart historical report/UTD timers or mutate systemd/.env/production DB as part of documentation/merge. Worker/service templates are inactive examples, not a deployed state claim. One-shot synthetic tests/recorders are not timers.

## Move to real accounts

Use [pilot access packet](../verification/PAI-pilot-access-20261010.md) and [prepared cutover package](../verification/PAI-28-cutover-packet.md). Needed: selected private bot/chat/owner/destination, test mailbox/folder/calendar, source/operation/model scopes, retention/duration/caps/budgets, secure credential references, stop/cleanup. UTD/API owner-deferred; Brave key not selected.

Source read, private-model egress, write and background work are separate. A mailbox filter does not narrow provider OAuth token. Private-data storage and production target are separate from SyntheticTarget. This packet contains no guessed connect-all, prod DSN or deploy command.

## Evidence

Current398/69/10 proof, engineering117 closure, native model/control captures and portable artifacts: [PRODUCT_STATUS](../PRODUCT_STATUS.md), [Go report](../verification/PAI-go-pilot-20261010.md). Private receipts/screenshots stay outside Git; public examples contain only synthetic data. Git master integration does not start this runtime.

D05/D06 model capabilities and frozen native trace procedures:
[model protocols and daily evaluation](model_protocols_and_daily_eval.md).
Selected text streaming/aliases never imply media, private-egress or background
consent; known/unknown accounting and no-repeat fences remain in force.
