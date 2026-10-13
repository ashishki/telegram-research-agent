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
