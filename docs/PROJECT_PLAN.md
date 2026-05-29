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

### P1 - Channel Intelligence Layer

- Track narratives over time.
- Track repeated claims.
- Track source trust signals.
- Add topic/entity graph.
- Connect project relevance to current portfolio tasks.

### P1 - Entropy Integration

- Add optional `research_brief_receipt`.
- Add evidence window per report.
- Add reviewer/referee pass for high-impact claims.
- Follow `docs/entropy_core_gensyn_integration.md`; Entropy Core is optional
  receipt vocabulary, not a runtime dependency.

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

## Stop Conditions

- Do not turn into a generic Telegram summarizer.
- Do not add product UI until weekly reports repeatedly influence decisions.
