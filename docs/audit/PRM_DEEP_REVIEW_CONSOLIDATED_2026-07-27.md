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

## Final Verification

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
<no output>
```

## Open Boundaries

- Candidate retrieval queries remain unapproved and must not be treated as gold
  evidence.
- PRM-8 vector/hybrid retrieval remains blocked.
- PRM-11 through PRM-12 remain unclosed; the PRM-9 through PRM-12 block review
  is not complete.
- No production database migration, live ingestion, embeddings, external skill,
  dogfood start, release claim, or compatibility-file archive/delete/move was
  performed.
