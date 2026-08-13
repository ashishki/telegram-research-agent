# PRM-UX Roadmap — Operator Experience And Professional Personalization

Status: proposed task queue
Date: 2026-08-12

## Product Verdict

The repository has enough technical PRM substrate for private alpha testing:
local archive search, hybrid retrieval, citation-safe context assembly,
freshness/no-answer gates, Telegram/voice entry, confirmation-gated proposal
concepts, and bounded archive refresh exist.

The remaining blocker is product usefulness for this operator. The next phase
should not be a RAG infrastructure wave. It should make one Telegram
conversation pleasant, answer-first, professionally personalized, project-aware,
and measurable in real private dogfood.

## Target Experience

The normal interface is one Telegram conversation.

```text
operator text or voice
  -> infer intent/lens/project
  -> ask at most one compact clarification only when needed
  -> retrieve broadly from local archive and curated memory
  -> rerank/frame by lens and active project
  -> answer first in Russian by default when the user writes Russian
  -> cite sources and uncertainty
  -> offer one small next action
  -> write durable memory only after explicit confirmation
```

Manual commands remain fallback controls, not the mental model.

## Default Russian Answer Contract

Required sections:

1. `Короткий вывод`
2. `Что найдено`
3. `Почему это важно тебе`
4. `Что сделать`
5. `Где доказательства слабые`
6. `Источники`

Optional sections:

- `Сравнение подходов`
- `Связь с проектом`
- `Что изменилось`
- `Что проверить внешне`
- `Что пока игнорировать`

Rules:

- answer-first, not retrieval-first;
- no visible mode names in ordinary Telegram output;
- no model-call count, token count, cost/debug footer, local paths, raw DB IDs,
  or unexplained English internal labels;
- no more than one primary recommendation;
- zero recommendations is valid;
- query language controls response language;
- weak evidence says `недостаточно данных`;
- citations must support the exact claims they follow;
- background model knowledge is labelled;
- high-stakes/current facts show external-verification status.

## Deterministic Validators

Can be validated exactly:

- required sections present for ordinary Telegram research answers;
- forbidden technical strings absent from ordinary Telegram output;
- absolute `/srv/...` paths absent;
- raw database IDs absent unless explicitly debug mode;
- source section present when source-backed claims exist;
- `недостаточно данных` path present when answer gate blocks an answer;
- current/high-stakes questions expose external-verification status;
- write actions require confirmation before durable mutation;
- provider-egress flag is represented in receipts.

Requires human review:

- whether the short conclusion answers the operator's decision;
- whether professional relevance is meaningful;
- whether the one next action is useful;
- whether citations support the exact nuanced claim;
- whether the answer is comfortable on mobile;
- whether the lens/project inference feels right.

## Phases

### Phase A — Dogfood-Ready Daily UX

Minimum goal: start PRM-19 with a usable daily Telegram loop, not a complete
knowledge platform.

Order:

1. PRM-UX-0 Current Operator Experience And Documentation Audit
2. PRM-UX-1 Single Conversational Entrypoint And Intent Acknowledgement
3. PRM-UX-2 Answer-First Telegram Response Contract
4. PRM-UX-3 Professional Lens Profile V2
5. PRM-UX-4 Active Project Portfolio Context V2
6. PRM-UX-5 Incremental Archive Freshness And Operator Refresh Receipt
7. PRM-UX-6 Reaction Sync And Searchable Fast Lane
8. PRM-UX-7 Post-Answer Save, Watch, Project, And Feedback Actions
9. PRM-UX-10 Real-Question Evaluation And PRM-19 Instrumentation
10. PRM-UX-11 Documentation And Runbook Consolidation

Adjustment from the generic recommended order: this planning pass creates the
audit and core operator docs now, so full runbook consolidation can follow the
first UX implementation slices and document observed behavior rather than
speculative copy.

### Phase B — Professional Value Slices

Implement separately testable workflows:

1. PRM-UX-8A AI Systems And Project Application Workflow
2. PRM-UX-8B Career And Portfolio Gap Workflow
3. PRM-UX-8D Writer And Editor Brief Workflow
4. PRM-UX-8C Product And Enterprise AI Adoption Workflow
5. PRM-UX-8E Learning And Experiment Workflow
6. PRM-UX-9 Targeted Primary-Source Verification

Targeted external verification is not required for the first operator test if
the assistant clearly marks verification-required claims.

### Phase C — Operator Production Tests

PRM-19 records optional human-run production-test evidence. It does not block
implementation of later deterministic UX slices.

### Phase D — Secondary Surfaces And Cleanup

1. PRM-UX-12 Usage-Derived Weekly Recap
2. PRM-UX-13 Post-Production-Test Simplification And PRM-20 Handoff
3. Existing PRM-20 cleanup/archive

## PRM-UX Task Summaries

| Task | Outcome |
| --- | --- |
| PRM-UX-0 | Current operator-experience audit and documentation baseline. |
| PRM-UX-1 | Ordinary Telegram text/voice is the single normal entrypoint with compact intent acknowledgement. |
| PRM-UX-2 | Telegram output follows the answer-first Russian contract with validators. |
| PRM-UX-3 | Versioned professional lens profile separates recall/rerank/framing/action. |
| PRM-UX-4 | Versioned project portfolio context distinguishes priority/active/watch/reference/paused/archived. |
| PRM-UX-5 | Freshness plan for 6-24h archive updates and `/refresh` receipts, pending schedule approval. |
| PRM-UX-6 | Reaction sync fast lane designed so reaction failure does not block archive freshness. |
| PRM-UX-7 | Inline save/watch/project/action/feedback loop with explicit confirmation before writes. |
| PRM-UX-8A | AI systems evidence becomes one project action and one eval case. |
| PRM-UX-8B | Career requirements compare against portfolio evidence and gaps. |
| PRM-UX-8C | Enterprise AI adoption cases map to pain/owner/workaround/effect. |
| PRM-UX-8D | Writer/editor brief produces thesis, cases, counterargument, and verification needs. |
| PRM-UX-8E | Learning question becomes plain explanation plus one experiment. |
| PRM-UX-9 | Targeted primary-source verification path with trust records before external skills. |
| PRM-UX-10 | Real-question product-usefulness eval and PRM-19 instrumentation. |
| PRM-UX-11 | README/operator/runbook/legacy docs consolidation. |
| PRM-UX-12 | Usage-derived weekly recap from receipts or an approved fixture preview. |
| PRM-UX-13 | Post-production-test simplification plan and PRM-20 handoff. |

## Dependency Graph

```text
PRM-UX-0
  -> PRM-UX-1 -> PRM-UX-2
  -> PRM-UX-3 -> PRM-UX-4
  -> PRM-UX-5 -> PRM-UX-6
  -> PRM-UX-7
  -> PRM-UX-10

PRM-UX-0 -> PRM-UX-11
PRM-UX-3/PRM-UX-4/PRM-UX-2 -> PRM-UX-8A
PRM-UX-3/PRM-UX-4/PRM-UX-10 -> PRM-UX-8B
PRM-UX-3/PRM-UX-2 -> PRM-UX-8D
PRM-UX-3/PRM-UX-4 -> PRM-UX-8C
PRM-UX-3/PRM-UX-4/PRM-UX-2 -> PRM-UX-8E
PRM-UX-2/PRM-UX-9 -> later externally verified answer slices
PRM-UX-10 -> PRM-UX-12 -> PRM-UX-13 -> PRM-20
PRM-19 is optional human production-test evidence and may inform PRM-20
```

## Operator Production Tests

Human production tests are optional evidence collection. They may use the
privacy-safe receipt schema when the operator chooses to record a session, but
they do not gate completion of deterministic UX tasks. Any live refresh,
reaction sync, provider egress, durable write, runtime change, or compatibility
cleanup remains subject to its own explicit approval boundary.

## Freshness Plan

Do not change the current weekly timer without approval. Proposed target:

- incremental archive freshness every 6-24 hours;
- no LLM, no report generation, no Radar/Frontier;
- idempotent bounded Telegram ingest plus FTS update;
- weekly maintenance for vector sidecar, dedupe, enrichment, health/eval
  receipts, backup/rollback checks;
- manual `/refresh` Telegram action that returns counts, latest post age, and
  reaction summary.

The current timer uses Europe/Berlin. The operator's actual timezone needs
confirmation before changing schedule or systemd timezone.

## Reaction Plan

Recommended routine shape:

```text
archive refresh succeeds or manual reaction refresh requested
  -> separate reaction sync job
  -> resolve personal reactions
  -> confirm canonical post exists
  -> make/search-check archive document
  -> apply temporary interest boost
  -> queue selective enrichment
  -> emit privacy-safe receipt
  -> show operator summary
```

Keep reaction sync separate from archive refresh. Rationale: Telethon reaction
visibility and credential failures should not block archive freshness. Reaction
sync failure should produce a receipt and leave archive search fresh.

Routine reaction sync remains blocked until the operator records credential
scope, Telethon reaction visibility, source volume, rate limits, failure
handling, rollback, and approval for the exact timer/service boundary.

## Targeted Primary-Source Verification

This is a bounded workflow, not unrestricted web research.

Trigger: `Проверить первоисточники`.

Use when facts are current, high-stakes, tied to model/API/pricing changes,
GitHub releases, benchmark claims, job-market signals, product/business claims,
or legal/medical/financial/visa topics.

Evidence classes:

- `telegram_archive`;
- `official_documentation`;
- `github_repository`;
- `research_paper`;
- `independent_case`;
- `model_background`;
- `unknown`.

Before external skills are enabled, create trust records and prefer direct
official docs/APIs or existing approved tooling.

## Evaluation Updates Needed

- `docs/retrieval_eval.md`: add real-query slices for professional-lens
  reranking, active-project routing, source diversity, reaction recall,
  freshness questions, no project match, and follow-up continuity.
- `docs/generation_eval.md`: add answer-first section checks, mobile comfort
  review, "one next action" review, citation-to-claim review, and
  verification-required wording.
- `docs/tool_eval.md`: add inline save/watch/project/action/feedback proposal
  checks and confirmation-before-write checks.
- `docs/agent_eval.md`: add ordinary-message intent selection, ambiguity,
  wrong-lens recovery, volatile follow-up, and no unsupported chat fallback.
- `docs/final_acceptance_plan.md`: separate retrieval/generation mechanics from
  product-usefulness labels.
- Dogfood evidence schema: add real-question fields listed in
  `docs/prm19_dogfood_plan.md`.

Human usefulness labels are primary product evidence. LLM judge output remains
advisory until calibrated.

## Anti-Complexity Rules

- Do not introduce a new vector backend, agent framework, graph database,
  dashboard, Mini App, second bot, public SaaS, or broad cleanup before
  dogfood.
- Do not use personalization to reduce raw retrieval recall.
- Do not bundle retrieval redesign with answer-generation rewrite.
- Do not bundle schema migration with broad UX redesign.
- Do not make every task high-risk or heavy mode.
- Do not treat generated labels or deterministic fixture pass status as user
  value.
- Do not delete or archive compatibility code/docs before PRM-19 evidence and
  explicit approval.
