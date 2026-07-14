# Intelligence Report V2 Product Contract

Version: `tra-intelligence-contract.v2`  
Status: planned reader contract; IRX-1 through IRX-5 plus IRX-8 through IRX-10
foundations implemented and verified
Queue: `IRX - Intelligence Report Experience And Editorial Quality`

This contract defines the reader-facing behavior of Weekly Intelligence Brief
V2 and Knowledge Atlas V2, and separates both from the technical Knowledge
Audit Explorer. It is the product boundary for renderers, editorial synthesis,
quality gates, retrieval projections, and operator feedback. It does not claim
that the current W29 reports satisfy the contract.

## Product Outcome

The weekly package must help one private operator understand, decide, act, and
learn. After a five-to-seven-minute Brief, the operator should be able to state:

1. `Я понял X.`
2. `Я проверил Y.`
3. `Я улучшил проект Z.`
4. `Я решил пока не делать W.`

Visual polish without those outcomes is not success. Report V2 does not require
new sources, raw Telegram RAG, vector retrieval, a public UI, or weaker evidence
gates.

## Surface And Layer Boundary

Report V2 has three surfaces with different jobs.

| Surface | Primary job | Default audience | Default detail |
|---|---|---|---|
| Weekly Intelligence Brief V2 | Explain the completed week and produce a bounded decision | operator | concise and decision-first |
| Knowledge Atlas V2 | Show cumulative canonical knowledge, evidence maturity, and learning progression | operator | visual with progressive disclosure |
| Knowledge Audit Explorer | Inspect atoms, sources, raw memberships, ranking inputs, and construction defects | operator/developer in audit mode | complete technical detail |

The processing boundary is:

```text
machine/audit inputs
  -> deterministic period and run validation
  -> canonical thread and evidence selection
  -> bounded editorial_intelligence.v1 JSON
  -> deterministic validation
  -> deterministic V2 renderers and static visuals
  -> reader-value quality gates
  -> Brief V2 + Atlas V2

machine/audit inputs
  -> Knowledge Audit Explorer
```

The editorial model may explain validated inputs, but it must not generate HTML,
invent claims, weaken Radar gates, or change projects, code, profile, or config.
The renderer may arrange validated content, but it must not silently create a
decision that is absent from editorial JSON.

## Shared Identity Contract

Every V2 sidecar and HTML artifact belongs to one
`weekly_run_manifest.v1` run and contains or links to:

- `run_id`;
- `generated_at`;
- `reporting_week`;
- `analysis_period_start` and `analysis_period_end`;
- `period_mode`;
- `run_status` and `partial`;
- `manifest_path`;
- source schema and renderer versions.

The default scheduled weekly report describes the last completed ISO week. Its
reader title uses inclusive dates, while the stored interval remains half-open.
Generation time is displayed separately.

Example:

```text
Недельный бриф: 6-12 июля 2026
Сформировано: 13 июля 2026, 09:02 CEST
Статус выпуска: полный
```

Filename similarity is not proof that Brief, Atlas, Frontier Analysis, and Radar
belong to the same run. The manifest identity and period checks are authoritative.

## Reader-Facing Language

- Navigation, headings, summaries, actions, confidence explanations, empty
  states, warnings, feedback prompts, and status labels are Russian.
- Product names, repository names, code paths, source titles, and short source
  quotations may remain in their original language.
- Raw enums are translated into reader meaning. For example,
  `do_not_build` becomes `Не собирать`, with a plain-language reason.
- English text copied from an internal schema is a quality failure, not a
  localization exception.
- Acronyms are expanded on first use when a Russian reader cannot be expected to
  know them.
- Explanations use direct language and short sentences. Model/vendor names do
  not substitute for an idea-level explanation.

Quality measurement should classify Russian editorial prose separately from
source quotations, code, paths, and proper names. The required outcome is
Russian reader copy, not an artificial ban on Latin characters.

## Shared Evidence And Confidence Contract

Evidence maturity and conclusion confidence are separate dimensions.

### Evidence Maturity

Allowed reader levels are:

1. `Один Telegram-источник`;
2. `Повторяющийся Telegram-сигнал`;
3. `Несколько независимых каналов`;
4. `Проверен первичный источник`;
5. `Подтверждено вне Telegram`;
6. `Достаточно для решения`.

A repeated commentary chain is not independent corroboration. Source and thread
visuals must distinguish total mentions from independent supporting sources.

### Confidence

Allowed reader labels are `Низкая`, `Средняя`, and `Высокая`. Every label has a
short reason derived from deterministic metadata, for example:

> Уверенность: средняя. Сигнал повторился в трех каналах, но первичный источник
> еще не проверен.

Low maturity forces cautious language. A high model probability cannot promote
weak evidence to decision-grade evidence.

### Evidence Access

- Every source-grounded claim has one or more resolvable `evidence_refs` in the
  sidecar.
- Reader cards show evidence strength and source count, not raw atom IDs.
- A collapsed `Источники и ограничения` disclosure may show source titles,
  links, dates, and a concise caveat.
- Raw atom records, membership traces, ranking factors, ingestion diagnostics,
  and full quotations belong in the Audit Explorer.
- Charts summarize and navigate evidence. They never count as evidence for the
  claim they visualize.

## Project Intelligence V2

`project_intelligence.v2` is the deterministic project-action authority for
future Report V2 readers. IRX-9 persists it only as an explicit shadow artifact
at `<output>/<run_id>/project/project-intelligence.v2.json`; V1 Brief, Atlas,
retrieval, and Obsidian projections remain unchanged. IRX-6 owns the reader
adapter and may consume no other source as Project Impact authority.

Project-specific action copy is host-owned in an opt-in
`project_action_permissions.v1` block under the active project descriptor. Each
permission fixes:

- configured `project_name` and repository;
- one or more exact canonical-thread refs;
- `why_this_project`, affected component, and suggested change;
- one to eight normalized repository-relative likely files;
- bounded `XS|S|M` effort;
- Russian acceptance criteria and risk;
- deterministic priority.

A `confirmed` action requires all of the following in the same run:

1. the configured project and permission exist;
2. the signal and descriptor share the exact canonical-thread ref;
3. the signal belongs to the bounded IRX-5 input package;
4. confidence ceiling is `medium` or `high`;
5. at least one cited ref belongs to that signal and is both decision-grade and
   non-context;
6. component, change, files, effort, criteria, risk, repository, and priority
   equal the host descriptor exactly.

Lexical project relevance and legacy keyword diagnostics cannot satisfy these
conditions. They may remain `watch` or `rejected_overlap` audit context only.
The other non-actionable states are `learning_only` and
`existing_project_context`. The zero state is
`no_confirmed_implication`. Reader surfaces collapse these states into concise
Russian copy, while the sidecar retains their distinct bounded reasons and
evidence closure.

The projection returns no more than two distinct permission/signal actions.
Stable action/audit refs, exact run and completed-week identity, immutable input
hash/cache bytes, safe text/refs/paths, deterministic selection, and the
32-record audit boundary fail closed. An unselected `confirmed` audit is valid
only after the two-action cap or when the same permission/signal authority is
already represented through another exact canonical ref.

Only revalidated non-empty actions may be converted to the existing IRX-5
permission shape (`project_action_ref`, `signal_id`, project, `allowed`, and
same-signal evidence refs). The extractor requires the exact preliminary input
package and loaded descriptors; empty context cannot grant authority. Project
shadow failure produces zero editorial permissions and cannot block V1 or a
separately requested editorial shadow. Project-only generation performs no LLM,
network, database mutation, or repository change.

## MVP Radar Reader V1

`mvp_radar_reader.v1` is the sole deterministic Radar input authority for
Report V2 consumers. It wraps the IRX-2 immutable handoff; it does not recompute
candidate ranking, evidence scores, source gates, or recommendation semantics.

The projection reloads and validates the exact `weekly_run_manifest.v1`,
`radar_run_binding.v1`, raw producer JSON, and opportunity-seed export. It
requires run, completed-week, half-open period, schema, status, path, selected
candidate, seed, and SHA-256 parity. An authoritative projection additionally
requires the current manifest Radar stage to be `succeeded`.

Reader states are `available`, `no_candidate`, `missing`, `invalid`, `disabled`,
and `unbound_legacy`. Only `available` can carry a selected candidate and a
permission-shaped `reader_decision`; `no_candidate` is a successful empty Radar
result, not an unavailable artifact. Every other state has
`reader_decision=unavailable`. A legacy candidate or recommendation may be
retained only in explicitly diagnostic fields.

Matched external proof is distinct from matching KIR provenance and unmatched
context. Market context, Telegram, X, negative signals, unsupported source
types, stale KIR, unbound payloads, and self-declared reader markers cannot
satisfy the build or focused-experiment gate. Canonical, retrieval, visual,
editorial, Brief, and Hermes/PI adapters receive authority explicitly only
after manifest validation; malformed or oversized JSON fails closed.

## Editorial Intelligence V1

`editorial_intelligence.v1` is the target sole narrative input to the Brief V2
renderer. IRX-5 currently persists it as an explicit opt-in shadow artifact;
neither the V1 renderers nor any V2 renderer consumes it yet. Renderer
consumption belongs to IRX-6 after its upstream dependencies pass. The artifact
is produced after deterministic period, evidence, canonical-thread, reaction,
project, feedback, and Radar selection. The strong model receives only the
bounded selected package, not all Telegram posts or the whole audit database.

The model may select and explain a weekly thesis, at most three signals,
act/study/watch/ignore decisions, concrete permitted project actions, Radar
meaning, uncertainty, and what not to do. It may not introduce an evidence ref,
claim, project permission, or Radar state absent from its input. It emits strict
JSON, never HTML or SVG.

Required output shape:

```json
{
  "schema_version": "editorial_intelligence.v1",
  "run_id": "tra-weekly-2026-W28-20260713T070252Z",
  "reporting_period": {
    "reporting_week": "2026-W28",
    "analysis_period_start": "2026-07-06T00:00:00Z",
    "analysis_period_end": "2026-07-13T00:00:00Z"
  },
  "weekly_thesis": {
    "title": "Проверяемость становится ограничением агентной разработки",
    "plain_language_summary": "...",
    "why_for_operator": "...",
    "confidence": "low|medium|high",
    "evidence_refs": ["evidence:..."]
  },
  "decision_matrix": {
    "act": ["signal:..."],
    "study": ["signal:..."],
    "watch": ["signal:..."],
    "ignore": ["signal:..."]
  },
  "signals": [
    {
      "signal_id": "signal:...",
      "decision": "act|study|watch|ignore|verify_first",
      "title": "...",
      "what_happened": "...",
      "plain_explanation": "...",
      "what_changed": "...",
      "why_for_operator": "...",
      "confidence": "low|medium|high",
      "evidence_refs": ["evidence:..."],
      "reaction_effect": {
        "effect": "selection_changed|rank_changed|linked_only|none",
        "reader_reason_ru": "..."
      },
      "project_implications": ["project-action:..."],
      "next_action": {
        "title": "...",
        "acceptance_criteria": ["..."]
      },
      "do_not_do": "..."
    }
  ],
  "project_actions": [],
  "feedback_effect": {
    "confirmed_events_considered": 0,
    "applied_changes": [],
    "unchanged": [],
    "code_config_required": [],
    "rejected": [],
    "pending": []
  },
  "mvp_summary": {
    "radar_ref": "radar:...",
    "reader_decision": "investigate|reject|build_allowed|unavailable",
    "why": "...",
    "what_would_change_it": "..."
  },
  "visual_specs": [],
  "feedback_targets": [],
  "generation_status": "complete",
  "partial": false,
  "fallback_reason": null,
  "generation_receipt": {
    "schema_version": "editorial_intelligence_generation.v1",
    "prompt_version": "editorial-intelligence-v1",
    "editorial_schema_version": "editorial_intelligence.v1",
    "requested_model": "<strong-model-route>",
    "model": "<actual-receipt-model>",
    "input_hash": "sha256:<64 lowercase hex characters>",
    "generated_at": "2026-07-13T07:03:00Z",
    "max_input_json_chars": 80000,
    "max_tokens": 6000,
    "planned_cost_ceiling_usd": 0.8,
    "cost_ceiling_exceeded": false,
    "input_tokens": 0,
    "output_tokens": 0,
    "estimated_cost_usd": 0.0,
    "duration_ms": 0,
    "attempts": 1,
    "usage_recorded": false,
    "completion_mode": "model",
    "validation_errors": []
  }
}
```

The model-authored object ends at `feedback_targets`. The host alone adds
`generation_status`, `partial`, `fallback_reason`, and the complete
`generation_receipt`; the model cannot author or copy audit metadata. For a
complete artifact, requested and actual model match, `completion_mode=model`,
at least one attempt is recorded, and `validation_errors` is empty. A partial
artifact uses `completion_mode=deterministic_fallback`, names a bounded fallback
reason, and retains only bounded validation error codes/class names. The receipt
records prompt/editorial schema versions, input hash, configured caps, planned
cost ceiling and warning, tokens, measured cost, latency, attempts, and whether
usage accounting was recorded.

The deterministic validator and production boundary enforce all of the
following:

- the exact run ID, completed reporting period, canonical snapshot fingerprint,
  persisted manifest identity, and immutable input hash;
- at most three returned signals and two project actions, exact decision-matrix
  coverage, strict enums and object keys, Russian/plain reader copy, no HTML/SVG
  or other markup, and no generic or duplicate action;
- source-observation closure and eligible non-`unsupported`, non-`context_only`
  evidence for every source-grounded thesis, signal, and project implication;
- per-reference confidence ceilings and cautious wording for low evidence;
- exact preissued reaction reason, confirmed-feedback classification and reader
  summary, project permission, and Radar ref/decision/reason. Merely loading
  feedback is `unchanged`, reaction absence is unknown rather than negative,
  and IRX-5 cannot turn current Radar state into build permission;
- persisted weekly manifest, reaction snapshot/receipt, feedback cutoff/count,
  Radar binding, and referenced Radar bytes are reloaded with exact identity,
  containment, schema, status, and checksum verification. Caller-supplied Radar
  data is comparison material, not authority.

Missing, stale, partial, mismatched, or tampered authoritative input sets a
deterministic release policy that forbids the model call and emits the exact
partial fallback. Invalid JSON, provider error, receipt mismatch, or invalid
model output produces the same visibly partial envelope. A completed period
with no changed eligible candidate is not a failure: it uses the exact
host-issued low-confidence zero-change thesis, no signals, and an empty matrix.
An existing complete artifact is accepted only for the same validated package,
requested model, and input hash; incomplete or conflicting run paths are
immutable and require a new `run_id`.

IRX-5 leaves all renderer behavior unchanged. The optional post-V1 shadow call
is isolated so any shadow import, input, model, validation, or persistence
exception leaves the already-created Brief and Atlas available and records only
the exception class in the split summary. Shadow comparison, V2 consumption,
reader rollout, and dogfood evidence remain future work.

## Weekly Intelligence Brief V2

### Purpose And Budget

The Brief is a five-to-seven-minute operational read about one completed week.
Its initial reader content targets `700-900` visible words. More than `900`
requires a quality warning; more than `1,100` before technical disclosures is a
critical failure unless the run is an explicitly labeled diagnostic.

Hard content limits:

| Content | Limit |
|---|---:|
| Main signals | 3 |
| Primary actions | 1 |
| Secondary actions | 2 |
| Concrete project actions | 2 |
| Radar decisions | 1 |
| Reaction effect receipts | 1 summary plus per-signal reason |
| Initially expanded technical/evidence blocks | 0 |

The Brief must stand on its own. Opening the Atlas cannot be required to
understand the weekly thesis or action.

### Information Architecture

#### 1. Header

Show, in this order:

- human-readable analysis dates;
- a separate generation timestamp;
- complete or partial run status;
- link to Knowledge Atlas V2;
- `Технические детали` disclosure containing the manifest and Audit Explorer
  links.

A partial run uses a prominent factual banner and names unavailable stages. It
must not look like a complete report with ordinary empty states.

#### 2. Main Weekly Thesis

Show one headline, a two-to-four-sentence plain-language explanation, personal
relevance, confidence, and a bounded evidence summary.

Russian example:

> **Главный вывод: качество агентной разработки теперь ограничивает не модель,
> а проверяемость процесса.** Инструменты ускорились, но надежный результат все
> чаще зависит от тестов, наблюдаемости и четких границ задачи. Для ваших
> проектов это повод улучшить один проверочный контур, а не менять стек.

If evidence cannot support a thesis, show a partial/low-evidence release instead
of manufacturing one.

#### 3. Decision Matrix

Show four bounded areas:

- `ДЕЙСТВОВАТЬ`;
- `ИЗУЧИТЬ`;
- `НАБЛЮДАТЬ`;
- `ОТЛОЖИТЬ / НЕ ДЕЛАТЬ`.

Each item is a concise decision, not a copy of a signal card. At least one
explicit defer or do-not-do decision is required.

#### 4. Signal Cards

Show no more than three. Each card contains:

- what happened;
- a simple explanation;
- what changed during the completed period;
- why it matters to this operator;
- evidence maturity, confidence, and independent source count;
- whether reactions or confirmed feedback influenced selection;
- a concrete project connection or `Подтвержденного влияния на проекты нет`;
- one next action where appropriate;
- what not to do;
- collapsed sources and limitations.

The same action sentence must not be repeated across matrix, signal, and project
sections. A reference such as `Основное действие недели` replaces duplication.

#### 5. Reaction Funnel

Show the trace from observed interest to selection:

```text
18 реакций -> 15 постов найдено -> 11 атомов -> 6 тем -> 3 сигнала в брифе
```

The funnel also states the snapshot status. Per-card copy may say:

> Почему сигнал попал в бриф: вы отметили два связанных поста за этот период.

Unconsumed reasons are summarized, with detailed counts collapsed. No reaction
means unknown, never negative interest.

The same compact personalization block includes confirmed-feedback effects:
how many confirmed events were considered, what changed ranking/editorial
context, what remained unchanged, and what requires separate code/config work.
It must not repeat raw feedback text or imply that a confirmed event was applied
when only loaded. Russian example:

> **Что изменилось по вашей обратной связи:** приоритет одной темы повышен;
> исправление доверия к источнику учтено. Запрос на новый формат требует
> отдельной задачи и в этом выпуске не применен.

No confirmed feedback remains unknown and produces no penalty.

#### 6. Project Impact

Use a compact table or responsive row set with columns:

- `Проект`;
- `Сигнал`;
- `Предлагаемое изменение`;
- `Трудозатраты`;
- `Уверенность`;
- `Доказательства`.

Every action names the project, affected component, likely files, acceptance
criteria, risk, confidence, and evidence refs in its sidecar record. Zero
confirmed implications is valid and is rendered honestly. Weak keyword overlap
is shown only as a watch or rejected overlap, never as an action.

#### 7. MVP Radar Gate

Show the candidate, dossier status, reader decision, why not to build, matched
candidate-specific evidence, unmatched context, missing evidence, what would
change the decision, next validation, and kill criteria.

`context_only` and market-lens records are labeled as context, not proof. The
Radar record must match the Brief run and period. Expected missing, invalid, or
wrong-run Radar makes the package partial. Intentionally disabled Radar says:

> MVP Radar отключен для этого запуска. Решение по сборке не сформировано.

No renderer or editorial model may translate `investigate` into build approval.
The renderer consumes `mvp_radar_reader.v1`, not an embedded candidate or
filename-adjacent legacy JSON. `available`/`no_candidate` require the current
manifest; all unbound values are diagnostic-only.

#### 8. Feedback Prompt

Ask separately and briefly:

- `Что было полезно?`
- `Какой приоритет выбран неверно?`
- `Где объяснение слишком поверхностное?`
- `Какое действие вы выполнили?`
- `Что изменить в следующем выпуске?`

Feedback controls target the Brief, a signal, Radar, a project action, reaction
personalization, or a visualization. Internal target IDs remain in form values
or sidecars, not visible labels.

### Brief Sidecar Contract

The renderer consumes validated `editorial_intelligence.v1` and deterministic
projections. A minimal reader sidecar shape is:

```json
{
  "schema_version": "split_ai_report.v2",
  "surface": "weekly_brief",
  "run_id": "tra-weekly-2026-W28-20260713T070252Z",
  "reporting_period": {
    "reporting_week": "2026-W28",
    "analysis_period_start": "2026-07-06T00:00:00Z",
    "analysis_period_end": "2026-07-13T00:00:00Z"
  },
  "run_status": "complete",
  "weekly_thesis": {},
  "decision_matrix": {},
  "signals": [],
  "reaction_effect": {},
  "feedback_effect": {},
  "project_actions": [],
  "mvp_radar": {},
  "feedback_targets": [],
  "visual_specs": [],
  "technical_refs": {
    "manifest_path": "...",
    "audit_explorer_path": "..."
  }
}
```

The sidecar may contain stable machine IDs for retrieval and audit. The HTML
must not expose them as reader copy.

## Knowledge Atlas V2

### Purpose And Budget

Atlas V2 is the cumulative visual map of long-term knowledge. It shows canonical
ideas and their lifecycle, not a mirror of every atom or Telegram post.

The initial page has at most `1,500` visible words before disclosures. It shows
`8-12` primary canonical threads. Additional threads require search/filter or a
collapsed secondary registry. No full evidence pane is expanded by default.

### First Screen

Without deep scrolling, the operator sees:

- the canonical knowledge graph;
- the strongest growing threads;
- weakening or stale threads;
- operator-interest highlights;
- an evidence-maturity overview;
- current learning progression;
- a bounded study backlog indicator.

The first screen answers `Что растет?`, `Что слабеет?`, `Чему я уделял
внимание?`, and `Где доказательств недостаточно?`.

### Information Architecture

#### 1. Canonical Knowledge Graph

- Nodes are canonical Idea Threads, labeled with thesis-level Russian titles.
- Edges represent a typed, evidence-backed relation, not simple shared-vendor
  occurrence.
- Node size encodes evidence volume or maturity; the legend states which.
- Border or shape encodes evidence quality.
- Interest highlighting shows reaction/operator attention.
- Status distinguishes growing, watch, stale, and contradicted threads.
- The graph initially contains no more than 12 primary nodes.

Graph navigation may reveal a thread summary, but raw memberships remain in the
Audit Explorer.

#### 2. Twelve-Week Thread Timeline

Use small multiples or sparklines for momentum and evidence count across 12
explicitly labeled weeks. Missing observations and zero evidence are distinct.
Merge/split events are annotated without rewriting history.

#### 3. Source By Thread Heatmap

Show source contribution to canonical threads. Encode independent support
separately from repeated commentary. Cell details give source count and period;
they do not display every post by default.

#### 4. Evidence Maturity Distribution

Show the six shared maturity levels and the count of primary threads at each
level. A mature/production label is forbidden when deterministic thresholds do
not support it.

#### 5. Operator Interest And Learning Progression

Interest shows weak reaction-based attention separately from explicit confirmed
feedback. Learning progression uses:

- `Отмечено`;
- `Прочитано`;
- `Понято`;
- `Объяснено`;
- `Испробовано`;
- `Внедрено`;
- `Измерено`.

Unknown stages remain unknown. The funnel must not infer understanding from a
reaction alone.

#### 6. Study Backlog

The backlog is curated, bounded, grouped by priority, and includes a reason for
each item. It must not contain ten near-identical claims from one fragmented
vendor cluster.

#### 7. Canonical Thread Registry

Show the primary thread title, thesis, lifecycle status, last meaningful change,
evidence maturity, and operator interest. Claims, sources, aliases, and history
are collapsed. Merge/split history remains accessible and auditable.

### Atlas Sidecar Contract

```json
{
  "schema_version": "split_ai_report.v2",
  "surface": "knowledge_atlas",
  "run_id": "tra-weekly-2026-W28-20260713T070252Z",
  "as_of": "2026-07-13T00:00:00Z",
  "primary_thread_ids": [],
  "canonical_threads": [],
  "thread_relations": [],
  "timeline": {},
  "source_thread_matrix": {},
  "evidence_maturity": {},
  "operator_interest": {},
  "learning_progression": {},
  "study_backlog": [],
  "visual_specs": [],
  "technical_refs": {
    "manifest_path": "...",
    "audit_explorer_path": "..."
  }
}
```

Thread records use stable `canonical_thread_id` and `stable_slug` in JSON while
displaying `title_ru` and `thesis` in the reader surface. Merge/split provenance
must not be lost when the primary set changes.

## Knowledge Audit Explorer

The current detailed Knowledge Atlas renderer and its thread-navigation sidecar
are the migration foundation for Knowledge Audit Explorer. They are preserved,
versioned, and relabeled; they are not deleted or passed off as Atlas V2.

Audit Explorer owns:

- full Knowledge Atom records and internal IDs;
- source quotes and links;
- raw and canonical memberships;
- entity aliases;
- merge/split curator history;
- ranking factors and fallback diagnostics;
- confidence inputs and evidence provenance;
- full thread/source tables;
- ingestion and lookup diagnostics.

Its navigation is reachable from `Технические детали`, not positioned as the
primary reading path. It should state that it is an audit surface and may be
long. Search and filters are appropriate here; automatically expanded evidence
is not appropriate in the reader Atlas.

## Progressive Disclosure Rules

| Information | Brief V2 | Atlas V2 | Audit Explorer |
|---|---|---|---|
| Thesis/decision | visible | summary only | traceable input |
| Confidence reason | visible, concise | visible, aggregate | full factors |
| Source count | visible | visual/aggregate | full source rows |
| Source titles/links | collapsed | collapsed | visible/filterable |
| Full quote | excluded or collapsed short excerpt | excluded | available |
| Atom/thread IDs | hidden | hidden | visible |
| Ranking/fallback trace | hidden | hidden | visible |
| Raw enums | translated | translated | visible with glossary |
| Merge/split history | concise annotation | collapsed | full history |
| Unconsumed reaction reasons | collapsed summary | aggregate | full receipt |

`<details>` elements start closed. A disclosure summary names its contents;
generic labels such as `More` are not acceptable. Core decisions, partial-run
warnings, and evidence limitations may not be hidden.

## Required Visual Components

Brief V2 uses at least three meaningful data-bearing components when its data
permits, including:

- decision matrix;
- reaction funnel;
- project impact table;
- Radar gate progress.

Atlas V2 uses, when data permits:

- canonical knowledge graph;
- 12-week thread timeline;
- source-thread heatmap;
- evidence-maturity distribution;
- learning-progression funnel.

All components follow `docs/static_visualization_system.md`. Decorative shapes,
badges, or empty containers do not count toward the visual quality gate.

## Duplicate Content Rules

- A claim has one primary reader location per surface.
- Decision Matrix labels summarize or link to Signal Cards; they do not repeat
  the full copy.
- Project Impact references a signal and adds project-specific information; it
  does not copy the generic next action.
- Atlas summaries may link to a canonical thread but must not reproduce its full
  evidence list in timeline, heatmap, backlog, and registry.
- Exact repeated action sentences are a critical quality finding.
- Renderer templates must not create prose fallbacks that appear to be an
  editorial recommendation.

## Compatibility And Migration

- Existing V1 commands and generated artifacts remain inspectable during
  rollout.
- The current detailed Atlas behavior becomes a versioned Audit Explorer;
  existing `knowledge_atlas_thread_navigation.v1` and `atlas_thread` retrieval
  remain supported or receive an explicit adapter.
- V2 sidecars are additive. Hermes/PI retrieval must read V1 and V2 during the
  migration; no silent schema replacement is allowed.
- Obsidian projection continues to receive stable evidence/thread references or
  uses a tested compatibility projection.
- V2 output directories, aliases, and retention are finalized under IRX-14.
  Until then, implementation must not overwrite V1 artifacts.
- `editorial_intelligence.v1`, `split_ai_report.v2`, and
  `weekly_run_manifest.v1` versions are recorded independently so schema and
  renderer drift is detectable.

## Acceptance Criteria

### Weekly Brief V2

- A Russian reader can identify the completed period, weekly thesis, one action,
  one defer decision, Radar status, and reaction effect without opening Atlas.
- There are at most three main signals and no more than two project actions.
- Every claim and project action has resolvable evidence refs.
- The actual same-run Radar result is present or the package is visibly partial.
- Reactions are shown as a weak influence receipt; absence is not negative.
- At least three meaningful visual components render for a normal fixture.
- No internal IDs, raw enums, fallback diagnostics, or ranking dumps are visible.
- Desktop and 375px mobile review shows no overlap, truncation, or hidden core
  decisions.

### Knowledge Atlas V2

- The first screen communicates growth, staleness, maturity, and interest.
- The initial registry contains 8-12 canonical idea-level threads, without
  Fable/Claude-style entity fragmentation dominating it.
- Graph, timeline, heatmap, and evidence-maturity views render when data permits.
- Initial visible copy is no more than 1,500 words and full evidence starts
  collapsed.
- Raw memberships and atoms remain available through Audit Explorer.
- Canonical merge/split provenance and stable references survive rendering.

### Audit Explorer

- Current audit capability is preserved or migrated with a compatibility path.
- The surface is clearly labeled technical and is not the default Atlas link.
- Retrieval and Obsidian compatibility have focused tests before V2 becomes the
  default.

## Failure States

- Invalid editorial JSON: do not render it as complete; use an explicitly
  partial deterministic fallback or fail the reader stage.
- Missing evidence ref: reject the affected claim and record a quality failure.
- Missing/wrong-run Radar: partial package with no invented candidate.
- Reaction snapshot failure: partial receipt stating reactions were not
  refreshed; do not report zero interest.
- No project implication: render `Подтвержденного влияния на проекты нет`.
- Empty completed week: render a valid low-evidence/zero-change report with an
  honest thesis limitation, not generic actions.
- Missing historical points: show gaps; do not convert them to zeros.
- Visualization cannot render: preserve the accessible text/table alternative,
  mark visual quality failed, and keep the run partial where the component is
  required.

## Stop Rules

Stop and ask the operator before a proposal or implementation would:

- weaken evidence or Radar gates;
- treat reaction absence as negative;
- turn reactions into permanent preferences automatically;
- let an LLM produce uncited claims or HTML;
- count Radar context-only records as build-ready evidence;
- infer project actions from broad keyword overlap;
- delete or hide the current audit capability;
- break Hermes/PI or Obsidian compatibility without a migration plan;
- add vector/raw Telegram RAG or new source skills;
- start dogfood before the P0 correctness failures are resolved;
- add visual decoration without information value.

## Verification Contract

Implementation tasks must add focused assertions for:

- completed-week and same-run identity;
- Russian reader labels and visible-content limits;
- evidence refs and confidence/maturity separation;
- reaction receipt counts and unconsumed reasons;
- concrete/weak/rejected/empty project implications;
- Radar success, failure, disabled, and wrong-run states;
- internal-ID and raw-enum exclusion;
- duplicate visible sentences;
- required meaningful visual markers;
- collapsed technical detail;
- V1 retrieval and Obsidian compatibility;
- 1440px and 375px visual regression.

The current W29 artifacts are expected to fail these reader-value checks. That
is an audit result, not permission to edit or commit generated reports.
