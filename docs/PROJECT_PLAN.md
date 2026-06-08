# Telegram Research Agent - Project Plan

Status: active observation / future product line
Role: private Telegram channel research intelligence
Priority: P0/P1

## Strategic Role

Telegram Research Agent is the general ingestion and weekly briefing engine for
Telegram channels. It should stay private and operator-focused for now.

The likely product evolution is **Telegram Channel Intelligence**: evidence-
backed analysis of narratives, sources, claims, and project-relevant signals.

## Near-Term Roadmap

Execution details for the next development cycle live in
`docs/next_development_roadmap.md`. `docs/tasks.md` is the active AI
development queue. Reader-facing report quality and Radar handoff details live
in `docs/report_quality_roadmap.md`.

### P0 - Reader-Facing Report Quality

- Add a first-screen Decision Brief to the weekly Research Brief.
- Show what was evaluated, what changed, what action follows, and why the
  operator should believe it.
- Add deterministic report-quality gates before delivery:
  - no internal `Matches: ...` traces as user takeaways;
  - no Study Plan / digest contradiction;
  - no Project Insights / digest contradiction;
  - no missing or buried trend summary.
- Turn proof receipts and evidence lookup into a concise reader-facing
  confidence/source-mix summary.
- Keep the report as a private operator decision surface, not a generic news
  digest.

### P0 - Demand-to-MVP Radar Honesty

- Radar work happens in `/srv/openclaw-you/workspace/Demand-to-MVP-Radar`.
- Change Radar weekly output from overconfident "MVP of the Week" framing to a
  Candidate Dossier when source evidence only supports investigation.
- Enforce one canonical final gate: Markdown and JSON must not disagree.
- Show selected-candidate source mix, missing credentials, missing evidence,
  next experiment, and kill criteria.
- Do not treat Telegram-only seeds as build-ready product validation.

### P0 - Operator Usefulness Log

- Track weekly:
  - which briefs were useful
  - which claims affected decisions
  - which channels were noisy
  - which sources gained/lost trust
- Keep examples of useful sections.

### P0 - Evidence Discipline

- Require source links/citations for brief claims.
- Add broken-source checks.
- Separate summaries from recommendations.
- Use `src/proof_receipts.py` to expose Core-compatible Research Brief receipt
  views for delivered weekly briefs.
- Add deterministic Core-style evidence lookup checks for delivered Research
  Brief receipts.
- Pin Core-compatible receipt schema fields before changing receipt contracts.

### P1 - Channel Intelligence Layer

- Track narratives over time.
- Track repeated claims.
- Track source trust signals.
- Add topic/entity graph.
- Connect project relevance to current portfolio tasks.
- Surface source down-rank explanations from observed local behavior.

### P1 - Entropy Integration

- Keep implemented `research_brief_receipt` storage and verification as the
  local source of truth.
- Use implemented CLI inspection for the Core-compatible receipt view.
- Evidence lookup checks for Core-compatible receipt refs are implemented.
- Schema compatibility and product-local boundary guards are implemented.
- Add reviewer/referee pass for high-impact claims after source trust
  explanations have accumulated enough observed evidence.
- Follow `docs/entropy_core_gensyn_integration.md`; Entropy Core is optional
  receipt vocabulary, not a runtime dependency.

### P1 - Operator Feedback And Reporting

- Artifact-level feedback beyond weekly usefulness logs is implemented.
- Monthly operator report summarizing reactions, button decisions, costs,
  low-signal weeks, and fallback delivery is implemented.
- Add low-friction Telegram artifact feedback buttons for Research Brief,
  Implementation Ideas, MVP of the Week, and optionally Study Plan.
- Keep all feedback product-local and based on observed behavior.

### P1 - Internal Cost Guardrails

- Dogfood the `LLM Cost & Guardrail Budget Sentinel` idea inside this private
  agent before considering any separate product.
- Use existing `llm_usage` rows for weekly budget, category cost, and spike
  warnings.
- Surface warnings in `cost-stats`, `operator-report`, and optionally weekly
  delivery notifications.

### P2 - Product Split

- Keep private research assistant as internal tool.
- If useful, split a productized Telegram Channel Intelligence repo or product
  workspace later.

## AI-Development Tasks

- Use AI for summarization, clustering, and project relevance.
- Keep extraction schemas strict.
- Do not let AI invent source trust; trust signals must come from observed
  behavior.
- Use deterministic citation checks.
- Reject Core-compatible receipt generation when no source evidence refs exist.

## Stop Conditions

- Do not turn into a generic Telegram summarizer.
- Do not add product UI until weekly reports repeatedly influence decisions.
