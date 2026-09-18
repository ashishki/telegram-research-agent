# PRM-SN-3A — request plan and egress boundary receipt

Date: 2026-09-17. Base SHA:
`cee8baae3b8a41f571bd689f2dadf7e6e981863f`; final working-diff hash:
`5b4e027ea23d584f57d28d0b5ef7431b1d55b9213f00ccf44becdbf78324c095`.

`prm_request_plan.v1` separates local archive, private context and public
verification. The public plan is capability-off: no query is derived from
operator text; calls, timeout and cost are zero. Application paths are hard
local regardless of environment flags: chat, synthesis and optional planner
provider paths are not invoked. Current CEO/version/price facts preserve a
verification boundary; a mixed response may show only URL-matched canonical
archive evidence and an explicit current-fact boundary.

Focused verification:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  tests/test_prm_request_plan.py tests/test_prm_intent_archive_contract.py \
  tests/test_prm_application.py -q
35 passed in 2.62s
```

Immediate egress/consent reviews found and closed P0/P1 issues around
environment-enabled chat/planner/synthesis, raw public-query construction,
current-fact routing, and mixed evidence provenance. Final independent
read-only review session `01a0b00f-7c06-7791-b464-4e6bf3c22883` observed
`gpt-5.6-terra` / `high` in the runner banner and returned
`PACKET_REVIEW_RESULT: PASS`.

No network/provider call, production write, live mode, delivery, or private
data egress occurred. Phase 3 still requires 3B and DR-3; this receipt grants
no production or pilot authority.
