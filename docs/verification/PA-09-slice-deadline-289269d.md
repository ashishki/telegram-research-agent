SLICE_REVIEW: STOP_SHIP

Reviewed read-only at `289269d978488d33dc866862101d264148419a37` against pre-PA-09 `788414f`.

P1 — the required observable/runtime outcome is still absent. [`WatchJobStore`](/srv/openclaw-you/workspace/telegram-research-agent/src/prm/watch_jobs.py:1) deliberately has no scheduler, collection adapter, default DB, or Telegram transport; repository references outside its dedicated synthetic tests are absent. It therefore cannot prove that confirmed watches arrive or stop at the actual collection/send boundaries. The scope amendment forbids enabling that integration, so this remains an explicit acceptance gate, not authorization to add it.

P1 — required runtime verification cannot be met by this local-only slice. The task marks runtime verification required, while the amendment prohibits service/timer/provider/Telegram-delivery/runtime-acceptance work. Synthetic contracts validate useful fail-closed behavior, but do not satisfy the stated runtime criterion.

Advisory — the handoff still names PA-08 as current despite PA-09 commits, and no focused-tier receipt exists for HEAD. The reviewer’s read-only environment could perform only static checks.

Static verification passed: `git diff --check 788414f^..HEAD`; import/purpose-map smoke test passed. No files were modified. This does not approve design, completion, runtime use, or release.