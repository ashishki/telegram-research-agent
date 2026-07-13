# Intelligence Report V2: W29 Audit

Status: completed documentation audit  
Audit date: 2026-07-13  
Scope: generated W29 split reports, their JSON sidecars, relevant source and
tests, the local SQLite state, and the same-period Radar output in
`Demand-to-MVP-Radar`

This audit is the evidence base for the `IRX` product-correction queue. It does
not claim that Report V2 is implemented.

## Executive Finding

The backend contains substantial useful intelligence infrastructure, but the W29
split reports fail as reader-facing information products. The Weekly Brief is a
structurally valid status dump with generic actions. The Knowledge Atlas is a
bounded but fully expanded audit explorer. Neither surface reliably answers what
changed, why it matters, what the operator should do, what prior feedback
changed, or how the Radar decision relates to the same weekly run.

The primary failure is not CSS. Five contracts are missing or incomplete:

1. completed-week period identity;
2. one manifest-owned run and Radar handoff;
3. reaction-to-selection provenance;
4. canonical idea-level thread curation;
5. a bounded editorial synthesis layer between deterministic selection and
   deterministic rendering.

## Artifacts Inspected

- `data/output/knowledge_atlas/2026-W29.knowledge-atlas.html`
- `data/output/knowledge_atlas/2026-W29.knowledge-atlas.json`
- `data/output/weekly_intelligence_briefs/2026-W29.weekly-brief.html`
- `data/output/weekly_intelligence_briefs/2026-W29.weekly-brief.json`
- the corresponding W28 split artifacts for comparison;
- `data/agent.db`;
- `/srv/openclaw-you/workspace/Demand-to-MVP-Radar/reports/mvp_of_week/mvp-weekly-2026-W28.json`;
- the report, knowledge, reaction, feedback, project, quality, retrieval,
  Obsidian, and Radar pipeline source and focused tests listed in
  `docs/intelligence_report_v2_roadmap.md`.

The generated artifacts were read only. They were not regenerated, edited, or
added to git.

## Audit Method

Programmatic HTML inspection parsed each document with `html5lib`, limited the
measurement to `<body>`, and collapsed descendant text whitespace. Visible word
tokens use Unicode-aware letter/number boundaries. A repeated sentence means a
normalized sentence of at least eight word tokens found in reader-bearing
elements (`p`, headings, cells, summaries, and non-container list items). The
metric reports distinct repeats, total occurrences, and occurrences after the
first. Exact fallback strings and visible internal-token patterns were counted
separately.

Language mix is the share of Cyrillic versus Latin word tokens in visible text.
It is a diagnostic, not a language-quality score: product and model names can
legitimately remain Latin. Near-duplicate titles use a review heuristic, not an
automatic merge rule: title-token overlap coefficient of at least `0.67` with
at least two shared tokens, plus exact containment for a one-token smaller title.

Manual inspection read the rendered document order, section copy, expanded
content, source presentation, action specificity, and sidecar-to-HTML parity.
No browser engine was installed in the workspace, so this audit does not claim
pixel-level or responsive screenshot review.

## Content Metrics

| Metric | Knowledge Atlas W29 | Weekly Brief W29 |
|---|---:|---:|
| File size | 66,915 bytes | 16,337 bytes |
| Visible words | 5,376 | 1,216 |
| Total headings | 145 | 35 |
| Repeated-sentence occurrences after first | 107 | 14 |
| Total repeated-sentence occurrences | 149 | 19 |
| Distinct repeated sentences | 42 | 5 |
| Tables | 3 | 1 |
| SVG elements | 0 | 0 |
| Canvas elements | 0 | 0 |
| Images | 0 | 0 |
| Semantic diagrams/figures | 0 | 0 |
| Fully visible thread-detail blocks | 8 | 0 |
| Fully visible evidence-item blocks | 24 | 0 |
| Collapsed `<details>` blocks | 0 | 0 |
| Visible `Atom <id>` references | 49 | 0 |
| Visible action/read target IDs | 0 | 5 |
| Visible audit/thread slugs | 24 | 0 |
| Total visible internal/debug ID occurrences | 73 | 5 |
| Exact generic action sentence occurrences | 0 | 9 |
| Visible fallback-diagnostic occurrences | 0 | 4 |
| Concrete configured project names | 0 | 0 |
| Completed-period Radar data available / bound | yes in sibling repo / no | yes in sibling repo / no |
| Visible reaction-effect receipt | no | no |
| Latin/Cyrillic share of language tokens | 92.7% / 7.3% | 100% / 0% |
| Near-duplicate Idea Thread title pairs | 8 pairs among the 12 visible titles | 1 pair among four unique action-thread titles |

The Brief's exact action sentence appears nine times because four action records
are reused in the decision matrix, Project Impact, and action cards. The exact
string count is the authoritative fallback metric; the sentence metric captures
broader repeated copy.

The Atlas sidecar contains 24 threads and 55 unique source atoms. Across all 24
sidecar titles, 11 titles participate in 19 heuristic near-duplicate pairs. The
rendered thread index lists 12 threads, while eight full thread details and 24
evidence items are expanded into the initial document. The absence of
`<details>` means none of that evidence is progressively disclosed. The four
index entries beyond the eight rendered details point to missing fragment
targets even though the sidecar calls all 12 cards navigable.

## Concrete Reader-Facing Failures

### Weekly Brief

- The first decision metric is `0 changed threads`.
- `What Changed This Week` says no current-week movement is visible.
- Four action cards repeat the same instruction: choose a claim, verify it, and
  turn it into a 30-minute note.
- The same generic instructions are copied into `Project Impact`; no repository,
  component, likely file, effort, or acceptance criterion is named.
- The Brief exposes `do_not_build`, `needs_more_evidence`, `context_only`,
  `prerequisite_gap`, and five machine feedback target IDs.
- `Why selected` tells the reader that items were fallbacks. That is useful audit
  data but not useful editorial copy.
- The Radar section says `No candidate selected` and that the JSON artifact was
  unavailable.
- The report has no weekly thesis, no clear one-action commitment, no reaction
  funnel, no project-impact matrix, and no visual Radar gate.
- Reader-facing navigation, headings, narrative, actions, feedback prompts, and
  status copy are English.

### Knowledge Atlas

- The initial document is 5,376 visible words with 145 headings.
- The thread registry is dominated by entity combinations rather than stable
  ideas.
- Timeline, Claims, Study Next, Evidence Pane, Study Backlog, and the audit table
  repeat the same claims and identifiers.
- Every rendered thread detail is open by default.
- `Atom 1282`, `production_pattern`, `project_watch`, atom types, confidence
  values, slugs, and raw source membership are reader-visible.
- `Idea Map` is a card grid, `Trend Board` is a list of bars/cards, and source
  contribution is tabular. There is no knowledge graph, 12-week comparative
  timeline, source-thread heatmap, or evidence-maturity distribution.
- English reader copy surrounds some Russian source quotations. The Russian
  text is evidence, not Russian editorial explanation.
- Zero values can render as blank because the shared escaping helper treats
  numeric zero as false; the W29 `Changed` metric is visibly empty. The two
  reports also contain eight blank table cells despite available zero states.

The content is valuable for provenance inspection. That makes it a strong
starting point for a Knowledge Audit Explorer, not the reader-facing Atlas V2.

## Period Bug Analysis

The artifacts were generated at `2026-07-13T07:02:52Z`, on the first morning of
ISO week W29, and were labeled `2026-W29`. The current default resolves
`datetime.isocalendar()` and passes the current week directly through context,
Frontier Analysis, split rendering, reaction selection, and Radar path lookup.
The Monday systemd report command supplies no explicit week.

Local data demonstrates the impact:

| Half-open UTC period | Posts | Knowledge Atoms last seen |
|---|---:|---:|
| `2026-07-06T00:00:00Z` to `2026-07-13T00:00:00Z` (W28) | 216 | 35 |
| `2026-07-13T00:00:00Z` to `2026-07-20T00:00:00Z` (W29, at audit) | 3 | 0 |

The changed-thread calculation is internally consistent with the wrong W29
window. The product bug is selecting that window for a Monday weekly report.

There is a second historical correctness risk: thread selection uses a thread's
current `last_seen_at`, and atom loading has no `analysis_period_end` cutoff.
Regenerating an old week can therefore include future state unless IRX-1 makes
the upper boundary explicit throughout the query path.

## Reaction And Feedback Pipeline Analysis

Reaction ingestion already has the correct base semantics:

- any visible personal Telegram reaction becomes `interesting` plus
  `operator_marked_interesting`;
- raw emoji is metadata;
- aggregate channel reactions are ignored as personal feedback;
- no reaction is not converted into a negative signal.

The reader-value path is incomplete:

1. marked posts are queried separately by feedback `recorded_at`;
2. the result is attached to `context["marked_posts"]`;
3. deterministic ranking scores only confirmed AI report feedback;
4. no helper maps reacted post to atom to thread to selected item;
5. neither split report exposes consumed/unconsumed counts or reasons.

The local database snapshot contains zero `reaction_sync_state`,
`signal_feedback`, and `user_post_tags` rows. Therefore this audit cannot prove a
specific historical reaction was consumed or dropped in this database. It can
prove that the W29 HTML contains no reaction receipt and that the code has no
reaction-to-ranking projection.

Separately, the Brief sidecar contains five confirmed W28 report-feedback
events and says feedback was used, including one promoted target and one trust
correction. The visible Brief still shows `No personal changes surfaced` and
generic `no confirmed feedback override` copy. This is a presentation and
mapping failure even for confirmed feedback, not merely a missing reaction-sync
run.

## Radar Handoff Analysis

The W29 Brief probes filenames using its report week. No W29 Radar file exists,
so its sidecar normalizes Radar to `not_available`. A valid completed-week Radar
artifact does exist:

- path: `Demand-to-MVP-Radar/reports/mvp_of_week/mvp-weekly-2026-W28.json`;
- run ID: `mvp-weekly-2026-W28`;
- selected candidate: `Hotkey Dictation Workflow Probe`;
- dossier status: `investigate`;
- recommendation: `revisit_with_evidence_gap`;
- score: `60`;
- matched candidate-specific external evidence: `0`.

The Radar artifact is safe in an important respect: `context_only` market
records are separated before candidate ranking and retained as decision context.
This behavior is implemented and tested in the sibling repository. IRX-10 must
reuse it, not reopen or weaken the gates.

The actual handoff defects are period identity and orchestration:

- Radar and split reports are separate commands/timers;
- there is no common manifest or required stage set;
- the Brief discards Radar run provenance during normalization;
- filename matching substitutes for same-run validation;
- the existing missing-Radar test treats a complete-looking report as success.

## Duplicate Thread Analysis

The database contains 1,290 current Idea Thread rows. The W29 Atlas selects 24;
11 of those titles participate in 19 heuristic near-duplicate pairs, while
seven of the 12 visible index titles participate in eight pairs. This does not
mean every pair should merge. For example, the broad `Claude / Anthropic`
cluster mixes labor, access, self-improvement, and agent-progress claims that
need splitting, while two Claude Sonnet price/performance variants likely need
merging. Vendor-token overlap has replaced idea-level curation.

Visible fragmentation includes Fable, Fable 5, and cross-entity Fable variants,
plus Claude, Claude Sonnet 5, Claude Code, and Anthropic combinations. Some
encode the same thesis; others combine unrelated theses. IRX-4 therefore needs
curated merge *and* split decisions, not a string-similarity merge job.

The existing deterministic builder groups atoms by normalized entity keys and
creates titles from the top entities. It has no durable canonical registry,
alias history, merge/split lifecycle, curator decision, or thesis-level naming
contract. IRX-4 must add those controls while preserving atom provenance and
stable references.

## Visualization Inventory

Existing visual primitives are limited to:

- metric cards;
- status tags;
- CSS momentum bars;
- card grids;
- four HTML tables;
- an Atlas thread index and text timelines.

There are no SVG, canvas, image, or figure elements in either W29 HTML file.
The separate legacy visual workbook contains reusable Archify/fallback diagram,
Russian copy, evidence-card, and responsive CSS patterns, but those patterns
were not carried into the split reports. A pipeline diagram is also not a
substitute for the required data visualizations.

## Quality-Gate Gap

Both sidecars report `quality_findings: []`.

Current split validators primarily check:

- standalone HTML;
- required section IDs;
- action ordering;
- absence of one internal match-trace pattern;
- coarse HTML byte length.

They do not test the analysis period, Radar same-run binding, generic action
repetition, reaction receipts, concrete project naming, Russian reader language,
thread title purity, progressive disclosure, semantic visual component count,
weekly thesis, `what not to do`, or visible internal IDs. This explains why the
reports are technically valid while failing reader value.

## Reusable Foundation

Reuse rather than rebuild:

- Knowledge Atom extraction, source URLs, evidence quotes, and confidence;
- deterministic Idea Thread candidate grouping and temporal metrics;
- Frontier Analysis bounded strong-model routing;
- `tra-intelligence-contract.v1` evidence projections;
- confirmed feedback provenance, correction history, and effect windows;
- reaction sync semantics and idempotent state;
- curated project registry and conservative project diagnostics;
- Radar dossier, validation query, missing-evidence, and kill-criteria fields;
- context-only candidate-ranking exclusion;
- split delivery and V1 artifact paths;
- Russian workbook copy and evidence-card patterns;
- deterministic report validators and dogfood scorecard framework;
- curated SQLite FTS, Hermes/PI read-only facade, and Obsidian projection.

The reference repository's `docs/DREAM_MEMORY_MAP.md` and static memory-map
HTML demonstrate useful offline graph principles: evidence-linked edges,
provisional versus confirmed states, bounded labels, and a static SVG/text
fallback. Reuse those information-design principles only. Report V2 must not
create a runtime or schema dependency on `Dream_Motif_Interpreter`.

All reuse is subject to additive V1/V2 compatibility adapters.

## Audit-Only Surface

The current `src/output/knowledge_atlas_report.py` renderer and its
`knowledge_atlas_thread_navigation.v1` sidecar should become the Knowledge Audit
Explorer baseline. Preserve:

- thread index and full detail;
- raw atom and membership inspection;
- claims, contradictions, evidence quotes, and source URLs;
- timeline rows and source diversity;
- internal slugs and enums;
- existing `atlas_thread` retrieval items.

Move that material behind a technical-details link. Do not delete it, silently
rename old files, or make it the first reader-facing Atlas surface.

## Audit Conclusion

W29 is a product-correction trigger, not proof that the underlying intelligence
system is empty. Report V2 must first correct period and run identity, then make
personalization and thread curation traceable, then add editorial synthesis and
information visualization. Starting dogfood on the current split reports would
measure already-known defects rather than product value.
