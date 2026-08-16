# PRM Operator Smoke Test

Status: required before candidate deployment or compatibility cleanup
Updated: 2026-08-16

## Purpose

Automated and silver evaluations are regression evidence only. This smoke test determines whether the intent-first archive answer contract is actually useful to the repository owner on realistic questions.

The smoke test is not PRM-19 dogfood, does not establish product value, and must not be used to justify compatibility cleanup or release claims.

## Safety boundary

Run against a production-equivalent local checkout and the operator-owned archive database in read-only mode.

Required defaults:

```bash
export PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=0
export PRM_TELEGRAM_RAG_LLM_SYNTHESIS=0
```

The smoke must not:

- send Telegram messages;
- modify the canonical database;
- run migrations;
- run ingestion or reaction sync;
- export archive text;
- enable external embeddings or hosted vector services;
- start or restart systemd units;
- create public reports containing queries, answers, snippets, or source URLs.

Private operator notes may contain query-level observations but must remain gitignored and owner-local.

## Preconditions

1. Focused PRM and retrofit-boundary tests pass.
2. MAT safety and public privacy checks pass.
3. Deployment parity for any later manual Telegram test can be established.
4. The candidate replay tool runs successfully with the synthetic fixture.
5. The previous known-good commit is recorded for rollback.

## Reference replay

```bash
PYTHONPATH=src python3 tools/prm_replay_query.py \
  --query 'Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?' \
  --fixture tests/fixtures/prm_agent_evals_replay.json \
  --private-trace data/evals/private/prm_replay/agent-evals.json
```

Expected:

- intent `archive_to_action`;
- contract `archive_research.v2`;
- no project context;
- no external verification;
- direct source above Agent Operations;
- decision template absent.

## Owner query set

Use at least 15 questions. The following 18-question set covers the critical boundaries.

### Archive lookup and synthesis

1. `Что у меня было про evals агентов?`
2. `Найди в архиве материалы про agent evaluation.`
3. `Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?`
4. `Что есть в архиве про Agent Operations?`
5. `Что архив говорит про groundedness?`
6. `Прямых материалов нет? Тогда покажи смежные.`
7. `Что у меня было про RAG retrieval?`
8. `Найди материалы про runtime failures.`

### Explicit project mapping

9. `Какие практики из сохранённых материалов подходят для Eval-Ground-Truth-Lab?`
10. `Что из найденного связано с Agent-Runtime-Grid?`
11. `Как материалы про retrieval связаны с telegram-research-agent?`

### Decision support

12. `Стоит ли мне добавить agent evals в backlog проекта Eval-Ground-Truth-Lab?`
13. `Что приоритизировать для Agent-Runtime-Grid: retry evals или cost telemetry?`

### Current external facts

14. `Что сейчас известно про новый внешний benchmark?`
15. `Проверь актуальную официальную документацию по external benchmark.`

### Memory and action boundaries

16. `Сохрани эту находку как заметку.`
17. `Свяжи выбранный источник с Eval-Ground-Truth-Lab.`
18. `Создай действие из этого ответа.`

## Expected intent matrix

| Questions | Expected intent | Project context | External verification |
|---|---|---:|---:|
| 1–8 | archive lookup/synthesis/to-action | No unless explicitly named | No |
| 9–11 | project mapping | Yes, named project only | No by default |
| 12–13 | decision support | Yes | Claim-dependent |
| 14–15 | current-fact verification | Only if separately named | Yes |
| 16–18 | memory action | Only when needed by the requested object | No |

## Per-answer checklist

Score each item `pass`, `partial`, or `fail`.

### Directness

- The first two or three sentences answer the actual question.
- The assistant explicitly states whether direct materials were found.
- Adjacent materials are not presented as direct matches.

### Retrieval

- The first source is more directly relevant than broad adjacent sources.
- Mixed Russian-English terminology is preserved.
- A hard negative such as Agent Operations does not replace agent-evaluation material.
- A no-result case does not invent archive content.

### Project context

- No project appears unless named or selected.
- A named project does not replace the archive findings.
- Project mapping is evidence-specific rather than generic descriptor prose.

### Evidence policy

- One archive source is enough to report that the material exists.
- Applicability is labelled as inference where appropriate.
- Current external claims are not made from archive evidence alone.
- Source links remain visible and correspond to the displayed finding.

### Presentation

- No irrelevant `Решение / Главный риск / Критерий успеха` template appears for archive questions.
- The first useful information appears immediately.
- The response fits comfortably into one or two Telegram messages.
- The answer avoids internal terms such as claim ledger, linked-source evidence, retrieval policy, or model telemetry.

### Actions

- Feedback appears before productive actions.
- `Показать ещё` and `Уточнить поиск` are available when relevant.
- Action/experiment/watch controls are not shown before relevance is established.
- Durable saves require confirmation and the confirmation accurately describes what will be persisted.

## Recording format

Store owner-local results as JSONL under:

```text
data/evals/private/prm_owner_smoke/2026-08-16.jsonl
```

Suggested private schema:

```json
{
  "schema_version": "prm_owner_smoke_case.v1",
  "case_number": 1,
  "query_hash": "<sha256 prefix>",
  "expected_intent": "archive_lookup",
  "actual_intent": "archive_lookup",
  "directness": "pass",
  "retrieval": "pass",
  "project_context": "pass",
  "evidence_policy": "pass",
  "presentation": "pass",
  "actions": "pass",
  "useful": "yes|partial|no",
  "trust": "high|medium|low",
  "rephrase_required": false,
  "incorrect_or_irrelevant_evidence": false,
  "operator_note": "<private note>",
  "privacy": {
    "commit_allowed": false,
    "contains_raw_archive_text": false
  }
}
```

Do not place raw questions, raw answers, snippets, or source URLs in a public aggregate. A public summary may contain only counts and rates.

## Acceptance thresholds

Critical cases 1–4, 9, 12, and 14 must all pass their intent and boundary checks.

Overall minimum:

- intent accuracy: 100% on critical cases, at least 95% overall;
- implicit project-context rate: 0%;
- external-verification false-positive rate: 0% for archive questions;
- direct-answer-start rate: at least 95%;
- adjacent-as-direct errors: 0 on the smoke set;
- irrelevant decision-template rate for archive questions: 0%;
- operator `useful=yes` or `partial`: at least 80%;
- operator `trust=low`: no more than 10%;
- no privacy or write-boundary violation.

A single privacy violation, unconfirmed durable write, or current-fact fabrication is a stop-ship failure.

## Failed-case loop

For every `partial` or `fail`:

1. capture a privacy-safe private trace;
2. identify whether the miss is routing, retrieval, relevance classification, synthesis, project mapping, rendering, or actions;
3. add an owner-reviewed private regression case;
4. change deterministic policy through a normal PR;
5. rerun the focused regression and the affected smoke cases;
6. do not automatically retrain or modify memory/ranking from one feedback click.

## Deployment decision

After smoke completion, record one of:

- `accepted_for_manual_runtime_test`;
- `needs_revision`;
- `rejected`.

Acceptance permits only a controlled manual-test deployment. It does not start dogfood, approve compatibility deletion, or establish product usefulness beyond the tested operator session.
