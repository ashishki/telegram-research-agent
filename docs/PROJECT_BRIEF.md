# Project Brief

Project: `telegram-research-agent`

Mode: Standard

Last updated: 2026-07-26

Playbook SHA: `5583eca96c4d2d480b5574ed78bea63e0b07ebf0`

## 1. Project

- **Project name:** telegram-research-agent
- **One-sentence summary:** A private Telegram archive memory and grounded
  assistant for one operator's AI, engineering, product, market, and career
  research.
- **Why this project exists:** The operator reads many Telegram channels and
  needs the accumulated corpus to answer concrete work and life questions with
  source links, not just produce weekly reports.
- **What success looks like in v1:** The operator asks real questions and gets
  useful, cited, freshness-aware answers from the full retained archive, with
  optional confirmation-gated saving into durable knowledge objects.

## 1b. Problem Fit And Adoption Reality

- **Concrete operational pain:** W29 reports omitted all useful reaction
  personalization despite 7 detected personal reactions, forced manual source
  verification, and exposed a large Atlas instead of an answerable memory.
- **Current workaround:** The operator manually searches Telegram, opens
  generated HTML/JSON, inspects repo artifacts, and asks separate tools to
  recover source posts or validate claims.
- **Why existing process is insufficient:** Weekly artifacts are projections,
  not a queryable memory; curated-only retrieval hides posts without Knowledge
  Atoms; manual verification does not scale across thousands of retained posts.
- **First operator who feels the pain:** The private repo owner/operator.
- **What would make v1 not worth adopting:** The assistant cannot retrieve
  known retained posts with Telegram links, especially reacted posts, within a
  short interactive loop.
- **Adoption proof metric:** A human-approved query set retrieves exact
  Telegram source links from the canonical archive without requiring Knowledge
  Atoms.
- **Claims out of bounds before evidence:** full-archive RAG shipped,
  assistant reliability proven, dogfood success, portfolio value, vector search
  superiority, production readiness, autonomous preference learning.
- **Work AI will not replace:** Human approval of saved memory, permanent
  preferences, project decisions, external verification conclusions, and final
  task completion.
- **Service delta:** Less manual search time, better source recovery, explicit
  no-answer behavior, lower false confidence, and more usable project/career
  recall.

## 1c. Evidence Plan From Day 1

- **First proof metric:** Known-item hit@10 and citation precision on a
  human-approved subset of the 50-query retrieval set.
- **Evaluation dataset source:** Candidate queries drafted in
  `evals/retrieval/query_set_candidate.jsonl`; gold labels require human
  approval and source IDs.
- **Minimum eval set size for v1:** 50 candidate queries; a meaningful
  human-approved subset before PRM-3 completion.
- **Known failure slices:** exact phrase, semantic topic, cases, comparison,
  freshness, project/life application, distractors, no-answer, duplicates,
  reposts, missing URLs, unstable external facts.
- **Human review owner and budget:** private operator; initial budget 50-100
  minutes to approve query labels and expected evidence.
- **LLM judge:** advisory only until calibrated against human labels.
- **Release gate:** manual approval plus deterministic Playbook validation and
  task-specific retrieval/generation/tool evaluation.

## 2. Users And Workflows

- **Primary user:** one private operator.
- **Main workflow 1:** Ask exact or conceptual questions over the Telegram
  archive and receive cited results.
- **Main workflow 2:** Save useful answers as Knowledge Notes, Watch Topics,
  project context, decisions, or experiments after confirmation.
- **Main workflow 3:** Review secondary weekly projections derived from actual
  queries, reactions, saved notes, watch topics, projects, and experiments.

## 3. Scope

In scope for v1:

- full retained Telegram text archive search;
- selective enrichment for reacted, repeatedly retrieved, saved, watched, or
  project-relevant posts;
- one assistant entrypoint with bounded read-only search tools;
- explicit insufficient-evidence behavior;
- confirmation-gated writes to curated memory;
- privacy, cost, rollback, and evaluation contracts.

Out of scope:

- public SaaS or multi-user architecture;
- automatic product builds or purchases;
- broad filesystem mutation through assistant tools;
- full archive LLM backfill;
- vector database before FTS baseline evaluation;
- generic cross-domain memory platform;
- automatic permanent preference changes.

## 4. AI Scope

- **Where AI may be needed:** query interpretation, evidence synthesis,
  selective extraction, comparison, contradiction surfacing, and optional
  external verification summarization.
- **Where AI is not wanted:** canonical storage, FTS indexing, permissions,
  data retention, write confirmation, cost limits, rollback, and eval scoring
  where deterministic checks are possible.
- **Minimum sufficient shape expected:** local deterministic archive search
  plus bounded tool-use assistant; Agentic profile stays ON because current and
  target assistant behavior can plan up to a small number of read-only tools.
- **Retrieval need:** RAG profile ON.
- **Tool-use need:** Tool-Use profile ON for bounded read-only and
  confirmation-gated proposal tools.
- **Planning profile:** OFF; persisted plans are not the user product.
- **Compliance profile:** OFF; no named regulatory framework is selected.

## 5. Human Approval Boundaries

Human approval is required for:

- product pivot ADR acceptance;
- gold query labels;
- external data egress for embeddings or web verification storage;
- permanent preferences/profile/config changes;
- saved Knowledge Notes, Watch Topics, project links, decisions, actions, and
  experiments;
- vector backend selection;
- dogfood start and final success claim.

## 6. Risk And Error Cost

The main risk is private-data misuse or false confidence: the assistant may
cite weak Telegram claims as truth, hide insufficient evidence, or leak raw
corpus text to providers/logs. The system must preserve provenance, separate
Telegram evidence from model background and external verification, and expose
unknown states honestly.

## 7. Data

- **Primary data sources:** local SQLite `raw_posts` and `posts`, Telegram
  source URLs, reactions, feedback, generated reports, and curated knowledge
  artifacts.
- **Observed local volume during retrofit:** 3,477 `raw_posts`, 3,477 `posts`,
  3,477 `posts_fts`, 1,346 `knowledge_atoms`, 1,290 `idea_threads`.
- **Sensitive data:** private Telegram corpus, operator reactions, feedback,
  project context, Telegram session and provider secrets.
- **Retention:** preserve canonical archive unless explicit deletion policy
  applies; generated private reports remain ignored.

## 8. Integrations

- Telegram via Telethon and bot APIs.
- SQLite local database.
- LLM provider via existing `src/llm/client.py`.
- Demand-to-MVP Radar remains a secondary integration.
- External web/research skills are disabled until trust records pass.

## 9. Runtime And Operations

Runtime tier: T1. The product uses bounded local scripts, bot process, and
systemd-style scheduled jobs. It does not require a persistent privileged T3
agent runtime.

## 10. Model And Cost Expectations

- Cost sensitivity: medium.
- Latency sensitivity: high for interactive archive search, medium for
  background enrichment.
- Default model path: no model for FTS search; cheap bounded model for
  extraction; stronger model only for synthesis that passes evidence gates.
- Budget overruns require human approval.

## 11. Success Metrics

- **Retrieval quality:** known-item hit@10, MRR, citation precision,
  no-answer accuracy, freshness handling, duplicate top-10 rate.
- **Generation quality:** faithfulness, relevance, citation correctness,
  unsupported-claim rate, human correction rate, usefulness score.
- **Operations:** index freshness, p95 local retrieval latency, cost per useful
  answer, queue failure receipts.
- **Dogfood:** 30 real questions over four weeks and evidence that the operator
  wants to continue using the product.
