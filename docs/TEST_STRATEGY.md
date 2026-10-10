# Test Strategy

Updated10 October2026. Use explicit active tiers; full historical pytest is prohibited. New slice tests must be meaningful, registered and actually executed. No weakened numerical/identity/source/confirmation checks to produce a green result.

## Evidence types

| Type | Proves | Does not prove |
| --- | --- | --- |
| Fixture/unit | Concrete logic/negative boundaries on the tested code | Provider availability or human usefulness. |
| Native E2E/isolated PG | Actual composition/store/jobs/leases/receipt paths | Production database/services/scalability. |
| Full-spec active PAI | All69 exact IDs /10 scenarios and zero skips/failures | Full connected/human acceptance. |
| Actual provider | Observed selected HTTP/model/usage | All providers/accounts, tariff or long-term availability. |
| Browser/PDF | Real rendered content, dimensions, errors and text bounds | Live phone/private hosted reader usability. |
| Advisory judge | Named dataset/criteria/raw grades | Safety/role/human/production acceptance. |
| Independent engineering | Exact committed diff/source risk findings and recheck | All formal roles or programme acceptance. |
| Remote CI | Workflow completion on its SHA | Deployment, operator usefulness or live scopes. |

## Active tiers

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python tools/test_tiers.py pai-complete
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python tools/test_tiers.py focused-prm
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python tools/test_tiers.py retrofit-boundaries
python tools/test_tiers.py focused-prm --print-only
```

`pai-complete` calls tools/run_pai_acceptance.py with --require-spec-matrix and explicit active paths. The runner owns JUnit, rejects zero/duplicate/skipped/failed/error cases and missing binding IDs/scenarios. Planned files/synthetic diagnostics are never substituted for an actual test. `focused-prm` includes active reused contracts, source/confirmation/tooling holdouts; `retrofit-boundaries` validates the source/compatibility boundary. Other fast/ops tiers remain defined in the entrypoint and are chosen only for relevant changes.

## Environment

Current observations use Python3.10/application venv, PYTHONPATH=src and PYTEST_DISABLE_PLUGIN_AUTOLOAD=1. PG tests require PostgreSQL14 initdb/pg_ctl/dump/restore tools; absent DB is failure, not skip. PostgresSandbox creates a unique disposable localhost cluster, port/database/marker/roles; it never reuses live DSN/port5432 or changes a service. Ambient PG variables are rejected.

Declared commands above are portable. Exact current execution argv/environment/log hashes/SHA and local interpreter path are in dated receipts. Dependencies/install instructions are not assertions of a reinstall in this session.

## Latest current source results

Runtime/test SHA0fbcfd1:PAI398/1164.34s;delivery43/127.72s;Brief77/100.04s;recovery33/260.43s. Before repair,6 multipart cases failed44.95s; failures preserved. Independent117 closed this P1; extreme HTML nesting P2 remains.

Premerge CI-focused PRM751/88.06s and retrofit150/14.28s are current source observations. Documentation/pin/plan/reference/expected-approval/MAT checks and final refs are in [master integration receipt](verification/PAI-master-integration-20261010.md). These tiers overlap and are not a summed unique test count. Previous736/150 dated runs remain in their old files.

## Checks for documentation/integration

```bash
python tools/playbook.py --check-pin
python tools/check_personal_assistant_plan.py
python tools/check_pai_plan.py
python tools/playbook.py playbook_validate --root . --check references
python tools/check_pa_approval_guard.py
python tools/prm_mat_eval.py --check safety
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_playbook_bridge.py tests/test_pa_approval_guard.py -q
git diff --check
```

Raw full playbook contract still reports51 missing design approvals. `check_pa_approval_guard.py` permits only the precise expected-rejection set in unapproved planning state; it does not manufacture approvals or green whole-project status. A new reference/delivery/readiness error must not be hidden inside that allowance.

## Cadence and preservation

Run the smallest existing relevant tier +new slice tests. Once a complete block passes, repeat/broaden only for actual change, failure, new risk or required integration check. Current doc-only reconciliation does not need more paid model calls or another PAI398 run while runtime bytes are unchanged. Record source identity after merge; a different target runtime tree needs relevant checks.

Reviews are fresh/read-only and independent; fix P0/P1 and obtain an actual recheck before dependent work. Do not run programme/design batches after every formatting correction. Genuinely completed shared scenarios remain regression evidence, not a reason to restart the programme.

Long local checks use a one-shot recorder with exact PID/PGID/source/argv/log, not a service/timer. An interrupted session is not PASS. Previous304-dot SIGTERM and owned earlier SIGINT remain original failures/incomplete attempts; cleanup touches only attributed temporary synthetic processes.

## Quality and visual data

Current Pro text judge:6 sessions25 turns/11 V4.1 generator calls, every8 axes≥4; full public synthetic input archived. Current Kimi visual pass belongs to fixed-content renderer benchmark, while fresh V4.1 Brief has separate5-page browser/PDF proof. Different models/data cannot be presented as a matched causal improvement. Raw labels/failures/unknowns are preserved; derived qualification uses actual numeric axes.

Model/key/ledger availability is not permission for private egress. Actual billing, live media/account connectors and owner usefulness remain unknown. CI status is observed via the actual remote run and recorded separately. Historical July/PRM/report-era results remain in Git/dated receipts and are not the current baseline.
