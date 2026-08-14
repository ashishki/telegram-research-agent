# PRM-MAT Block A deep-review receipt

Scope: PRM-MAT-1 through PRM-MAT-5, including the accumulated commit
`441b2cfe513988b8ae7d15ae07f468d1850946ff` and the local corrective diff.

Status: corrective implementation and targeted verification are complete; the
block is **not closed** and this is not operator validation, dogfood evidence,
a release claim, or approval for a persistent write.

## Review execution

An independent read-only review was requested as `gpt-5.6-terra` with `high`
reasoning. The runtime did not expose the effective model or effort, so this
receipt records it as unverified rather than representing it as Terra/high.
The reviewer made no file, network, provider, Telegram, database, or service
change.

The first review found that canonical context did not reach retrieval/DTO,
dialog state used a raw chat key, the V2 portfolio validation was disconnected
from the live resolver, and the professional DTO lacked contract fields and
validation. Two corrective review cycles were applied:

- `operator_context` now reaches local retrieval and its interaction/workflow
  reach `professional_answer.v1`.
- Dialog state uses a hashed chat key, expires after 30 minutes, retains at
  most six bounded summaries, and has an explicit per-session ID. A new topic
  starts a new session; a short follow-up continues the prior session.
- The live descriptor loader validates the approved Portfolio V2 shape before
  adapting it to the established project-context resolver.
- The professional answer has the contract fields and rejects missing identity,
  unsupported workflow, uncited findings, and current-fact actions. Its
  compatibility fallback preserves one generated interaction ID in both the
  DTO and enclosing result.

## Targeted verification

- `PYTHONPATH=src python3 -m pytest tests/test_operator_context.py
  tests/test_project_portfolio_context.py tests/test_prm_professional_workflows.py
  tests/test_memory_research.py tests/test_handlers.py -q` — `105 passed in
  12.80s`.
- `python3 tools/playbook_validate.py --root . --check tasks --check
  references` — `errors=0 warnings=0`.
- `git diff --check` — passed.

No full suite was run under the global operator policy.

## Remaining gate conditions

1. On 2026-08-14 the operator approved exact uniform Portfolio V2 completion
   values. They are now required by the validator and recorded in the MAT-3
   receipt; no database or runtime boundary changed.
2. MAT-1 through MAT-5 receipts still need a declared evidence disposition for
   their task-marked holdout, mutation, property, visual, and runtime checks.
   Current focused tests cover deterministic context, route, citation, session,
   and final-chunk properties, but do not substitute for human mobile review or
   operator runtime validation. Any public screenshot remains separately
   approval-gated.
3. MAT-6 changes durable proposal storage and its migration. It remains blocked
   pending explicit operator approval of the persistent schema and retention
   policy, independently of the Block A evidence items above.
