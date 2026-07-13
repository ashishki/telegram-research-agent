# Static Visualization System Contract

Version: `report_visuals.v1`  
Status: planned under IRX-8; not implemented  
Consumers: Weekly Intelligence Brief V2 and Knowledge Atlas V2

This contract defines reusable, deterministic, offline visualization components
for Report V2. Components explain, compare, and navigate validated data. They do
not create evidence, increase confidence, or substitute decoration for reader
value.

## Technology Boundary

Required implementation properties:

- server-side Python rendering;
- semantic HTML and CSS;
- inline SVG for charts and graphs;
- deterministic output for identical structured input;
- standalone offline HTML with no required network access;
- optional small embedded JavaScript only for progressive disclosure, filtering,
  or accessible focus behavior that cannot be achieved with HTML/CSS;
- no React, frontend build pipeline, web server, canvas-only chart, external
  font, CDN, remote image, or analytics dependency;
- no LLM-generated SVG or HTML;
- no random decorative images, gradients, animated decoration, or visual count
  padding.

Archify may be reused for a bounded explanatory workflow diagram when its local
output is embedded into the standalone artifact and a deterministic fallback
exists. It is not the renderer for evidence graphs, timelines, heatmaps,
funnels, or gate state, and an explanatory architecture diagram does not count
as evidence or satisfy a missing data-visual requirement.

The likely implementation modules are `src/output/report_visuals.py` for data
visuals and `src/output/report_ui.py` for shared report structure. Exact module
names may follow repository conventions during IRX-8.

`Dream_Motif_Interpreter/docs/DREAM_MEMORY_MAP.md` and its static memory-map
prototype are visual references for evidence-linked edges, provisional versus
confirmed states, and SVG-plus-text fallback. They are not a dependency and
their domain model must not be copied into Report V2.

## Rendering Contract

Each component receives validated structured input and returns a result with:

```json
{
  "html": "<section ...>",
  "component_id": "reaction-effect",
  "component_type": "reaction_funnel",
  "schema_version": "report_visual.reaction_funnel.v1",
  "render_status": "complete",
  "data_status": "available",
  "source_ref_count": 1,
  "warnings": []
}
```

Allowed `render_status` values are `complete`, `partial`, and `failed`. Allowed
`data_status` values are `available`, `empty`, `unavailable`, and `stale`.

The root element exposes machine-detectable quality markers:

```html
<section
  data-irx-visual="true"
  data-component="reaction_funnel"
  data-component-id="reaction-effect"
  data-schema-version="report_visual.reaction_funnel.v1"
  data-render-status="complete"
  data-data-status="available"
  data-source-ref-count="1"
>
```

Quality gates count a component as meaningful only when:

1. its input schema validates;
2. `render_status=complete` or an accepted partial state is explained;
3. it contains non-empty domain data or a required honest empty state;
4. it has a visible title, legend or labels, and source/data note;
5. it has an accessible text or table equivalent;
6. its type is appropriate to a reader question.

Metric cards, decorative icons, empty SVGs, repeated variants of the same data,
and hidden components do not increase the meaningful-visual count.

## Shared Input Envelope

All component schemas extend this envelope:

```json
{
  "schema_version": "report_visual.<component>.v1",
  "component_id": "stable-local-id",
  "title_ru": "Русский заголовок",
  "summary_ru": "Что показывает визуализация",
  "run_id": "tra-weekly-2026-W28-20260713T070252Z",
  "reporting_week": "2026-W28",
  "analysis_period_start": "2026-07-06T00:00:00Z",
  "analysis_period_end": "2026-07-13T00:00:00Z",
  "data_status": "available",
  "source_refs": [],
  "data_note_ru": "Источник и ограничение данных",
  "items": []
}
```

Rules:

- `component_id` is stable within one artifact and unique in the DOM.
- Visible labels use Russian; stable internal values remain in the schema.
- Every count defines its unit and period.
- `null`, `0`, and missing are distinct.
- Source refs point to sidecar evidence or manifest artifacts; they are not
  silently converted into proof.
- User-authored/source text is escaped. Links are restricted to accepted local
  paths and safe `http`/`https` source URLs.

## Determinism Rules

- Input lists use an explicit sort key. Ties resolve with a stable ID, never
  process order.
- Do not use Python's randomized `hash()` for positions or colors.
- Numeric domains, bins, rounding, and missing-value handling are defined per
  component.
- SVG coordinates are generated from fixed algorithms and rounded consistently.
- A graph uses deterministic ordering/layering from stable canonical IDs. If
  layout cannot satisfy overlap limits, reduce to the primary node budget and
  record excluded-node count.
- No random seeds, current-time labels, or environment-specific absolute paths
  enter component HTML.
- Identical normalized input and renderer version produce byte-stable component
  output, apart from explicitly excluded artifact timestamps.

## Shared Visual Semantics

Use a restrained multi-hue semantic palette with sufficient contrast:

- act/confirmed: green;
- study/watch: blue or amber with distinct shape/label;
- defer/blocked: neutral gray;
- risk/contradicted/failed: red;
- operator interest: a separate accent that is not confused with evidence
  strength.

Color is never the only signal. Text, icon, line style, border, or pattern also
encodes state. Confidence and evidence maturity must not share an identical
encoding. All legends state what size, color, border, and line style mean.

No component uses gradient fills to imply precision. Bar lengths and areas start
from an honest baseline. Truncated axes require an explicit mark and note.

## Component Catalog

### 1. Decision Matrix

Schema: `report_visual.decision_matrix.v1`

```json
{
  "items": [
    {
      "decision": "act|study|watch|ignore",
      "label_ru": "Проверить контракт периода",
      "signal_ref": "signal-period-semantics",
      "confidence": "low|medium|high",
      "evidence_maturity": "single_source|repeated_signal|multi_channel|primary_verified|externally_corroborated|decision_grade"
    }
  ]
}
```

- **Question answered:** what should I act on, study, watch, or defer?
- **Normal state:** four semantic regions, maximum three concise items per
  region, with one primary action and one explicit defer decision highlighted.
- **Empty state:** retain all four labels and say `Решений для этой категории
  нет`; do not invent balance across quadrants.
- **Mobile:** one-column ordered regions; primary action remains first.
- **Accessibility:** semantic headings and lists precede or accompany the visual
  grid. Decision is never conveyed by color alone.

### 2. Reaction Funnel

Schema: `report_visual.reaction_funnel.v1`

```json
{
  "snapshot_status": "complete|partial|failed",
  "stages": [
    {"key": "detected", "label_ru": "Реакции", "count": 18},
    {"key": "posts_resolved", "label_ru": "Посты найдены", "count": 15},
    {"key": "atoms_linked", "label_ru": "Связаны с атомами", "count": 11},
    {"key": "threads_linked", "label_ru": "Связаны с темами", "count": 6},
    {"key": "signals_selected", "label_ru": "Повлияли на сигналы", "count": 3}
  ],
  "unconsumed_reasons": []
}
```

- **Question answered:** how did my marked posts affect this report?
- Personal reaction events must be greater than or equal to unique reacted
  posts, but later entity counts are not required to be monotonic because one
  post can map to several atoms or threads. Render this as a lineage flow with
  explicit units, not a percentage-conversion funnel or narrowing area chart.
- **Empty state:** `За период личные реакции не обнаружены. Это не означает
  отрицательный интерес.`
- **Unavailable state:** `Синхронизация реакций не завершена`; do not render
  zeros.
- **Mobile:** vertical stages with count and conversion loss; no tiny horizontal
  labels.
- **Accessibility:** ordered list alternative; losses and unconsumed reasons
  available as text.

### 3. MVP Radar Gate Progress

Schema: `report_visual.radar_gate.v1`

```json
{
  "candidate_name": "Hotkey Dictation Workflow Probe",
  "dossier_status": "investigate",
  "reader_decision": "investigate|reject|build_allowed|unavailable",
  "gates": [
    {"key": "kir_evidence", "status": "pass|missing|blocked|not_applicable", "reason_ru": "..."}
  ],
  "candidate_evidence_count": 0,
  "context_only_count": 4,
  "missing_evidence": [],
  "next_validation_ru": "...",
  "kill_criteria_ru": "..."
}
```

- **Question answered:** what does Radar allow or block, and why?
- Candidate evidence and context-only records are visually separated and
  labeled. Context never fills an evidence gate.
- **Empty state:** valid only when no candidate is selected by a successful
  same-run Radar. Missing/wrong-run Radar is `unavailable` and makes the report
  partial.
- **Mobile:** gates become a vertical checklist; decision and block reason remain
  above the fold.
- **Accessibility:** status text accompanies every icon; the full gate list is a
  semantic list.

### 4. Project Impact Table

Schema: `report_visual.project_impact.v1`

```json
{
  "items": [
    {
      "project_name": "telegram-research-agent",
      "signal_ref": "signal-reaction-effect",
      "suggested_change_ru": "Показать отчет о влиянии реакций",
      "affected_component": "Weekly Brief",
      "likely_files": ["src/output/weekly_intelligence_brief.py"],
      "effort": "1-2 hours",
      "confidence": "high",
      "acceptance_criteria": ["Бриф показывает, сколько реакций изменило отбор"],
      "risk_ru": "Не путать связь с фактическим изменением ранга",
      "evidence_refs": ["evidence:reaction-ranking-gap"],
      "status": "confirmed|watch|rejected_overlap|learning_only|existing_context"
    }
  ]
}
```

- **Question answered:** which active project could change, specifically?
- Normal Brief state shows at most two confirmed actions. Likely files and
  acceptance criteria appear in an adjacent disclosure or concise row detail.
- **Empty state:** `Подтвержденного влияния на активные проекты нет.`
- Watch/rejected/learning-only records cannot use action styling.
- **Mobile:** each semantic table row becomes a labeled definition list without
  losing headers or source links.
- **Accessibility:** use a real table at wider widths and retain programmatic
  header associations.

### 5. Canonical Knowledge Graph

Schema: `report_visual.knowledge_graph.v1`

```json
{
  "encoding": {
    "node_size": "evidence_volume",
    "node_border": "evidence_maturity",
    "node_accent": "operator_interest"
  },
  "nodes": [
    {
      "canonical_thread_id": "...",
      "title_ru": "...",
      "status": "growing|watch|stale|contradicted",
      "evidence_volume": 8,
      "evidence_maturity": "multi_channel",
      "operator_interest_score": 0.25
    }
  ],
  "edges": [
    {
      "source_thread_id": "...",
      "target_thread_id": "...",
      "relation": "supports|depends_on|contradicts|converges_with",
      "weight": 2,
      "evidence_refs": []
    }
  ]
}
```

- **Question answered:** how do the primary ideas relate, mature, and attract
  operator interest?
- Maximum 12 primary nodes initially. An edge requires a typed relationship and
  evidence refs; shared vendor tokens are insufficient.
- Stable node ordering and layout are mandatory. Labels must not overlap.
- **Empty state:** explain that no canonical threads passed the current display
  threshold and link to Audit Explorer; do not fall back to entity clusters.
- **Mobile:** use a readable vertically layered SVG or horizontally scrollable
  fixed-minimum canvas with an adjacent thread list. Core labels cannot require
  hover.
- **Accessibility:** SVG `role="img"`, title/description, focusable node links,
  and a complete semantic relation list or table alternative.

### 6. Thread Timeline And Sparklines

Schema: `report_visual.thread_timeline.v1`

```json
{
  "weeks": ["2026-W17", "2026-W18", "...", "2026-W28"],
  "series": [
    {
      "canonical_thread_id": "...",
      "title_ru": "...",
      "momentum": [0.0, null, 0.2],
      "evidence_count": [0, null, 3],
      "events": [{"week": "2026-W24", "type": "merge", "label_ru": "..."}]
    }
  ]
}
```

- **Question answered:** which threads are growing, weakening, or stale over 12
  weeks?
- Weeks are explicit and ordered. `null` renders as a gap; zero renders on the
  baseline.
- Use a shared scale when comparing series, or label independent scales clearly.
- **Empty state:** state that fewer than the required historical snapshots exist
  and show the available range.
- **Mobile:** stack small multiples; show first/last/current values as text.
- **Accessibility:** each sparkline has a concise trend sentence and an
  accessible data table.

### 7. Source By Thread Heatmap

Schema: `report_visual.source_thread_heatmap.v1`

```json
{
  "value": "independent_support_count",
  "sources": [{"source_id": "...", "label": "...", "independence_group": "..."}],
  "threads": [{"canonical_thread_id": "...", "title_ru": "..."}],
  "cells": [
    {
      "source_id": "...",
      "canonical_thread_id": "...",
      "mention_count": 4,
      "independent_support_count": 1,
      "evidence_refs": []
    }
  ]
}
```

- **Question answered:** which sources support which ideas, and is support
  independent or repeated commentary?
- Color intensity follows the declared `value`; a text/tooltip discloses both
  mention and independent counts.
- **Empty state:** distinguish no contribution from unavailable source
  classification.
- **Mobile:** scrollable matrix with sticky or repeated labels, plus a ranked
  text summary. Do not shrink labels below readable size.
- **Accessibility:** semantic table equivalent with explicit row/column headers.

### 8. Evidence Maturity Distribution

Schema: `report_visual.evidence_maturity.v1`

```json
{
  "levels": [
    {"key": "single_source", "label_ru": "Один Telegram-источник", "count": 4},
    {"key": "repeated_signal", "label_ru": "Повторяющийся сигнал", "count": 3}
  ],
  "thread_count": 12
}
```

- **Question answered:** how much of the knowledge map is mature enough for a
  decision?
- Level order is fixed and counts must sum to the declared population, with an
  explicit unknown bucket when necessary.
- **Empty state:** no qualifying canonical threads; do not imply zero maturity
  for unavailable data.
- **Mobile:** horizontal bars become full-width labeled rows.
- **Accessibility:** counts and percentages are present as text.

### 9. Learning Progression Funnel

Schema: `report_visual.learning_progression.v1`

```json
{
  "stages": [
    {"key": "marked", "label_ru": "Отмечено", "count": 18},
    {"key": "read", "label_ru": "Прочитано", "count": 9},
    {"key": "understood", "label_ru": "Понято", "count": 4},
    {"key": "explained", "label_ru": "Объяснено", "count": 2},
    {"key": "tried", "label_ru": "Испробовано", "count": 1},
    {"key": "implemented", "label_ru": "Внедрено", "count": 1},
    {"key": "measured", "label_ru": "Измерено", "count": 0}
  ]
}
```

- **Question answered:** how is attention becoming applied learning?
- Later stages require their own observed/confirmed event. A reaction alone may
  populate `marked`, not `read` or `understood`.
- **Empty state:** `Прогресс обучения еще не подтвержден`; no-feedback remains
  unknown.
- **Mobile:** vertical progression with explicit counts.
- **Accessibility:** ordered stage list and transition explanations.

### 10. Confidence And Evidence Badges

Schema: `report_visual.evidence_badge.v1`

```json
{
  "confidence": "medium",
  "confidence_reason_ru": "...",
  "evidence_maturity": "multi_channel",
  "source_count": 3,
  "independent_source_count": 2
}
```

- **Question answered:** how certain is this conclusion, and how mature is its
  evidence?
- Confidence and maturity render as two labeled values, not one ambiguous score.
- This is a supporting semantic component and does not count as a standalone
  meaningful visualization for the three-component Brief gate.
- **Accessibility:** full labels remain visible; abbreviations and color-only
  dots are forbidden.

## Responsive Layout Contract

Reference widths are `1440px` desktop and `375px` mobile.

- Use stable `minmax()` grid tracks, explicit SVG `viewBox`, bounded aspect
  ratios, and minimum touch targets.
- Text wraps naturally; do not scale font size with viewport width.
- Tables either preserve semantic table behavior with controlled horizontal
  scrolling or transform to labeled rows without losing headers.
- Tooltips cannot contain essential information because they do not work
  reliably on touch. Essential values are visible or focus-accessible.
- Graphs and heatmaps may scroll within a labeled region, but the page itself
  must not gain unintended horizontal overflow.
- Dynamic labels, empty states, and status badges must not resize the surrounding
  layout enough to cause content shifts or overlap.

## Accessibility Contract

- One `h2`/`h3` heading names every component in document order.
- SVG uses `role="img"`, `<title>`, `<desc>`, and `aria-labelledby`.
- A text list or table contains the same decision-relevant data as each SVG.
- Contrast meets WCAG AA for normal text and meaningful graphical objects.
- Color, line width, shape, label, or pattern provide redundant encodings.
- Focus order follows reading order; focus indicators remain visible.
- Links and controls have specific Russian accessible names.
- Print/PDF output retains labels, legends, and source notes.
- Reduced-motion settings are respected; motion is not required to understand a
  component.

## Empty, Partial, And Error States

Every component implements all four `data_status` states:

| State | Required behavior |
|---|---|
| `available` | render validated data and source note |
| `empty` | explain that the successful query found no qualifying records |
| `unavailable` | name the failed/missing upstream stage; do not render zeros |
| `stale` | show source period and warning; do not present as current-run data |

Schema validation failure returns `render_status=failed`, records an actionable
warning, and lets the surface apply its partial/failure contract. It must not
emit an empty SVG or silently remove a required visualization.

Russian examples:

- Empty: `За завершенный период подтвержденных проектных изменений нет.`
- Unavailable: `Данные MVP Radar недоступны для этого запуска.`
- Stale: `Показаны данные предыдущего запуска; они не участвуют в решении.`
- Partial: `Связь реакций с темами рассчитана не полностью: 4 поста не найдены.`

## Evidence And Source Notes

Every component has a visible, concise note answering:

1. what period/population it summarizes;
2. what value or status is encoded;
3. which upstream artifact supplied the data;
4. what limitation matters to interpretation.

Example:

> Данные: 12 канонических тем за W17-W28. Интенсивность показывает число
> независимых источников, а не количество повторных упоминаний.

The note can link to a collapsed source summary. Full provenance belongs in the
Audit Explorer.

## Security And Standalone Output

- Escape all text before HTML/SVG interpolation, including titles and source
  snippets.
- Validate URLs and local artifact paths; prohibit script URLs and inline event
  handlers from data.
- Use a restrictive Content Security Policy compatible with inline styles and
  explicitly hashed/nonce-free bundled script if optional JavaScript exists.
- Embed required CSS and icons in the document; do not fetch remote assets.
- Do not place private raw evidence in SVG metadata, DOM attributes, or hidden
  accessibility alternatives.
- The report remains understandable with JavaScript disabled.

## Quality-Gate Integration

The report-quality layer evaluates components by category:

- `visual.structure`: valid markers, schema, and render state;
- `visual.information_value`: answers a declared reader question with real data;
- `visual.accessibility`: labels, alternative, contrast, and focus behavior;
- `visual.responsive`: desktop/mobile overflow and overlap;
- `visual.provenance`: period, data note, and source refs;
- `visual.integrity`: honest axes, missing values, context/evidence distinction;
- `visual.duplication`: component does not repeat another component's data without
  a distinct reader question.

A report cannot pass by adding three decorative SVGs. For a normal Brief fixture,
three distinct data-bearing component types must pass. For Atlas, the graph,
timeline, heatmap, and maturity distribution are required when their validated
input is available.

## Test Contract

Each component has focused fixtures for:

- normal data;
- empty data;
- unavailable upstream data;
- partial data;
- stale data where applicable;
- long Russian labels and product/code names;
- missing values versus zero;
- deterministic tie ordering;
- unsafe input escaping;
- accessible text/table parity;
- desktop `1440px` and mobile `375px` screenshots.

System-level checks include:

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache \
  python3 -m unittest tests.test_report_visuals

rg 'data-irx-visual|data-component|data-render-status|data-data-status' \
  tests/fixtures/report_v2
```

Exact test module and sanitized fixture paths are finalized during IRX-8 and
IRX-13. Offline browser tests must deny network requests and verify no page-level
horizontal overflow, label overlap, blank SVG, or missing accessible alternative.

## Acceptance Criteria

- Brief and Atlas reuse the same component renderers and semantics.
- Output is deterministic, offline, standalone, and Russian reader-facing.
- Every component has structured input, validation, data/source note, accessible
  alternative, empty/unavailable/partial handling, and 1440px/375px behavior.
- Knowledge graph labels do not overlap and expose no raw IDs as reader copy.
- Timeline distinguishes missing values from zero.
- Heatmap distinguishes mentions from independent evidence.
- Radar keeps context-only information outside proof/gate progress.
- Reaction and learning funnels do not infer negative interest or understanding.
- Meaningful-component markers let reader-value gates reject the current W29
  no-visual reports and reject decorative substitutes.
- No network request or frontend runtime is required to read or print a report.

## Stop Rules

Stop and ask the operator before a visualization implementation would:

- use decoration to satisfy a quality count;
- imply that a chart proves a claim;
- hide weak evidence behind high-confidence styling;
- turn Radar context into candidate evidence;
- infer negative preference from no reaction;
- infer learning stages without confirmed events;
- expose private raw evidence or internal IDs in reader HTML;
- use LLM-generated HTML/SVG;
- add React, a web server, a remote dependency, or required network access;
- remove the text/audit alternative;
- make V1 retrieval or Obsidian projection incompatible without a migration
  plan.
