# Operator AI Systems Learning Roadmap

Version: 1.0
Last updated: 2026-07-10
Status: supporting learning roadmap

Goal: grow the operator toward AI Engineer / Applied AI Engineer / AI Systems
Engineer capability while improving this repository. At least 60-70% of learning
time should produce implementation, tests, evals, or portfolio artifacts in
`telegram-research-agent`.

Operator profile:

- Python developer / AI Engineer in development.
- Works with LLM apps, RAG, agentic workflows, evaluation, and
  infrastructure-oriented projects.
- Familiar with Python, FastAPI, PostgreSQL, Redis, Prefect, LangChain,
  LlamaIndex, Langfuse, Qdrant, Docker, and CI.
- Wants deeper architecture skill, not just API assembly.

## Learning Principles

- Reading is only stage 1.
- Mastery requires explaining, reproducing, implementing, testing, and applying
  to an active project.
- Every module should produce a portfolio artifact.
- Do not study broad topics unless a PGI task needs them.

## 4-6 Month Path

### Month 1 - Information Extraction And Evidence Modeling

Why it matters: `PGI-001` needs a clean SourceObservation -> EvidenceItem ->
Claim -> Atom contract.

Prerequisites: Python dataclasses/Pydantic, current `ai_report_contract.py`,
SQLite fixtures.

Concepts:

- information extraction;
- claim/evidence separation;
- evidence roles and tiers;
- quote verification;
- negative and contradictory evidence.

Coding exercise: create fixture-backed extraction cases where one source
contains support, contradiction, and context-only commentary.

Project task: `PGI-001`.

Portfolio artifact: domain model and correctness fixture report.

Mastery criterion: can explain why a summary is not a claim and why market
commentary is not demand evidence.

Duration: 3-4 weeks.

Do not study yet: large knowledge graphs or ontology tooling.

### Month 2 - Retrieval, Ranking, And Search Evaluation

Why it matters: Hermes and Atlas need curated retrieval, not raw Telegram RAG.

Prerequisites: existing `intelligence_retrieval_items.py`,
`assistant/semantic_retrieval.py`, tests `test_intelligence_retrieval_items.py`
and `test_semantic_retrieval.py`.

Concepts:

- lexical retrieval and FTS;
- metadata filtering before ranking;
- hit@k, precision@k, nDCG;
- citation precision;
- no-answer / insufficient-evidence behavior.

Coding exercise: build a small eval fixture with current-week, stale, and
missing artifacts.

Project task: `PGI-003` Hermes awareness and retrieval eval slice.

Portfolio artifact: Hermes retrieval eval table.

Mastery criterion: can defend why curated deterministic+FTS retrieval is the
right first step before vector search.

Duration: 3 weeks.

Do not study yet: large-scale ANN tuning or vector DB operations.

### Month 2-3 - Temporal Knowledge Representation

Why it matters: Atlas quality depends on temporal deltas, novelty, staleness,
and merge/split audit.

Prerequisites: `knowledge_atoms`, `idea_threads`, W28 fixture, ISO week
handling.

Concepts:

- event time vs processing time;
- novelty and staleness;
- temporal deltas;
- thread state transitions;
- merge/split audit.

Coding exercise: create two-week fixture where a thread forks and an old claim
is contradicted.

Project task: `PGI-001` and `PGI-004`.

Portfolio artifact: temporal thread evaluation report and Atlas v2 screenshot.

Mastery criterion: can distinguish momentum growth from evidence growth.

Duration: 3-4 weeks.

Do not study yet: graph databases unless Atlas tasks prove a real need.

### Month 3 - Feedback, Preference Learning, And Calibration

Why it matters: personalization must not become fragile reinforcement from weak
signals.

Prerequisites: `ai_report_feedback.py`, `action_status.py`, operator context
docs.

Concepts:

- explicit vs behavioral feedback;
- signal strength;
- append-only corrections;
- confidence calibration;
- Bayesian-style updates at a conceptual level;
- no-feedback as unknown.

Coding exercise: implement a fixture where `read`, `verify_first`, `tried`, and
`applied_to_project` have different ranking effects.

Project task: `PGI-002`.

Portfolio artifact: explainable ranking sidecar and feedback effect audit.

Mastery criterion: can explain why `verify_first` should calibrate trust rather
than promote a topic.

Duration: 3-4 weeks.

Do not study yet: deep recommender systems or collaborative filtering.

### Month 3-4 - LLM And Agent Evaluation

Why it matters: Hermes and weekly synthesis need grounded answers and
insufficient-evidence behavior.

Prerequisites: PI tool catalog, `pi_chat.py`, evaluation framework.

Concepts:

- groundedness;
- answer faithfulness;
- tool-call bounds;
- refusal/insufficient-evidence evaluation;
- regression fixtures;
- cost-aware evaluation.

Coding exercise: create 40 Hermes questions with expected cited objects and
failure labels.

Project task: `PGI-003` and `PGI-006`.

Portfolio artifact: Hermes answer eval dataset and scorecard.

Mastery criterion: can identify unsupported assistant synthesis from the
sidecar alone.

Duration: 4 weeks.

Do not study yet: autonomous multi-agent orchestration.

### Month 4 - Human-Computer Interaction And Information Architecture

Why it matters: the Brief and Atlas must reduce overload, not create prettier
reports.

Prerequisites: current split report HTML, dogfood checklist, basic CSS/HTML.

Concepts:

- progressive disclosure;
- decision-first UI;
- information scent;
- task-based usability testing;
- visual hierarchy for dense operational tools.

Coding exercise: run timed Brief and Atlas tasks and record failures before
redesign.

Project task: `PGI-003` and `PGI-004`.

Portfolio artifact: before/after usability notes and screenshots.

Mastery criterion: can show that first-screen Brief tasks complete faster
without hiding evidence gaps.

Duration: 3-4 weeks.

Do not study yet: large frontend frameworks or decorative graph visualization.

### Month 4-5 - Observability, Cost Control, And Reproducibility

Why it matters: portfolio-grade AI systems need bounded cost, graceful failures,
and reproducible demos.

Prerequisites: `cost_guardrails.py`, `delivery_health.py`, systemd docs, tests.

Concepts:

- cost telemetry;
- latency budgets;
- health checks;
- missing artifact states;
- deterministic fixture demos;
- CI quality gates.

Coding exercise: add a no-secrets demo path and cost/latency summary fixture.

Project task: `PGI-006` and `PGI-008`.

Portfolio artifact: reproducible local demo and cost/latency report.

Mastery criterion: can run a demo without private data and explain failure
modes.

Duration: 3 weeks.

Do not study yet: distributed tracing stacks unless local telemetry becomes
insufficient.

### Month 5-6 - Experimental Design And Product Analytics

Why it matters: the system must prove decision impact, not report volume.

Prerequisites: dogfood scorecard, decision/experiment/outcome model.

Concepts:

- hypothesis and kill criteria;
- outcome metrics;
- action completion vs value;
- false-confidence incidents;
- qualitative coding;
- baseline and guardrail metrics.

Coding exercise: design and run four weekly dogfood scorecards.

Project task: `PGI-007`.

Portfolio artifact: Weekly Verified Decision Impact report.

Mastery criterion: can make a restrained product claim backed by dogfood data
and failure cases.

Duration: 4-6 weeks.

Do not study yet: growth analytics, SaaS funnels, or multi-user telemetry.

## Mapping To Implementation Tasks

| Learning module | Primary tasks | Portfolio artifact |
|---|---|---|
| Information extraction and evidence modeling | `PGI-001` | domain model, evidence/claim fixtures |
| Retrieval and ranking eval | `PGI-003`, `PGI-006` | retrieval eval table |
| Temporal knowledge representation | `PGI-001`, `PGI-004` | thread delta eval |
| Preference learning and calibration | `PGI-002` | feedback/ranking audit |
| LLM and agent evaluation | `PGI-003`, `PGI-006` | Hermes answer eval |
| HCI and information architecture | `PGI-003`, `PGI-004` | usability before/after |
| Observability and reproducibility | `PGI-006`, `PGI-008` | demo and cost/latency report |
| Experimental design and analytics | `PGI-007` | dogfood impact report |

## Learning Outcome States

Each objective should be marked as one of:

- `read`;
- `understood`;
- `explained`;
- `reproduced`;
- `implemented`;
- `tested`;
- `applied_to_project`;
- `measured_result`;
- `stale_or_forgotten`;
- `prerequisite_gap`.

Only `implemented`, `tested`, `applied_to_project`, and `measured_result` count
as strong portfolio evidence.
