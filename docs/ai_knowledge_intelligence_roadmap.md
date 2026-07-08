# AI Knowledge Intelligence Roadmap

Status: active roadmap
Created: 2026-07-06
Last updated: 2026-07-07

## Why This Exists

The current Telegram Research Agent no longer matches the operator need.

Observed on 2026-07-06:

- Telegram ingestion works: the weekly ingest collected, normalized, clustered,
  topic-detected, and scored hundreds of recent posts.
- MVP weekly still runs as a separate downstream artifact.
- The weekly digest timer was inactive after 2026-06-22, so Research Brief and
  Implementation Ideas did not run for two weeks until manually restarted.
- When the digest was run manually for 2026-W28, it generated artifacts, but
  report-quality logs still showed reader-facing internal traces such as
  `Matches: ...`, a Study Plan contradiction, and Project Insights saying no
  insights while the Research Brief contained project-like sections.
- Scoring produced `0 strong` while the operator manually found many useful
  posts in AI Telegram groups. This means the current strong/watch/noise scoring
  does not model the operator's actual taste or learning goal.

The product should shift from a project/MVP recommender with a weekly digest into
a personal AI intelligence desk:

```text
all Telegram posts
  -> durable knowledge archive
  -> cheap structured extraction
  -> temporal idea graph
  -> frontier-model weekly analysis
  -> human-readable HTML report
  -> generated Obsidian knowledge vault
  -> personal read/try/build loop
```

MVP Radar and project implementation ideas remain useful, but they should become
downstream consumers of the knowledge base, not the primary weekly product.

## Product Goal

Build a personal AI Knowledge Intelligence system that reads AI-focused
Telegram channels over time and explains:

- what changed this week;
- which ideas, tools, practices, claims, and risks are evolving;
- what is stale, superseded, hype-only, or becoming production practice;
- which posts are worth reading;
- what the operator should try to develop AI systems engineering skill;
- how current signals compare with the last 30/90 days of channel history.
- how the evolving knowledge base can be browsed as a generated Obsidian vault.

The main weekly artifact is a designed HTML report. Telegram should deliver a
short notification with a link, not be the primary reading surface. Obsidian can
be a long-lived navigation surface for threads, weekly notes, tools, practices,
and learning actions, but not the runtime source of truth.

## Non-Goals

- Do not make MVP Radar the center of the new system.
- Do not use `project_state.md` as the main cross-project memory mechanism.
- Do not rely on `strong/watch/noise` as the only filter for knowledge capture.
- Do not feed thousands of raw posts directly to an expensive frontier model.
- Do not delete old knowledge just because it is stale; mark it as stale,
  superseded, resolved, or hype-only.
- Do not make Obsidian or any Markdown vault the primary database.
- Do not create one permanent note per Telegram post. Keep raw posts in the
  archive and project curated, grouped knowledge into the vault.

## Target Architecture

### 1. Raw Archive

Keep all posts from each configured channel as source material.

Required post-level facts:

- channel;
- message id and Telegram URL;
- posted_at;
- raw text and normalized text;
- links and referenced domains;
- media metadata when available;
- views/reactions when available;
- language;
- ingestion batch id;
- source reliability metadata.

Raw archive is not a report. It is the durable evidence layer.

### 2. Knowledge Atoms

A cheap model processes posts in bounded batches and extracts structured JSON.
It should not write prose reports.

Atom types:

- `tool_release`
- `model_update`
- `workflow_pattern`
- `engineering_practice`
- `benchmark_claim`
- `market_signal`
- `risk_warning`
- `case_study`
- `tutorial_resource`
- `opinion_shift`
- `research_claim`
- `pricing_or_limit_change`
- `regulatory_or_access_change`

Each atom should include:

- source post ids;
- short claim;
- normalized entities;
- evidence quote/excerpt;
- confidence;
- novelty estimate;
- practical utility estimate;
- expiry/staleness hints;
- why it matters for an AI systems engineer.

### 3. Idea Threads

Knowledge atoms are grouped into evolving ideas.

Examples:

- Claude Code / Codex / Cursor workflows;
- eval-driven AI engineering;
- MCP and tool ecosystems;
- agentic coding;
- local-first knowledge bases;
- voice agents;
- AI cost/ROI;
- browser automation;
- open-source model deployment;
- AI implementation barriers in business;
- source-grounded research workflows.

Each thread stores:

- first_seen_at;
- last_seen_at;
- active channels;
- key claims;
- related tools/models;
- related practices;
- contradictions;
- status: `active`, `stale`, `superseded`, `resolved`, `hype_only`,
  `production_pattern`;
- 7/30/90 day momentum.

### 4. Temporal Evolution Layer

The system must explain idea development, not just cluster current posts.

For each high-signal idea:

- how it appeared;
- what early claims were;
- what tools or model releases accelerated it;
- what practical patterns emerged;
- what broke or was contradicted;
- what became production practice;
- what is still only hype.

### 5. Frontier Weekly Analysis

Use the expensive/frontier model only after cheap extraction and thread
aggregation.

The frontier model receives:

- this week's new/changed atoms;
- thread histories for the last 30/90 days;
- strongest sources;
- contradictions;
- stale/superseded candidates;
- operator feedback and reading history.

The frontier model outputs:

- a weekly executive brief;
- what changed compared with last week;
- idea evolution narratives;
- read/try/build recommendations;
- source confidence and caveats.

### 6. HTML Intelligence Report

The primary weekly report is a multi-section HTML artifact.

Required sections:

1. Executive Brief
2. What Changed This Week
3. Idea Evolution Timelines
4. Tools, Models, and Practices
5. Contradictions and Unresolved Claims
6. Read Queue
7. Try This Week
8. Source Map
9. Appendix: grouped source posts

Design requirements:

- human-readable first screen;
- no internal traces such as `Matches: ...`;
- source links visible but not dominant;
- clear typography and section navigation;
- works as a standalone HTML file;
- Telegram notification contains only a short summary and link.

The stakeholder-facing variant is generated by `ai-visual-report`. It keeps the
same source-grounded Idea Thread / Knowledge Atom base, but spends extra render
work on a one-off visual HTML artifact:

- first-screen Decision Brief with top-model readout, trust caveats, and the
  most important "do now" / "study next" items;
- Archify data-flow diagram for the current knowledge pipeline and memory
  surfaces, placed after the decision sections so it supports auditability
  instead of becoming the report's main point;
- week delta metrics and atom-type distribution;
- conservative Project Implication leads against `src/config/projects.yaml`;
- trend momentum board for 7/30/90 day movement;
- frontier-model "study now" and "do next" actions;
- source/channel links and JSON sidecar for auditability.

Project implications are intentionally conservative. Broad overlaps such as
`AI`, `workflow`, `evidence`, and `tool` are not enough for a user-facing
project claim. If the report shows zero project leads, that means the current
atom/thread context did not support a specific enough project implication; this
is preferable to a noisy project-fit matrix that looks confident but only
reflects keyword overlap.

Install Archify as an agent skill directory and point `ARCHIFY_ROOT` at it, or
pass `--archify-root`. If unavailable, the command writes a deterministic
fallback diagram so the weekly delivery does not fail. Use `--deliver` with a
bot token and Telegram chat/channel id to send the HTML artifact as a document.

### 7. Obsidian Knowledge Vault Projection

Obsidian is useful as a human-facing cockpit for the knowledge system, not as
the ingestion store or runtime coordination layer.

The database remains authoritative for raw posts, knowledge atoms, idea threads,
feedback, and generation state. The vault is an idempotently generated
projection that makes the knowledge base easy to browse, review, and connect
with existing engineering cognition notes.

Recommended default:

- create a separate generated vault, for example `ai-intelligence-vault`, when
  the goal is high-volume AI-source intelligence;
- if reusing `engineering-cognition-vault`, write into a clearly scoped
  generated namespace such as `_generated/ai-intelligence/` or
  `80-ai-intelligence/`;
- only promote mature, project-relevant insights back into the hand-authored
  cognition vault areas.

Do not store every Telegram post as a note. The right granularity is:

- weekly intelligence notes;
- idea-thread notes;
- tool/model notes;
- engineering-practice notes;
- channel/source profile notes;
- read queue notes;
- try/build experiment notes.

Suggested folder layout for a dedicated projection vault:

```text
ai-intelligence-vault/
  00-dashboard/
  10-weekly/
  20-idea-threads/
  30-tools-models/
  40-practices/
  50-channels/
  60-read-queue/
  70-experiments/
  90-generated/
```

Every generated note should have stable frontmatter so future runs can update
it safely:

```yaml
---
type: idea_thread
status: active
first_seen: 2026-06-01
last_seen: 2026-07-06
momentum_7d: 0.72
channels: [ai_newz, neuraldeep]
entities: [Claude Code, Codex, MCP]
source_count: 18
generated_from: telegram-research-agent
---
```

The vault exporter must be deterministic:

- stable slugs for idea threads, tools, practices, channels, and weeks;
- generated file markers to avoid overwriting hand-authored notes;
- source links back to Telegram posts and report sections;
- no raw post dump unless explicitly requested for debugging;
- validation that generated Markdown has frontmatter, backlinks, and source
  references.

### 8. Personal Learning Loop

The report must actively develop the operator as an AI systems engineer.

Weekly output should include:

- five posts to read;
- two tools/workflows to try;
- one small experiment to run;
- one skill gap to close;
- one reflection question to answer.

Feedback to capture:

- read;
- useful;
- tried;
- applied to a project;
- too shallow;
- missed important post;
- wrong priority;
- not interested.

## KIR Quality And User-Value Roadmap After 2026-W28 Audit

Status: active quality/eval roadmap
Source: committed repository state plus the versioned 2026-W28 visual artifact.
The live DB/VPS pipeline was not evaluated for this audit.

### Short Diagnosis

The project is no longer just a digest bot. The repository already contains an
end-to-end knowledge-intelligence pipeline:

```text
Telegram posts
  -> durable archive
  -> Knowledge Atoms
  -> Idea Threads
  -> frontier synthesis
  -> HTML/JSON reports
  -> Archify audit map
  -> Obsidian projection
  -> feedback/read/try/build loop
  -> downstream MVP Radar and project consumers
```

The W28 artifact proves that the plumbing works: it contains 12 idea threads,
14 rendered source atoms, 4 source channels, 4 actions, a JSON sidecar,
Decision Brief, Trust Check, Do Now, Study Next, What Changed, Project
Implications, Knowledge Flow, Trend Board, and Sources.

The current bottleneck is not ingestion, HTML rendering, Archify, or Obsidian.
The bottleneck is synthesis quality, personalization, and the eval loop. The old
scoring produced `0 strong` while the operator manually found useful posts,
which means system scoring does not yet match the real user task.

KIR-050 finished the infrastructure loop, but it did not finish the user-value
work. The next queue is a quality/eval/user-value roadmap, not another feature
roadmap.

### Product Quality Target

A weekly report is good only if the operator can quickly understand:

- what changed this week;
- what changed compared with previous weeks;
- which 3-5 claims matter;
- which claims are weak, single-source, vendor-adjacent, or speculative;
- what to read;
- what to try;
- what to ignore or defer;
- how the signals relate to active projects/profile;
- which minimum feedback will make the next report better.

HTML remains the weekly decision artifact. Archify remains an audit/navigation
surface. Obsidian remains a generated projection/cockpit. SQLite/local evidence
remains the source of truth.

Final HTML language contract:

- operator-facing weekly HTML report copy must be Russian;
- section headings, cards, action labels, caveats, empty states, and feedback
  prompts must be Russian;
- internal JSON keys, CLI names, schema fields, code identifiers, and source
  titles may remain English;
- source quotes should keep their original language unless a separate
  translation field is added.

### P0 - Report Quality Contract

Introduce a strict report contract. A report is not good merely because all
sections exist; it must pass user-value gates.

Required first-screen blocks:

- `Operator Verdict`: apply, study, watch, ignore/defer, verify first;
- `Top Claims Evidence`: source count, source type, independent confirmation,
  quote verification, confidence, contradiction/caveat, expiry, and next
  verification step;
- `What Changed`: previous state -> new evidence -> updated interpretation ->
  confidence movement;
- `Operational Actions`: effort, scope, success criterion, kill condition, and
  feedback target;
- `Project Fit Diagnostic`: confirmed leads, project watch, learning-only
  implications, rejected broad overlaps, and missing evidence.

A report quality gate must fail when:

- top claims do not cite atom IDs;
- evidence quotes are missing or not verified against source text;
- source URL is missing for a high-impact claim;
- a single-source claim is written as an established trend;
- `What Changed` is only a count of changed threads;
- actions lack success criteria or feedback targets;
- zero project leads are shown without diagnostic explanation;
- no-feedback weeks do not warn that personalization confidence is low;
- the final user-facing HTML report is not Russian.

### P1 - Atom/Thread/Frontier Handoff Improvements

Knowledge Atom extraction already has bounded batches, JSON validation, source
IDs/URLs, confidence/novelty/utility/relevance scores, and idempotent batch
skips. The next improvement is claim quality, not extraction volume.

Add or derive these atom/report fields:

- `evidence_role`: primary announcement, commentary, user anecdote, benchmark
  claim, rumor, tutorial, case study;
- `source_independence_key`;
- `verification_status`;
- `quote_verified`;
- `claim_scope`;
- `time_horizon`;
- `expiry_hint`;
- `operator_relevance_reason`;
- `project_relevance_reason`.

Acceptance rule: a top claim cannot enter Decision Brief without source URL and
verified quote unless it is explicitly marked weak/single-source/speculative.

Idea Threads already group Knowledge Atoms and compute 7/30/90 momentum. The
next improvement is temporal interpretation.

Add per-thread fields or equivalent derived structure:

- `previous_week_state`;
- `this_week_delta`;
- `delta_reason`;
- `confidence_change`;
- `new_evidence_atom_ids`;
- `state`: emerging, accelerating, contested, validated, stale, superseded,
  hype-only, production-pattern;
- `why_this_is_one_thread`;
- `merge_split_audit_status`.

Frontier output should be structured as decision data, not prose that HTML has
to reinterpret:

```json
{
  "decisions": [
    {
      "title": "...",
      "status": "apply | study | watch | ignore | verify_first",
      "evidence_atom_ids": [1, 2],
      "confidence": "low | medium | high",
      "why_for_me": "...",
      "next_action": "...",
      "success_metric": "..."
    }
  ],
  "claim_cards": [
    {
      "claim": "...",
      "evidence_tier": "primary | secondary | anecdote | speculative",
      "source_count": 2,
      "independent_sources": 1,
      "caveat": "...",
      "verification_action": "..."
    }
  ],
  "thread_deltas": [
    {
      "thread_id": 10,
      "previous_state": "...",
      "new_state": "...",
      "delta_reason": "..."
    }
  ]
}
```

Project implications remain conservative. Do not loosen matching with broad
terms such as `AI`, `workflow`, `evidence`, and `tool`. Replace binary
"project links or zero" with three tiers:

- confirmed project lead: specific project overlap plus evidence;
- project watch: plausible but weak, not an action;
- learning-only implication: useful for the operator but not attached to a
  project.

### P2 - Longitudinal Intelligence

Start this only after 3-4 stable weekly runs with the P0/P1 gates:

- referee pass for only the 3-5 high-impact Decision Brief claims;
- thread merge/split audit CLI;
- monthly `changed beliefs` report;
- cautious scoped retrieval/embeddings over evidence items only, not over all
  raw posts.

The monthly report should show what became stronger, what was contradicted,
what was accepted, what was rejected, what remains uncertain, what was tried,
what was applied to a project, and what was ignored.

### End-To-End Development Stages

#### Stage 0 - Contract And Fixtures

Status: implemented by KIR-Q-001.

Goal: remove the false `done` state and define report quality as a testable
contract.

Work:

- update `docs/tasks.md` with KIR-Q open tasks;
- add the report contract to this roadmap;
- define JSON schema shape for decisions, claim cards, thread deltas, feedback
  targets, project diagnostic, and final HTML language metadata;
- use W28 artifact as the first regression fixture.

Acceptance:

- docs no longer say no KIR work remains;
- fixture can be checked without live DB/VPS run;
- tests can fail a structurally complete but low-value report;
- tests can fail a final HTML report whose user-facing copy is not Russian.

Implementation note:

- The code-facing contract lives in `src/output/ai_report_contract.py` as
  `weekly-ai-intelligence-v1`. It validates `decision_cards`, `claim_cards`,
  `thread_deltas`, `action_cards`, `project_diagnostic`, `feedback_targets`,
  and Russian final-HTML markers.
- `ai-visual-report` writes the contract fields into the JSON sidecar and uses
  them to render the operator-facing final HTML in Russian.
- The committed 2026-W28 artifact under
  `docs/artifacts/ai-decision-intelligence-2026-W28/` is now an offline
  regression fixture: tests can evaluate it without the live DB/VPS pipeline
  and currently flag it as pre-contract output.

#### Stage 1 - Claim Evidence Cards

Status: implemented by KIR-Q-002.

Goal: make claims auditable before they influence operator decisions.

Work:

- add evidence tier, evidence role, quote verification, source independence,
  claim scope, expiry, and caveat metadata;
- verify evidence quotes deterministically against source post text;
- render top claims in Russian HTML evidence cards;
- enforce single-source wording rules.

Acceptance:

- top claim without source URL or verified quote is blocked or labeled weak;
- W28-style high-impact claims show caveat and verification action;
- report gates catch missing atom provenance.

Implementation note:

- Weekly AI visual reports now attach local source-post text to Knowledge Atom
  context and verify claim-card `evidence_quote` values deterministically
  against `posts.content`.
- Claim cards include evidence tier, evidence role, source independence key(s),
  verification status, `quote_verified`, claim scope, time horizon, expiry hint,
  caveat, next verification action, and decision eligibility.
- Gates prevent missing atom IDs/URLs and prevent `apply`/`study` decisions
  from relying on unverified quote evidence unless the claim is explicitly weak
  and decision-ineligible.

#### Stage 2 - Temporal Delta Layer

Status: implemented by KIR-Q-003.

Goal: turn `What Changed` into a real temporal-intelligence surface.

Work:

- compute previous state, new evidence, delta reason, and confidence movement
  for top threads;
- render previous -> new -> interpretation;
- mark insufficient history explicitly;
- add thread merge/split audit hooks.

Acceptance:

- at least five top threads have clear delta or insufficient-history label;
- momentum bars are explained, not treated as quantitative truth;
- report no longer substitutes thread counts for interpretation.

Implementation note:

- Weekly report metadata now derives top `thread_deltas` by splitting each
  Idea Thread into previous atoms and this-week evidence.
- Russian HTML renders previous state -> new evidence -> updated interpretation
  with confidence movement, delta reason, source atom IDs, continuity rationale,
  and merge/split audit status.
- Gates require delta details for the available thread count and make
  `insufficient_history` explicit when no previous atoms exist.

#### Stage 3 - Project Fit Diagnostic

Status: implemented by KIR-Q-004.

Goal: make zero project leads useful without creating fake project matching.

Work:

- keep broad-term suppression;
- add confirmed lead / project watch / learning-only tiers;
- render checked projects, rejected overlaps, close-but-not-enough signals, and
  missing evidence/config additions.

Acceptance:

- 0 project leads explains what was checked and why nothing passed;
- learning-only implications stay visible;
- broad keyword overlap cannot become a confident project decision.

Implementation note:

- Project diagnostics now split confirmed leads, project watch, and
  learning-only implications, while broad overlaps are surfaced only as
  rejected close-but-not-enough signals.
- The Russian HTML report explains checked projects, rejected broad terms,
  missing evidence, and config additions needed to turn a learning signal into
  a project lead.
- Gates require the diagnostic shape and prevent zero-lead reports from being
  empty or falsely confident.

#### Stage 4 - Operational Action Cards

Status: implemented by KIR-Q-005.

Goal: make actions measurable and suitable for feedback in the next weekly run.

Work:

- render effort: 15/30/60 min or equivalent;
- render scope: skill, project, infra, reading, experiment;
- render success criterion, kill condition, feedback target, and follow-up
  date/hint;
- connect actions to stable target refs.

Acceptance:

- each action says what to do, how to know it worked, when to stop, and how to
  leave feedback;
- action outcomes can be recorded as useful, tried, applied_to_project,
  wrong_priority, too_shallow, or not_interested.

Implementation note:

- Weekly `action_cards` now include stable target refs, action kind, effort,
  scope, success criterion, kill condition, follow-up hint, feedback options,
  outcome policy, and feedback target linkage.
- The report contract guarantees at least two try actions and one experiment
  action even when frontier output is sparse.
- Russian HTML renders these fields so actions are measurable and do not count
  as useful until outcome feedback is recorded.

#### Stage 5 - Obsidian Projection Pruning

Status: implemented in KIR-Q-006.

Goal: keep Obsidian as a cockpit, not a database mirror.

Work:

- generate fewer term/channel notes;
- create experiment notes with hypothesis, method, result, decision, and
  optional project link;
- connect weekly note to top threads, five read items, two try items, one
  experiment, and project watches only when threshold passes;
- preserve generated markers and hand-authored overwrite protection.

Acceptance:

- no note explosion and no one-note-per-post output;
- generated notes have frontmatter, backlinks, source refs, and report links;
- mature insights are manually promotable into the hand-authored cognition
  vault.

Implementation:

- the exporter builds a bounded projection context from the weekly report
  contract, project diagnostics, and action cards;
- term/channel notes require repeated, promoted, decision-relevant, or
  active-high-signal evidence and are capped per folder;
- weekly notes link to top threads, capped read queue, two try actions, one
  experiment note, and project watches only when thresholds pass;
- experiment notes now carry hypothesis, method, result, decision, optional
  project link, source refs, generated markers, and manual-promotion guidance.

#### Stage 6 - Minimum Weekly Feedback And Eval Loop

Status: implemented in KIR-Q-007.

Goal: make personalization measurable.

Work:

- add weekly feedback completion indicator;
- require or request minimum weekly feedback: two read items, one action, one
  missed important post or explicit no-missed, and one trust correction when
  relevant;
- convert missed posts and wrong-priority labels into eval examples;
- feed previous feedback into frontier context.

Acceptance:

- next report can explicitly say what previous feedback changed;
- at least 3-5 feedback events are recordable for one report;
- no-feedback weeks show low personalization confidence.

Implementation:

- AI report feedback events support the minimum loop: two read events, one
  action/experiment outcome, missed-post or no-missed marker, and trust
  correction;
- summaries derive completion state, promoted/downranked targets, missed-post
  eval examples, priority-calibration eval examples, and frontier prompt
  guidance from the same feedback table;
- the weekly report contract and visual report expose feedback usage and
  low-personalization confidence instead of treating feedback as theoretical;
- frontier synthesis is instructed to downrank wrong-priority/not-interested
  patterns and promote useful/tried/read/applied patterns.

#### Stage 7 - Regeneration And Manual Eval

Goal: prove the roadmap on W28 and the standard run path.

Run:

```bash
python3 src/main.py knowledge-extract --weeks 12 --model cheap
python3 src/main.py idea-threads --weeks 12
python3 src/main.py frontier-analysis --week 2026-W28 --lookback-weeks 12 --model strong
python3 src/main.py ai-visual-report --week 2026-W28 --skip-refresh
python3 src/main.py obsidian-export --week 2026-W28
```

Acceptance:

- HTML passes structural gates plus claim/action/evidence/language gates;
- at least three feedback events are recorded;
- W28 before/after visibly improves first-screen clarity, evidence discipline,
  project diagnostic value, and action usefulness;
- final W28 HTML user-facing copy is Russian;
- Obsidian output remains scoped and disposable.

#### Stage 8 - Referee, Audit, Monthly Intelligence

Goal: add higher-cost intelligence checks after the weekly loop is stable.

Work:

- referee pass for only top high-impact claims;
- thread merge/split audit CLI;
- monthly changed-beliefs report;
- scoped retrieval over evidence items if deterministic context is
  insufficient.

Acceptance:

- top claims get second-pass scrutiny without expensive review of every atom;
- monthly report shows accepted/rejected/uncertain/tried/applied/ignored
  changes;
- embeddings are not introduced as a global raw-post memory.

### 7-Day Implementation Plan

Day 1:

- finish Stage 0;
- update docs/tasks;
- add report contract and schema notes;
- prepare W28 fixture.

Acceptance: false `done` is removed; W28 can be evaluated as fixture.

Day 2:

- implement claim evidence cards;
- add quote verification;
- render top five claim cards in Russian HTML.

Acceptance: unsupported high-impact claims are blocked or labeled weak.

Day 3:

- implement temporal thread deltas;
- replace count-based `What Changed` with previous/new/interpretation.

Acceptance: at least five top threads have delta or insufficient-history label.

Day 4:

- implement Project Fit Diagnostic;
- add confirmed/watch/learning-only tiers.

Acceptance: 0 project leads still produces useful diagnostic output.

Day 5:

- implement operational action cards;
- expose success criteria and feedback targets in Russian HTML.

Acceptance: every action has effort, success, kill condition, and feedback ref.

Day 6:

- prune Obsidian projection;
- add experiment note template and tighter weekly note links.

Acceptance: no note explosion; generated projection remains auditable.

Day 7:

- regenerate W28;
- run quality gates;
- record manual feedback events;
- compare artifact before/after.

Acceptance: structural, user-value, and Russian HTML gates pass; W28 diff
improves clarity.

### 30-Day Plan

Week 1:

- report contract;
- claim evidence cards;
- quote verification;
- operational action rendering.

Result: W28/W29 report has verdict, evidence cards, Russian user-facing HTML,
and action success criteria.

Week 2:

- temporal delta layer;
- project diagnostic;
- useful zero-lead state.

Result: `What Changed` becomes temporal intelligence and 0 project leads becomes
actionable diagnostic.

Week 3:

- feedback completion indicator;
- missed-post eval examples;
- wrong-priority and too-shallow examples in next frontier prompt.

Result: next report explicitly uses operator feedback.

Week 4:

- monthly changed-beliefs report;
- first thread merge/split audit;
- scoped referee pass for top claims.

Result: system reports what changed in beliefs/actions, not just what changed
in Telegram.

### Metrics

Track these per week:

- decision usefulness rate: useful + tried + applied_to_project / shown
  actions;
- read queue completion;
- try completion;
- experiment completion;
- evidence coverage for top claims;
- independent-source coverage for high-impact claims;
- temporal delta coverage for top threads;
- personal relevance precision: useful / not_interested;
- missed important post count;
- project implication precision, including accepted zero-lead diagnostic weeks;
- Russian HTML coverage for user-facing final report labels, sections, cards,
  caveats, and empty states.

After four weekly runs the system is better only if:

- there are at least 12-20 feedback events for the month;
- at least 50% of action cards have an outcome;
- top claims have evidence tier and caveat;
- missed important posts decline or become eval examples;
- at least two experiments were actually completed;
- the operator can name at least two decisions changed by the report.

### Guardrails And Non-Goals

Do not do now:

- public SaaS or multi-user UI;
- broad keyword project matching;
- one note per Telegram post;
- generic global vector memory over all raw posts;
- Archify as the main screen;
- HTML animation polish ahead of evidence/action metrics;
- feeding thousands of raw posts into the frontier model;
- auto-editing `profile.yaml` without explicit operator approval.

Guardrails:

- coverage badge: thin, adequate, strong;
- evidence tier: primary, secondary, anecdote, speculative;
- quote verification must match source text;
- single-source wording rule for strong trend language;
- weekly sample of top threads for merge/split quality;
- conservative project lead threshold;
- no-feedback warning for low personalization confidence;
- artifact receipt should expose scheduled, on-demand, partial, or regenerated
  run state;
- Obsidian generated namespace only, with manual promotion of mature notes;
- action is not counted useful until feedback records read/tried/applied.

### Key Risks

The system can sound confident while being wrong when:

- high-impact claims come from weak Telegram atoms;
- single-source anecdotes are turned into trends;
- deterministic thread grouping creates false continuity;
- frontier synthesis converts a few weak signals into a macro narrative;
- polished HTML/Obsidian/Archify surfaces hide a thin evidence base.

Examples to handle carefully in W28-style reports: GigaChat parity/speed,
J-space, Nvidia revenue-share, Stanford agentic-skill demand, Fable pricing, and
commoditization forecasts. These can be useful intelligence candidates, but
they need evidence tier, caveat, and verification action before they influence
decisions.

## Data Model Proposal

Add migrations for these tables or equivalent structures.

### `knowledge_extraction_batches`

- `id`
- `started_at`
- `completed_at`
- `week_label`
- `channel_username`
- `post_count`
- `model`
- `prompt_version`
- `status`
- `error`

### `knowledge_atoms`

- `id`
- `atom_type`
- `claim`
- `summary`
- `source_post_ids_json`
- `source_urls_json`
- `entities_json`
- `tools_json`
- `models_json`
- `practices_json`
- `confidence`
- `novelty_score`
- `practical_utility_score`
- `frontier_relevance_score`
- `operator_relevance_score`
- `staleness_status`
- `first_seen_at`
- `last_seen_at`
- `created_at`
- `updated_at`

### `idea_threads`

- `id`
- `title`
- `slug`
- `summary`
- `status`
- `first_seen_at`
- `last_seen_at`
- `momentum_7d`
- `momentum_30d`
- `momentum_90d`
- `key_entities_json`
- `current_claims_json`
- `superseded_claims_json`
- `contradictions_json`
- `updated_at`

### `idea_thread_atoms`

- `thread_id`
- `atom_id`
- `relation`
- `created_at`

### `operator_learning_actions`

- `id`
- `week_label`
- `action_type`
- `title`
- `source_urls_json`
- `status`
- `feedback`
- `created_at`
- `completed_at`

## Implementation Phases

### Phase 0: Stabilize Weekly Delivery

Purpose: make sure the system reliably runs before product changes continue.

Required work:

- keep `telegram-digest.timer` active;
- add a health check that fails if current-week digest is missing after the
  scheduled run window;
- add a guard against root-owned files under `data/output`;
- log/report if digest timer is inactive;
- make `llm_usage` recording non-blocking and low-contention.

Acceptance:

- `health-check` reports weekly delivery status;
- root-owned output files are detected before scheduled jobs fail;
- current week digest absence is visible without reading journal logs.

### Phase 1: Knowledge Atom Extraction MVP

Purpose: create a cheap structured knowledge layer from Telegram posts.

Required work:

- add schema for extraction batches and knowledge atoms;
- implement CLI command, for example:

  ```bash
  python3 src/main.py knowledge-extract --weeks 4 --model cheap
  ```

- process posts in bounded batches;
- store JSON atoms with source links;
- add deterministic validation for atom shape;
- add inspection command:

  ```bash
  python3 src/main.py memory inspect-knowledge-atoms --week 2026-W28
  ```

Acceptance:

- extraction can backfill at least four weeks;
- every atom cites source post ids/URLs;
- extraction is resumable and idempotent;
- no report prose is generated in this phase.

### Phase 2: Idea Thread Builder

Purpose: group atoms into evolving ideas.

Required work:

- add `idea_threads` and `idea_thread_atoms`;
- implement deterministic first-pass grouping using normalized entities,
  atom type, semantic keywords, and source-channel overlap;
- use cheap LLM only for ambiguous merges;
- compute 7/30/90 day momentum;
- mark stale/superseded candidates.

Acceptance:

- inspection command shows top active threads;
- thread timeline includes source atoms;
- stale status does not delete evidence;
- repeated claims across channels are visible.

### Phase 3: Weekly AI Intelligence HTML Report

Purpose: replace the current Research Brief as the primary user-facing report.

Required work:

- create `output/ai_intelligence_report.py`;
- generate standalone HTML with the required sections;
- use frontier model only over compressed thread context;
- include read/try/build learning actions;
- publish to Telegraph or store local HTML with Telegram notification;
- add report-quality gates that block internal traces.

Acceptance:

- report is readable without Telegram context;
- no `Matches: ...` or internal matching traces;
- report includes source map and appendix;
- report includes personal learning actions;
- Telegram notification links to the full report.

### Phase 3.5: Obsidian Projection Layer

Purpose: generate a navigable Obsidian vault from the same knowledge layer as
the HTML report.

Required work:

- add an `obsidian-export` command that reads idea threads, knowledge atoms,
  weekly reports, learning actions, and channel profiles;
- generate Markdown into a configured vault path;
- use stable slugs and generated-file markers;
- create weekly, idea-thread, tool/model, practice, channel, read-queue, and
  experiment notes;
- optionally link mature project-relevant notes into
  `engineering-cognition-vault`;
- validate frontmatter, backlinks, source references, and no accidental raw
  post dump.

Acceptance:

- exporter can regenerate the same week without duplicating notes;
- raw Telegram posts remain in the database, not as one-note-per-post vault
  clutter;
- generated notes link back to source posts and HTML report sections;
- hand-authored vault notes are not overwritten;
- Obsidian output works with a local dedicated vault or a scoped generated
  namespace inside `engineering-cognition-vault`.

### Phase 4: Feedback and Evaluation Loop

Purpose: make the system learn from the operator.

Required work:

- add feedback buttons or commands for read/useful/tried/missed/noise;
- store feedback against atoms, threads, and report sections;
- add weekly evaluation summary;
- use feedback to update operator relevance scoring.

Acceptance:

- at least five feedback events can be recorded from a report;
- next report can cite prior feedback as personalization context;
- missed-post feedback can be converted into eval examples.

### Phase 5: Downstream MVP and Project Consumers

Purpose: keep MVP Radar and project recommendations, but feed them from the
knowledge base.

Required work:

- MVP Radar reads market-signal and workaround threads;
- Implementation Ideas read engineering-practice and workflow-pattern threads;
- project matching stops depending only on keyword matches;
- downstream artifacts cite knowledge threads and source atoms.

Acceptance:

- MVP weekly can explain which knowledge threads informed candidates;
- implementation ideas do not run when knowledge/project context is stale;
- project insights no longer say "no insights" when the report contains
  project-relevant thread sections.

### Phase 6: Weekly Intelligence Workbook And Feedback Loop

Purpose: turn the weekly AI Intelligence report into a study/work artifact that
drives the operator's weekly read/try/build loop and makes feedback actionable.

Detailed task planning lives in `docs/ai_intelligence_workbook_roadmap.md`.

Required work:

- promote the visual report into a Weekly AI Intelligence Workbook with a
  concise Decision Brief, Strong Signals, Deep Explanation cards, Project
  Implementation, MVP Radar, Read/Try/Build, Feedback, and Appendix sections;
- add Deep Explanation sections for the strongest 3-5 signals;
- generate deterministic local concept diagrams, preferably Archify-style
  dataflow/concept diagrams;
- treat any visible operator reaction as positive implicit interest after
  Telethon personal-reaction visibility is validated;
- add voice feedback intake with transcription, structured LLM parse, bot
  confirmation, and confirmed-only memory writes;
- add a Strategy Reviewer that proposes memory/config/code improvements without
  applying them;
- generate Codex-ready task suggestions with title, files likely touched,
  acceptance criteria, and verification commands;
- refine Obsidian projection for workbook/read/try/build, feedback summaries,
  and Strategy Reviewer notes without one-note-per-post output.

Acceptance:

- first screen remains concise and decision-oriented;
- strongest signals explain what changed, why it matters, caveats, evidence
  strength, source links, and what to study/try;
- concept diagrams are deterministic and explanatory, not evidence;
- no reaction is treated as unknown, not negative;
- voice feedback does not affect memory until the operator confirms the parsed
  summary;
- the system never edits code, prompts, thresholds, `profile.yaml`, or
  `projects.yaml` without explicit human approval;
- Radar remains conservative: Telegram-seeded build/focused_experiment requires
  fresh KIR thread evidence, source atoms, source URLs, external
  corroboration, operator fit, and no blocking risk/profile mismatch.

## First Tasks for Next AI Development Session

Start from `docs/tasks.md`. The active queue is now
`KIR-Q: AI Intelligence Quality / Workbook / Feedback / Radar Contract`.

KIR-Q0..KIR-Q13 in that queue are implemented. Future sessions should not
restart from KIR-Q1; they should pick the first genuinely open task in
`docs/tasks.md`.

Current open/future work outside the completed Q0..Q13 queue:

- KIR-Q-008 standard regeneration/manual quality loop is partially verified,
  but forced frontier regeneration still needs `LLM_API_KEY` or
  `ANTHROPIC_API_KEY`.
- KIR-Q-009 referee/thread-audit/monthly changed-beliefs work is intentionally
  deferred until after 3-4 stable weekly runs.

## Suggested New Session Prompt

```text
Work in /srv/openclaw-you/workspace/telegram-research-agent on master.
Read docs/CODEX_PROMPT.md, docs/tasks.md, and
docs/ai_intelligence_workbook_roadmap.md. Also inspect the Demand-to-MVP-Radar
bridge at /srv/openclaw-you/workspace/Demand-to-MVP-Radar.

Continue from the first genuinely open task in docs/tasks.md. Do not restart
completed KIR-Q0..KIR-Q13 work unless fixing a discovered regression.

If working on KIR-Q-008, verify the standard weekly regeneration/manual quality
loop and only force frontier regeneration when LLM_API_KEY or ANTHROPIC_API_KEY
is configured. If working on KIR-Q-009, first confirm 3-4 stable weekly runs are
available as evidence.

Run:
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py tests/test_mvp_report_quality.py
```
