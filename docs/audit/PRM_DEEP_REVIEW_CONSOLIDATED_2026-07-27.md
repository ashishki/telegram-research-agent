# PRM Deep Review Consolidated Corrective Log - 2026-07-27

Status: active corrective review evidence
Reviewer protocol: meta -> architecture/privacy -> code/tests -> consolidate
Authority: `docs/REVIEW_POLICY.md`, `docs/tasks.md`,
`docs/PRIVACY_THREAT_MODEL.md`, `docs/retrieval_eval.md`

## Scope

This is corrective evidence for the already-committed PRM range
`eca8385..bc2d145` plus the 2026-07-27 fixes recorded in this change set.

The review was required because PRM block-review gates were crossed before
independent review evidence was committed. This document does not erase that
process miss and does not claim release readiness, dogfood start, vector backend
adoption, gold-query approval, or external-skill approval.

The operator's 2026-07-27 chat instructions requested continuation, granular
commits/pushes, and the deep-review protocol. This is recorded as permission to
perform corrective implementation and review work in the repository. It is not
an ADR acceptance receipt and does not approve any stop-ship boundary.

## Subagent Protocol

Nested Codex processes were used only as read-only reviewers, not for bootstrap
or implementation. This fits the review-policy allowance for optional child
reviewers while preserving the AGENTS rule that implementation stays in the main
repository session.

Preflight:

```text
command -v codex
/usr/bin/codex

codex exec --help
Result: `-a` is not a `codex exec` subcommand option; approval must be passed
to the top-level `codex` command.
```

Initial failed attempt:

```bash
codex exec -C /srv/openclaw-you/workspace/telegram-research-agent -s read-only -a never -m gpt-5.5 -c model_reasoning_effort='high' -o /tmp/prm_meta_review.md
```

Result:

```text
error: unexpected argument '-a' found
```

Read-only `/srv` sandbox attempts with the corrected option order could not
inspect the target repository path and returned blocker-only findings. A clean
temporary clone was then created for review:

```bash
REVIEW_ROOT=$(mktemp -d /tmp/prm-review-repo.XXXXXX)
git clone --quiet --no-local . "$REVIEW_ROOT"
printf '%s\n' "$REVIEW_ROOT"
git -C "$REVIEW_ROOT" status --short --branch
git -C "$REVIEW_ROOT" log --oneline --decorate -6
```

Result:

```text
/tmp/prm-review-repo.7UcDnW
## master...origin/master
bc2d145 (HEAD -> master, origin/master, origin/HEAD) docs(prm): record readiness evidence and block reviews
e46447c feat(assistant): add bounded archive routing and answer contract
18b4e8f test(rag): add retrieval baseline eval gate
096c901 feat(rag): add reaction fast lane and enrichment gates
7baa292 feat(rag): add archive identity and fts search
eca8385 docs: retrofit playbook for research memory pivot
```

Reviewer commands:

```bash
codex -a never -C /tmp/prm-review-repo.7UcDnW exec -s read-only -m gpt-5.5 -c model_reasoning_effort='high' -o /tmp/prm_meta_review.md - <<'PROMPT'
Review only eca8385..HEAD as META/PROCESS. Do not edit, commit, push, inspect
or print private Telegram raw text, query data/agent.db content, run network
research, or request approval. Check review gates, stop-ship boundaries,
candidate-vs-gold rules, sequencing, evidence, and corrective-review claims.
Return PACKET_REVIEW_RESULT plus severity-ordered findings.
PROMPT
```

```bash
codex -a never -C /tmp/prm-review-repo.7UcDnW exec -s read-only -m gpt-5.5 -c model_reasoning_effort='high' -o /tmp/prm_arch_review.md - <<'PROMPT'
Review only eca8385..HEAD as ARCHITECTURE/PRIVACY. Do not edit, commit, push,
inspect or print private Telegram raw text, query data/agent.db content, run
network research, or request approval. Check archive boundaries, read-only
behavior, confirmation gates, provider/raw text egress, vector backend gate,
rollback/indexing contract, and scope leaks. Return PACKET_REVIEW_RESULT plus
severity-ordered findings.
PROMPT
```

```bash
codex -a never -C /tmp/prm-review-repo.7UcDnW exec -s read-only -m gpt-5.5 -c model_reasoning_effort='high' -o /tmp/prm_code_review.md - <<'PROMPT'
Review only eca8385..HEAD as CODE/TESTS. Do not edit, commit, push, inspect or
print private Telegram raw text, query data/agent.db content, run network
research, or request approval. Check new code/tests for bugs, missing tests,
privacy regressions, unsafe writes, and metric/report inconsistencies. Return
PACKET_REVIEW_RESULT plus severity-ordered findings.
PROMPT
```

All three valid reviewer outputs returned `PACKET_REVIEW_RESULT: ISSUES_FOUND`.

## Findings And Disposition

| Reviewer | Finding | Disposition |
| --- | --- | --- |
| Meta/process | P1: implementation proceeded without committed approval/evidence for the pivot/start boundary. | Recorded as corrective work only. Handoff docs now describe actual HEAD state and explicitly avoid dogfood/release/vector/gold approval claims. |
| Meta/process | P2: final committed verification evidence was incomplete for the corrective range. | This document records exact review/test commands and the final validator/diff results. |
| Architecture/privacy | P1: PRM block boundaries were crossed and PRM-9/PRM-10 slices exist while PRM-11/PRM-12 remain open. | Recorded as an audit miss. No new PRM implementation continues from this log until the corrective change set is committed and pushed. |
| Architecture/privacy | P2: trace/cost telemetry under-reported bounded snippet provider egress and fake/live cost source. | `pi_chat` now separates bounded snippet provider egress from broad corpus egress and uses live completion receipts where available. |
| Code/tests | High: approved-but-unlabeled eval rows counted as gold. | `archive_retrieval_eval` now rejects human-approved rows without scoreable expected labels. Regression test added. |
| Code/tests | High: no-answer scoring passed when search failed. | Search errors now fail no-answer and stale-rejection metrics. Regression test added. |
| Code/tests | Medium: LLM planner could override deterministic exact/reaction/no-answer routes. | Critical deterministic routes now bypass LLM planning. Regression test added. |
| Code/tests | Medium: generation/planning cost and egress telemetry were inaccurate. | Generation uses `complete_with_receipt` when available; telemetry records cost source and bounded snippet egress. |

## Test Tier Evidence

```text
PYTHONPATH=src python3 -m pytest tests/test_archive_retrieval_eval.py tests/test_pi_chat.py -q
16 passed in 1.47s
```

```text
PYTHONPATH=src python3 -m pytest tests/test_test_tiers.py -q
3 passed in 0.06s
```

```text
python3 tools/test_tiers.py focused-prm
49 passed in 2.36s
```

```text
python3 tools/test_tiers.py fast-contract
102 passed in 28.36s
```

```text
python3 tools/test_tiers.py ops-date-sensitive
1 failed, 3 passed in 3.86s
FAILED tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
```

The ops failure is the known date-sensitive live-evidence-window fixture. It was
not fixed in this corrective work because the operator explicitly excluded it
from scope.

```text
python3 tools/verify_project.py --root .
PASS: playbook_contract exit=0
FAIL: project_tests exit=1
verify_project: required_failures=1 result=/srv/openclaw-you/workspace/telegram-research-agent/.playbook-artifacts/project_verification.json
```

Project verifier test summary:

```text
1 failed, 1002 passed, 281 subtests passed in 324.77s (0:05:24)
FAILED tests/test_product_ops.py::TestProductOps::test_ops_validation_passes_when_live_evidence_rows_exist
```

## Final Verification

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
<no output>
```

## PRM-11 Continuation Evidence

Scope:

- Implemented PRM-11 on-demand external verification requirement path.
- High-stakes categories `pricing`, `legal`, `medical`, `financial`,
  `career_market`, and `visa`, plus freshness/news/current or explicit external
  verification prompts, route deterministically through
  `request_external_verification`.
- `request_external_verification` is local only: no browser/web call, no
  external skill use, no automatic Telegram archive snippet collection, no
  persisted research note, and no profile/project/config mutation.
- Grounded answer contracts now expose separate archive evidence, external
  evidence, and unknowns sections for verification-required answers.
- Tool catalog validation rejects unapproved external-skill tool names while
  approved external skill allowlist remains empty.

Changed files:

- `src/assistant/pi_chat.py`
- `src/assistant/pi_tools.py`
- `src/assistant/pi_prompts.py`
- `tests/test_pi_chat.py`
- `tests/test_pi_tools.py`
- `AGENTS.md`
- `docs/CODEX_PROMPT.md`
- `docs/TEST_STRATEGY.md`
- `docs/tool_eval.md`
- `docs/PRIVACY_THREAT_MODEL.md`
- `docs/audit/PRM_DEEP_REVIEW_CONSOLIDATED_2026-07-27.md`

Verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_pi_tools.py tests/test_pi_chat.py -q
28 passed, 6 subtests passed in 2.06s
```

```text
python3 tools/test_tiers.py focused-prm
54 passed, 6 subtests passed in 1.85s
```

```text
python3 tools/test_tiers.py fast-contract
107 passed, 6 subtests passed in 50.27s
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
<no output>
```

Boundary evidence:

- No live Telegram ingestion, reaction sync, LLM extraction, Frontier, Radar,
  report generation, full archive indexing, embeddings, external web research,
  external skill execution, or production database migration was run.
- No raw Telegram text was written to docs or fixtures.
- No external-verification evidence is approved or stored; the implemented path
  records a requirement only.

## PRM-12 Continuation Evidence

Scope:

- Implemented PRM-12 confirmation-gated save/watch flow.
- Added `pi_memory_proposal.v1` proposal objects and exact confirmation tokens
  for Knowledge Notes, Watch Topics, project links, decisions, actions,
  experiments, and feedback.
- Added `propose_decision`; all proposal tools remain read-only and return
  `persisted=false` until confirmation.
- Added `confirm_save_proposal` as the only confirmation-gated write tool. It
  requires an explicit facade and exact proposal/token pair before persistence.
- Confirmed saves append `personal_memory_events` rows. Edit, delete, and
  rollback are represented as new audit events, not destructive updates.
- Chat save requests draft proposals only; session chat text is not durable
  memory without explicit confirmation.

Changed files:

- `src/assistant/pi_memory.py`
- `src/assistant/pi_chat.py`
- `src/assistant/pi_tools.py`
- `src/assistant/pi_prompts.py`
- `tests/test_pi_chat.py`
- `tests/test_pi_tools.py`
- `AGENTS.md`
- `docs/CODEX_PROMPT.md`
- `docs/TEST_STRATEGY.md`
- `docs/tool_eval.md`
- `docs/PRIVACY_THREAT_MODEL.md`
- `docs/audit/PRM_DEEP_REVIEW_CONSOLIDATED_2026-07-27.md`

Verification:

```text
PYTHONPATH=src python3 -m pytest tests/test_pi_tools.py tests/test_pi_chat.py -q
33 passed, 6 subtests passed in 2.19s
```

```text
python3 tools/test_tiers.py focused-prm
59 passed, 6 subtests passed in 2.09s
```

```text
python3 tools/test_tiers.py fast-contract
112 passed, 6 subtests passed in 47.21s
```

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
<no output>
```

Boundary evidence:

- Fixture tests used temporary SQLite databases only.
- No production database contents were modified.
- No live Telegram ingestion, reaction sync, LLM extraction, Frontier, Radar,
  report generation, full archive indexing, embeddings, external web research,
  external skill execution, or production database migration was run.
- No raw Telegram text was written to docs or fixtures.

## Open Boundaries

- Candidate retrieval queries remain unapproved and must not be treated as gold
  evidence.
- PRM-8 vector/hybrid retrieval remains blocked.
- PRM-9 through PRM-12 block review was completed by the corrective deep review
  recorded in `docs/audit/PRM_DEEP_REVIEW_PRM9_12_2026-07-27.md`. PRM-13
  remains unstarted and should proceed only by human direction beyond that gate.
- No production database migration, live ingestion, embeddings, external skill,
  dogfood start, release claim, or compatibility-file archive/delete/move was
  performed.
