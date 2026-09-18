# PRM-SN-5A — immediate delivery-boundary engineering receipt

Scope: fixture-only delivery outbox, source-change replay, quota reservation,
ordinary-digest recovery, retry/unknown outcomes and Telegram multi-chunk error
classification. No source polling, service, timer, production DB, Telegram send,
private data, pilot or release was invoked.

Base/reviewed SHA: `cee8baae3b8a41f571bd689f2dadf7e6e981863f` (the implementation is
an uncommitted working diff). Final reviewed diff SHA-256:
`a51bbcf9857a015a7e9ab7c811f11f554b05e25bed5f9af4669962a6cd58744c`.

Requested reviewer command:

```text
codex exec --cd /tmp/prm-sn-5a-final-current-v4/input --skip-git-repo-check
  --ignore-user-config --ephemeral --sandbox read-only --model gpt-5.6-terra
  -c model_reasoning_effort="high" --output-last-message …/review.md
```

Observed runtime evidence: the external runner banner records Codex `v0.154.0`,
model `gpt-5.6-terra`, sandbox `read-only`, reasoning effort `high`, and session
`01a0b08e-9a33-7011-a54b-308a66df83b5`. The sanitised input and raw runner logs
remain under `/tmp`, outside the repository. Exit completed successfully with
`PACKET_REVIEW_RESULT: PASS`; the reviewer could not rerun pytest because its
read-only sandbox lacked a writable temporary directory.

Findings and closure:

- Earlier focused reviews identified non-atomic source/outbox handoff, lease
  ambiguity, ordinary-digest reservation races, receipt/reservation accounting,
  prior-day recovery, missing fault tests, and class-name exception matching.
- The final correction reserves capacity for the **actual delivery day** before
  a prior-day digest is leased; a full cap leaves the durable work pending.
- A failure after an accepted Telegram chunk now becomes ambiguous/`unknown`,
  never a deferred replay. A known pre-acceptance rejection remains bounded
  deferred work. No exactly-once claim is made.
- Final reviewer found no P0/P1/P2 in this slice and confirmed the positive
  ordinary-delivery route as well as no-replay behavior.

Implementer verification:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  tests/test_external_watch_shadow.py tests/test_external_watch_delivery.py -q
28 passed in 1.35s
git diff --check
passed
```

New fault evidence covers two concurrent delivery workers (one sender call),
lease expiry, generic timeout, retry budget, current-day cap for prior-day
recovery, trusted versus same-named unrelated rejection, and accepted first
chunk plus rejected second chunk.

Engineering state: 5A is `implemented_pending_phase_review`; its accumulated
scope remains subject to PRM-SN-DR-5 after 5B. Residual gates are human
authorization, runtime/service-state observation, reconciliation/rollback
exercise, pilot evidence and release approval. Rollback in this local scope is
sender off / kill switch on; pending and unknown records remain for explicit
operator reconciliation and are not automatically replayed.
