# PRM-14 Project Context And Decision Support - 2026-07-28

Status: implementation evidence
Scope: PRM-14 Project Context And Decision Support

## Gate

PRM-14 continued within the open PRM-13 through PRM-17 implementation block.
The next batched deep-review gate remains the PRM-13 through PRM-17 block review
before PRM-18. Immediate review is still required earlier for privacy egress,
unsafe writes, production migrations, vector backend adoption, external skill
approval, dogfood start, release claims, or compatibility-file
archive/delete/move.

## Scope

- Added deterministic `project_context_decision_support.v1` DTO support.
- Added `analyze_project_context` to the bounded PI tool catalog as a read-only
  assistant tool.
- The tool loads active project descriptors from local descriptor files and
  combines descriptor fields, bounded SQLite FTS archive retrieval, and curated
  knowledge search.
- Project context labels are `direct_implication`, `weak_watch`,
  `learning_relevance`, and `no_match`.
- Direct implications cite archive/source evidence, name descriptor fields used,
  and return read-only candidate next steps.
- Weak keyword-only, learning-only, and no-match cases do not produce project
  action recommendations.
- Project-application chat routes bypass LLM planning and render deterministic
  answers from the DTO.
- Build approval, code mutation, and project mutation commands remain forbidden
  by the explicit PI tool allowlist.

## Changed Files

- `src/assistant/project_context.py`
- `src/assistant/pi_facade.py`
- `src/assistant/pi_tools.py`
- `src/assistant/pi_chat.py`
- `src/assistant/pi_prompts.py`
- `tests/test_project_context.py`
- `tests/test_pi_tools.py`
- `tests/test_pi_chat.py`
- `tools/test_tiers.py`
- `AGENTS.md`
- `docs/CODEX_PROMPT.md`
- `docs/ARCHITECTURE.md`
- `docs/AGENT_HARNESS_DESIGN.md`
- `docs/TEST_STRATEGY.md`
- `docs/tasks.md`
- `docs/personal_research_memory_product_contract.md`
- `docs/generation_eval.md`
- `docs/tool_eval.md`
- `docs/audit/AUDIT_INDEX.md`
- `docs/audit/PRM14_PROJECT_CONTEXT_2026-07-28.md`

## Verification

```text
PYTHONPATH=src python3 -m pytest tests/test_project_context.py tests/test_pi_tools.py tests/test_pi_chat.py -q
47 passed, 6 subtests passed in 5.59s
```

```text
python3 tools/test_tiers.py focused-prm
78 passed, 6 subtests passed in 11.38s
```

```text
python3 tools/test_tiers.py fast-contract
131 passed, 6 subtests passed in 33.79s
```

Final pre-push checks:

```text
python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references
playbook_validate: errors=0 warnings=0
```

```text
git diff --check
<no output>
```

## Boundary Evidence

- No live Telegram ingestion, reaction sync, LLM extraction, Frontier, Radar,
  report generation, full archive indexing, embeddings, external web research,
  external skill execution, production database migration, dogfood start,
  release claim, or compatibility-file archive/delete/move was performed.
- No production database contents were modified.
- Tests used synthetic fixture strings and temporary SQLite databases only.
- No raw Telegram text was written to docs or fixtures.
- No LLM calls were required for PRM-14 project-context fixture answers.
- Candidate retrieval rows remain candidates, not gold labels.
- PRM-8 vector/hybrid retrieval remains blocked.
- PRM-15 is next only if the human operator chooses to proceed within the
  PRM-13 through PRM-17 block.
