# PRM Intent and Answer Contract

Status: active candidate contract
Updated: 2026-08-16
Scope: Telegram and CLI PRM question-answering path

## Purpose

The assistant must answer the operator's actual question before it offers project mapping, external verification, or a durable action. Archive lookup, archive synthesis, project mapping, decision support, current-fact verification, and memory actions are separate product jobs. They may share retrieval infrastructure, but they must not share one mandatory user-facing template.

This contract is designed for a technical single operator using mixed Russian-English queries such as `agent evals`, `RAG`, `ground truth`, and `runtime`.

## Primary intents

### `archive_lookup`

Use when the operator asks what exists in the retained Telegram archive or asks to find a post/material.

Examples:

- `Что есть в архиве про agent evals?`
- `Найди в архиве материалы про agent evaluation.`
- `Что у меня было про Agent Operations?`

Required behavior:

- search the local archive;
- report direct, partial, and adjacent matches separately;
- do not select a project implicitly;
- do not require external verification;
- do not render a decision template.

Response contract: `archive_lookup.v2`.

### `archive_synthesis`

Use when the operator asks what the archive says about a topic or requests a synthesis of saved material.

Required behavior:

- lead with the archive-scoped conclusion;
- preserve source provenance;
- distinguish source facts from analytical inference;
- keep project context optional and secondary.

Response contract: `archive_research.v2`.

### `archive_to_action`

Use when the operator asks what from the archive is practically applicable but does not explicitly request a project decision.

Examples:

- `Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?`
- `Какие практики из найденного можно попробовать?`

Required behavior:

- answer the archive question first;
- list applicability as an explicit analytical inference;
- do not treat `сейчас` or `now` alone as a request for live external verification;
- do not infer a target project unless the operator names one;
- do not mention backlog, project blockers, acceptance criteria, or independent-source policy in the main answer.

Response contract: `archive_research.v2`.

### `project_mapping`

Use only when the operator names a project or explicitly selects one and asks how archive findings relate to it.

Examples:

- `Какие практики подходят для Eval-Ground-Truth-Lab?`
- `Свяжи эти материалы с Agent-Runtime-Grid.`

Required behavior:

- preserve the archive findings as the primary evidence;
- map only selected evidence to the named project;
- do not run a broad project-confirmation search that replaces the original result set;
- clearly label direct implication, learning relevance, weak watch, or no match.

Response contract: `project_mapping.v2`.

### `decision_support`

Use only when the operator explicitly asks for a decision, prioritization, choice, or backlog change.

Examples:

- `Стоит ли добавить agent evals в backlog проекта X?`
- `Что из двух подходов приоритизировать?`

Required behavior:

- require a named project where the decision is project-specific;
- show the decision, evidence, risk, and next proof;
- do not activate from the word `применимо` alone;
- retain human confirmation for durable changes.

Response contract: `decision_support.v2`.

### `current_fact_verification`

Use when the claim depends on current external state and the operator explicitly asks for it.

Examples:

- `Что сейчас известно про новый внешний benchmark?`
- `Проверь актуальную официальную документацию.`

Required behavior:

- do not present retained Telegram material as current truth;
- require a separately approved primary-source verification path;
- preserve archive material only as historical/discovery context;
- fail closed when external verification is unavailable or not approved.

Response contract: `current_fact.v2`.

### `memory_action`

Use when the operator explicitly asks to save, watch, link, or create a stored action/experiment.

Required behavior:

- draft first;
- persist only after explicit confirmation;
- state what is actually persisted;
- never imply that a stored `action` object changed a GitHub backlog or external task system.

## Routing precedence

1. Explicit command mode is respected, but the semantic intent is still recorded.
2. Explicit decision language plus a named project selects `decision_support`.
3. Explicit project applicability plus a named project selects `project_mapping`.
4. Explicit current external-fact language selects `current_fact_verification`.
5. Archive scope plus applicability selects `archive_to_action`.
6. Archive scope plus synthesis language selects `archive_synthesis`.
7. Archive scope alone selects `archive_lookup`.
8. A safe local archive research path is the default.

Archive-scope markers take precedence over a lone `сейчас`, `now`, or `current`. External verification is activated by the claim being external/current, not by one temporal token.

## Project-context rules

- No implicit project descriptor selection for `archive_lookup`, `archive_synthesis`, or `archive_to_action`.
- A topic keyword such as `eval` must never select a project by substring alone.
- Project mapping is a secondary operation over already selected evidence.
- An inferred possible project relation may be offered as a follow-up action, but it must not alter the primary archive answer.
- Project policy fields must not enter an archive synthesis prompt unless the operator requested project mapping or decision support.

## Retrieval contract

The raw archive path is phrase-first and bounded:

1. preserve the canonical mixed-language phrase;
2. search exact/near-exact aliases;
3. search bounded concept expansions;
4. build a candidate pool;
5. classify candidates as `direct`, `partial`, `adjacent`, or `unrelated`;
6. rerank by relevance class and directness before lexical/vector tie-breakers;
7. select evidence only after reranking.

For `agent evals`, bounded variants include:

- `agent evals`;
- `agent evaluation`;
- `evaluation of agents`;
- `LLM agent evaluation`;
- `agent benchmark`;
- `agent task success`;
- `agent tool-call correctness`;
- `agent groundedness`.

A broad material about Agent Operations is `adjacent` unless it contains a concrete evaluation practice.

## Evidence rules

| Claim | Minimum evidence |
|---|---|
| A material exists in the archive | One correctly identified archive document |
| A material is a direct match | Direct phrase, alias, or combined agent-and-evaluation concepts in the source span |
| A material is adjacent | A related agent context without direct evaluation practice |
| A practice may be tried | One relevant source plus an explicitly labelled inference |
| A practice is proven to improve a project | Project result or adequate independent evidence |
| An external fact is current | Approved current primary-source verification |
| A durable project change should occur | Explicit decision intent plus human confirmation |

Independent corroboration is not required to report archive presence. It may be required for generalization, current external facts, high-impact decisions, or automated action.

## Archive answer contract

Schema: `prm_archive_answer.v2`.

Required fields:

- `primary_intent`;
- `response_contract_id`;
- `direct_answer`;
- `answer_status`;
- `result_summary.direct_count`;
- `result_summary.partial_count`;
- `result_summary.adjacent_count`;
- direct, partial, and adjacent findings;
- applicability inferences when requested;
- limitations;
- sources;
- bounded search refinements;
- explicit project and external-verification boundaries.

Required presentation order:

1. direct answer;
2. result counts;
3. direct findings;
4. partial and adjacent findings;
5. practical applicability when requested;
6. limitations;
7. sources.

When no direct material is found, the answer must explicitly say so. Adjacent evidence must never be presented as a direct answer.

Archive answers must not contain these default sections:

- `Решение`;
- `Контекст проекта`;
- `Цель проекта`;
- `Главный риск`;
- `Критерий успеха`;
- `Что изменило бы решение`;
- backlog impact;
- second-independent-source policy.

## Telegram contract

Archive answers should fit into one message where practical and no more than two messages. The first useful statement appears immediately.

Archive lookup actions are context-aware:

- feedback: `Полезно`, `Частично`, `Мимо`;
- retrieval follow-up: `Показать ещё`, `Уточнить поиск`;
- `Сохранить заметку` only after direct or partial evidence;
- project linking only after relevant evidence and explicit project context.

Do not show `Следить`, `Сохранить действие`, or `Сохранить эксперимент` before relevance is established. Feedback is recorded immediately; durable memory objects remain confirmation-gated.

## Privacy and observability

Private traces may contain:

- intent and response contract;
- route reason codes;
- retrieval policy;
- hashed evidence IDs;
- direct/partial/adjacent counts;
- bounded scores and rejection reasons;
- render length and mode;
- feedback label, component, and reason.

Public reports must not contain raw queries, raw Telegram text, source URLs, chat IDs, private candidate IDs, or provider payloads.

## Acceptance criteria

For the reference query:

`Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?`

Expected route:

```text
primary_intent = archive_to_action
response_contract_id = archive_research.v2
retrieval_query = agent evals
project_context_required = false
external_verification_required = false
decision_requested = false
```

If only an Agent Operations fixture is available, the answer must report zero direct matches and show the material as adjacent. If a direct evaluation fixture is available, it must rank above Agent Operations. The decision template must not render in either case.
