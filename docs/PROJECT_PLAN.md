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
development queue.

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
- Add evidence window per report.
- Add evidence lookup checks for Core-compatible receipt refs.
- Add reviewer/referee pass for high-impact claims.
- Follow `docs/entropy_core_gensyn_integration.md`; Entropy Core is optional
  receipt vocabulary, not a runtime dependency.

### P1 - Operator Feedback And Reporting

- Add artifact-level feedback beyond weekly usefulness logs.
- Add monthly operator report summarizing reactions, button decisions, costs,
  low-signal weeks, and fallback delivery.
- Keep all feedback product-local and based on observed behavior.

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
