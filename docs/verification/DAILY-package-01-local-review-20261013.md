# Daily package 1 — independent local read-only review

Review route: collaboration agent `/root/daily01_readonly_review`.
Requested model/effort: active session defaults, no override. Observed
model/effort: unknown. Paid/provider calls: zero. This is local independent
engineering evidence; the non-Codex Go route in REVIEW_POLICY remains
unobserved and is not claimed satisfied. No governed/human acceptance.

Reviewed source: `08fb32e1a9c97f8041088e8427f9b9b80059c468`, exact range
`2a1236c..08fb32e`, metadata context `d7368b4`.
`git diff --binary` SHA-256:
`c246840e13aa5742167e329f3eadcfbbdfc67ec22d9d876085d1bc2b64bba84a`.
Full package verdict: **STOP**. Frozen findings:

| ID | Severity | Trigger and evidence | Disposition |
| --- | --- | --- | --- |
| DAILY01-R01 | P1 | Natural controls bypassed durable inbox. Replay of the same Stop update after A cancellation/B admission/restart cancelled B. Independently reproduced in memory through actual ingress. | Fix persists resolved target or ambiguity before execution; changed same-ID content raises StateConflict. |
| DAILY01-R02 | P1 | Worker can claim an effect between the separate status read and unconditional cancel update. It became cancelled at attempts=1, losing the recovery-to-reconciliation path. | Fix makes the transition atomic in queue SQL: started effects become awaiting_reconciliation and lose the execution fence; compute remains cancelled. |
| DAILY01-R03 | P2 | Graph tenant/redirect and delivery origin checks are incomplete offline. Invalid nested config can pass before constructor validation; TokenVault may mutate its directory first. | Retained explicitly for shared pure config validators; no live graph/credential/startup exercise in these packages. |

The reviewer found no additional P0/P1 in the inspected owner checks, opaque
callback expiry, deletion lineage, compute fencing or retained delivery and
confirmation guards. Outbound bindings/ack/quarantine are D56 work, not evidence
from this review. Existing 38/52 test results were read, not rerun by reviewer.
Three read-only in-memory reproductions used PYTHONDONTWRITEBYTECODE=1, exit 0;
no DB, private files, credentials, network/provider calls or writes.

Implementer reproduced both P1s with real isolated PG fixtures:
`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_daily_controls.py::test_stop_update_replay_after_restart_keeps_original_target tests/test_daily_controls.py::test_ambiguous_stop_replay_does_not_become_single_job_cancel tests/test_daily_controls.py::test_effect_claim_between_status_and_cancel_preserves_unknown_fence`:
**exit 1, 3 failed / 12.67s** before fixes.

After fixes:
`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_daily_controls.py tests/test_pai_ingress_jobs.py tests/test_pai_delivery.py::test_cancelled_effect_lease_cannot_send_completed_result tests/test_pai_workers.py::test_unknown_effect_is_never_reclaimed_as_compute_or_resent`:
**exit 0, 30 passed / 84.96s**, zero skips. `git diff --check`: exit 0.

Narrow independent P1 recheck is pending on the committed fix. Do not repeat
the full package review for these fixes. The latest owner says “делай следующий
пакет”; local continuation is requested, while paid authorization and an explicit
policy reviewer-route replacement remain absent. The implementer uses this
transparent local engineering check and preserves the policy evidence gap.

## Narrow recheck of 57f6e39

Fresh agent `/root/daily01_p1_recheck` reviewed
`57f6e39f57af57fcf4b6e622b3e30d6640a37c61`, range `d7368b4..57f6e39`, binary
diff SHA-256 `321b2a1abfe5dd27a9bd19f0a391eb23cf539b4dc685c09ae6a7f7c14cd7820c`.
Verdict **STOP**: R02 CLOSED; R01 remains P1 for same-ID cross-route changes;
new R04 P1 for copied candidate titles without input deletion lineage. Three
memory reproductions exited 0, with no filesystem/database/provider writes.

Follow-through fix shares one immutable raw-update fingerprint between control
and compute commits, and adds input namespace/ref lineage for each frozen
selected/candidate job. The fingerprint retains no source text. Source deletion
tombstones the frozen selection so replay fails closed rather than resolving a
new job. Initial queue-admission test now also asserts the rejected update has
no identity row after rollback; the added identity metadata is counted explicitly.

`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_daily_controls.py::test_control_identity_cannot_cross_into_compute_route tests/test_daily_controls.py::test_deletion_removes_control_choices_and_prevents_replay_retarget tests/test_daily_controls.py::test_stop_update_replay_after_restart_keeps_original_target tests/test_daily_controls.py::test_effect_claim_between_status_and_cancel_preserves_unknown_fence tests/test_pai_ingress_jobs.py::test_enqueue_failure_rolls_back_inbox_and_never_acknowledges`:
**exit 0, 5 passed / 47.38s**, zero skips. R01/R04 require only a narrow
closure on the next committed SHA; no second full package review.

## Final narrow closure

Fresh read-only turn `/root/daily01_p1_recheck` reviewed exact
`988da0e5f907f933168dc655e354ac713a004e64`, range `57f6e39..988da0e`, binary diff
SHA-256 `ec882f20f72075a68a99a22c62244118341f91ee410d0b74ae8f3e706e2e4054`.
Verdict **PASS: R01/R04 CLOSED for newly admitted state**; R02 remains closed.
Memory reproduction exited 0: both cross-route changes fail closed, deletion
removes copied titles/tombstones selection, replay does not cancel remaining B.
No writes/network/provider/credentials; five PG passes inspected, not rerun.
Existing pre-identity state was not backfilled or tested. R03 P2 remains.
Local engineering closure allows the owner's requested next local package;
non-Codex Go/governed/human acceptance is still not claimed.
