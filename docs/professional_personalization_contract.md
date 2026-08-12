# Professional Personalization Contract

Status: proposed, requires operator approval before configuration changes
Date: 2026-08-12
Schema version: `professional_personalization.v2.proposed`

## Goal

Personalization should help the private operator understand, decide, build,
learn, write, and advance professionally with less friction.

It must not hide useful archive evidence. Retrieval recall stays broad; lens
and project context influence reranking, framing, and action selection.

## Layer Separation

1. Recall
   - Retrieve potentially relevant archive evidence broadly.
   - Use topic/source downranks only as soft ranking signals, not hard filters.
   - Do not exclude a source globally when it may be useful for a specific
     lens.

2. Rerank
   - Order close candidates by professional lens, active project, freshness,
     reaction signals, source quality, and source class.
   - Treat reactions as temporary interest boosts unless repeated evidence
     leads to an explicit preference proposal.

3. Framing
   - Explain results in the vocabulary of the current professional goal.
   - Make uncertainty and verification status explicit.

4. Action
   - Propose at most one bounded next step.
   - Durable notes, watches, project links, actions, experiments, and profile
     changes require confirmation.

## Final Professional Lenses

### `ai_systems_engineer`

Goals:

- agent reliability;
- evaluation;
- RAG quality;
- observability;
- cost control;
- runtime safety;
- bounded tool use.

Preferred evidence:

- official documentation;
- GitHub repositories;
- code;
- primary benchmarks with methodology;
- production postmortems.

Preferred outputs:

- architecture pattern;
- failure mode;
- implementation idea;
- eval case;
- risk boundary.

### `portfolio_builder`

Goals:

- improve strongest repositories;
- produce demonstrable evidence;
- close one visible skill gap;
- turn research into a PR-sized improvement.

Preferred evidence:

- repository docs/tasks/tests;
- existing receipts;
- source-backed implementation patterns;
- role requirements linked to portfolio proof.

Preferred outputs:

- repo implication;
- PR-sized change;
- acceptance criteria;
- portfolio narrative.

### `career`

Goals:

- Agentic AI Engineer readiness;
- AI Systems / Solutions Architect readiness;
- interview and portfolio evidence;
- recurring market skill signals.

Preferred evidence:

- job descriptions or current market sources after verification;
- repeated archive signals;
- portfolio repository evidence;
- explicit missing proof.

Preferred outputs:

- recurring requirement;
- current portfolio evidence;
- missing proof;
- next career action.

### `product_strategy`

Goals:

- AI adoption pain;
- workflow automation opportunities;
- demand evidence;
- buyer/workaround signals;
- do-not-build boundaries.

Preferred evidence:

- repeated user/business pain;
- independent cases;
- manual workaround signals;
- measurable effect;
- external validation when current.

Preferred outputs:

- problem pattern;
- evidence maturity;
- validation step;
- do-not-build boundary.

### `enterprise_ai_adoption`

Goals:

- operating-model change;
- role-specific adoption;
- guardrails and training;
- measurable rollout;
- enterprise failure modes.

Preferred evidence:

- official enterprise case studies;
- practitioner postmortems;
- implementation details;
- adoption metrics;
- risk/guardrail examples.

Preferred outputs:

- enterprise case;
- failure mode;
- adoption metric;
- relevant project implication.

### `writer_editor`

Goals:

- source-backed Russian posts;
- strong thesis;
- concrete examples;
- counterargument;
- practical takeaway.

Preferred evidence:

- Telegram discovery signals;
- primary sources for current claims;
- cases with clear stakes;
- source links.

Preferred outputs:

- editor brief;
- evidence packet;
- story angle;
- source links;
- claims requiring verification.

### `learning`

Goals:

- understand difficult ideas;
- connect ideas to existing knowledge;
- run a small experiment;
- retain useful explanations.

Preferred evidence:

- clear definitions;
- examples from sources;
- project context;
- small runnable experiments.

Preferred outputs:

- plain explanation;
- analogy;
- source evidence;
- experiment;
- success criterion;
- reflection question.

## Source And Topic Policy

- A model announcement is downranked by default when it is hype-only.
- It must be surfaced when it changes cost, capability, API, architecture, eval
  design, or an active-project decision.
- Benchmark methodology and benchmark marketing are separate signal types.
- A source may be weak for technical evidence but useful for culture, career,
  product discovery, or writing angle discovery.
- Telegram is discovery evidence for current claims; official/current sources
  are required before pricing, API, legal, medical, financial, visa, or
  high-stakes claims become recommendations.

## Temporary Versus Permanent Preferences

Allowed without confirmation:

- per-answer reranking based on explicit user wording;
- short-term volatile follow-up context;
- temporary boost from a recent reaction;
- a one-turn lens inferred from query language.

Requires explicit confirmation:

- permanent `profile.yaml` changes;
- new default lens;
- global source downrank;
- project active/priority changes;
- automatic reminders;
- durable saved memory;
- durable watch topics;
- project links/actions/experiments.

Repeated behavior may create a proposal, not an automatic preference.

## Profile Migration From Current Flat Model

Current `src/config/profile.yaml` maps to V2 as follows:

| Current field | V2 role |
| --- | --- |
| `boost_topics` | soft rerank features per lens; never hard recall filters |
| `downrank_topics` | soft downrank reasons with lens exceptions |
| `downrank_sources` | source-quality priors with lens-specific override |
| `cultural_keywords` | writer/culture signal lane, not technical evidence |

New configuration should be versioned and reviewed before write. Proposed
runtime shape:

```yaml
schema_version: professional_personalization.v2
default_lenses:
  - ai_systems_engineer
  - portfolio_builder
lens_policy:
  recall_never_reduced_by_lens: true
  durable_changes_require_confirmation: true
professional_lenses:
  ai_systems_engineer: ...
```

No config mutation is approved by this document.

## Project Context Schema

Proposed schema version: `project_portfolio_context.v2`.

Required fields:

```yaml
name: telegram-research-agent
repo: ashishki/telegram-research-agent
status: priority
priority: 1
current_goal: "make PRM daily Telegram use dogfood-ready"
current_blocker: "PRM-19 dogfood-start approval and PRM-UX minimum slice"
next_proof: "10-question smoke eval plus real PRM-19 labels"
relevant_capabilities:
  - rag quality
  - conversational ux
  - evaluation
preferred_signal_types:
  - source-backed UX failure
  - eval case
  - project action
excluded_signal_types:
  - broad hype
  - report-era suggestions
last_reviewed_at: "2026-08-12"
owner_confirmation_status: proposed
```

Rules:

- Use only a small active/priority set by default.
- Do not route every signal to every repository.
- Project recommendations require direct evidence.
- Broad keyword overlap is not a project implication.
- Reference projects can supply patterns but should not receive action
  recommendations by default.
- Paused/archived projects are excluded unless explicitly named.

## Candidate Active Project Classification

This is a proposal, not approved configuration.

| Project | Local verification | Proposed status | Priority | Default use |
| --- | --- | --- | ---: | --- |
| `telegram-research-agent` | current repo present | priority | 1 | default active project for PRM UX/RAG/eval improvements |
| `AI_workflow_playbook` | repo present; current Playbook source | priority | 2 | workflow/eval/playbook evidence and portfolio narrative |
| `AI-Rollout-Training-OS` | repo present | watch | 3 | enterprise adoption cases and training/guardrail patterns |
| `Demand-to-MVP-Radar` | repo present | watch | 3 | demand/product validation patterns only when product lens is active |
| `Workflow-to-Agent-Studio` | repo present | watch | 4 | workflow automation / solution architecture patterns |
| `Dream_Motif_Interpreter` | repo present, pre-existing local changes | reference | 5 | Telegram/voice/RAG UX reference only |
| `Lead-Response-SLA-Agent` | repo present in workspace | watch | 4 | customer-facing safe automation reference |
| `Eval-Ground-Truth-Lab` | not present in workspace | reference | 4 | candidate portfolio proof; verify before routing |
| `Agent-Runtime-Grid` | not present in workspace | reference | 4 | candidate runtime architecture proof; verify before routing |

Human approval is required before changing `projects.yaml`, active status,
priority, or the default active project set.

## Human Approval Rules

Explicit approval is required for:

- accepting this schema;
- changing `profile.yaml`;
- changing project active/priority status;
- changing default active projects;
- changing archive-refresh schedule or timezone;
- adding reaction sync to a routine service;
- enabling external verification;
- enabling external skills;
- changing provider-egress boundaries;
- starting PRM-19 dogfood;
- claiming dogfood success;
- deleting, moving, or archiving legacy code/docs.

