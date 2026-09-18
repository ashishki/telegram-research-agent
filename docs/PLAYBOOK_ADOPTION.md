# Playbook Adoption — 2026-09-18

## What changed

The owner requested upgrading the repository's development methodology. Old
policy named pin 965612aa463fca1a35a55104633d0e09da33d615. The new canonical
kit is the Git submodule `.playbook/upstream`, pinned to
**d570163ab17ec3b4245187c778f1e8d89af9690f** from the owner's
AI_workflow_playbook repository. The lock, Git index and checked-out upstream
HEAD must agree. No runtime depends on this kit.

We did not run the initializer with --force or overwrite project safety rules
with templates. Existing copied toolkit scripts remain compatibility paths;
new development uses `tools/playbook.py TOOL ...` or the four new forwarding
entrypoints. This is a pinned execution path, not merely a new version label.
Task/design/instruction schemas are symlinks to that exact kit, preventing
new tools from validating new tasks against stale schema copies. Supported
checkout environment is Linux/macOS or WSL with real Git symlinks enabled.
An uninitialized submodule is an explicit setup failure, not an old-tool fallback.

## Setup and offline checks

```bash
git submodule update --init --checkout -- .playbook/upstream
python -m pip install -r requirements-playbook.txt
python tools/playbook.py --check-pin
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_playbook_bridge.py -q
python tools/check_personal_assistant_plan.py
python tools/playbook.py playbook_validate --root . --check tasks --check references
python tools/feature_workflow.py --help
python tools/run_codex_role.py --help
```

The bridge never fetches a moving branch, installs a hook, enables a skill or
runs an application service. Initialization fetches only the recorded submodule.
No `git submodule update --remote`. To upgrade later, review an explicit new
commit, update gitlink and lock together, rerun checks and record a new receipt.
Do not execute modified/untracked upstream tooling.

## Development loop

Mode is Standard; planning depth for this programme is designed_slices. Use:

```bash
python tools/feature_workflow.py --root . plan --task PA-00
python tools/feature_workflow.py --root . review --task PA-00 --feature-id PA --role auto
```

Inspect prompts and policy before invoking a paid reviewer. Supply the actually
available approved model/effort to Role Runner. For example, after the model
variable is set by the operator:

```bash
python tools/run_codex_role.py run --root . --task PA-00 --feature-id PA \
  --role program_design_review --model "$REVIEW_MODEL" --reasoning-effort high
```

No review is claimed by rendering a prompt. Design approval is the existing
interactive hash-bound human flow; the registry remains review_required now.
Do not borrow an old project-brief approval. If the tool requests project-level
brief provenance, present `docs/PERSONAL_ASSISTANT_BRIEF.md`, update the current
intake reference explicitly after human approval, and rerun the guard.

After real approval, Feature Workflow selects the first dependency-ready slice:

```bash
python tools/feature_workflow.py --root . next --feature-id PA
python tools/feature_workflow.py --root . start --task PA-00 --feature-id PA --slice-id PA-00
python tools/feature_workflow.py --root . context --task PA-00 --feature-id PA --slice-id PA-00
python tools/feature_workflow.py --root . check --task PA-00 --feature-id PA --slice-id PA-00
```

High-risk slices require actual acceptance after a local scoped commit through
`accept-slice`. Do not replace missing reviewer/approval evidence with a prose
PASS. New tests and their exact commands must be added to each slice before
implementation and to the project verifier before completion. Existing test
tiers in the registry are regression floors, not new-feature acceptance proof.

## Token discipline

Keep AGENTS and the handoff short. Read the full spec once during design, then
current task, compact approved design, relevant spec sections and current-slice
packet. The instruction manifest loads only short boundaries by default;
full requirements and historic snapshots are on-demand/never-by-default.
This avoids repeatedly injecting the old 10KB handoff and full task history.
Do not truncate away requirements or security obligations to make a packet small.

Use targeted task tests, independent focused reviewers and accumulated phase
reviews. Do not fan out all reviewers after every cosmetic edit. Stable context
prefix, changing diff/evidence suffix; receipts are references rather than
repeated log dumps. Cost-per-accepted-task must include fixes, review and tests.
The owner reports upstream savings; no quantitative saving in this repo has
yet been measured. Runtime model efficiency is separately designed in
`docs/COST_ARCHITECTURE.md`.

## Verification and evidence boundaries

`python tools/playbook.py verify_project --root .` now requires real focused
product tests and safety/boundary checks as well as governance, rather than a
contract-only result. Full historical pytest remains prohibited. The new
planning CI is separate from product CI; a green plan is not a green product.
Current baseline product CI has one known UX evaluation failure, assigned PA-00.
Nothing in this update removes it or declares the app ready.

Local bridge tests were actually run against the authored files on Python
3.13.5: 6 passed. A full repository checkout could not be obtained in the
editing container due to network resolution; repository-wide integration
checks are delegated to the committed GitHub CI and must be read as observed,
not assumed. No independent model review or live provider test ran here.

## Trust, preservation and rollback

See `docs/security/PLAYBOOK_UPSTREAM_TRUST.md`. Upstream is source-visible and
has no general project open-source license; the owner requested this use. No
relicensing or external-skill scan guarantee is claimed. Old AGENTS, handoff,
task and review documents remain byte-identical dated snapshots, not current
instructions. The implementation contract and original Academic Inbox handoff
are unchanged. Rollback is a revert of these docs/tooling commits; no database,
account or application runtime migration exists in this publication.
