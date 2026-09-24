# Cost Architecture — Personal Assistant Target

Status: design; no new paid workload enabled. Existing `docs/COST_BUDGET.md`
remains the current budget boundary until an explicit revised budget is approved.
The owner's willingness to provide any models is a quality/resource preference,
not an infinite spend grant or privacy waiver.

## Two different costs

Development cost: planning/context packets, implementation, targeted review,
correction rounds and verification. Runtime cost: each successful chat/search/
brief/action plus ingestion, embedding, retries and background monitoring.
Measure separately. No percentage improvement for this repository is claimed.

## Workload decisions

- Chat: strong fixed baseline first, bounded relevant history and stable prefix.
- Search: deterministic retrieval/dedupe, bounded excerpts, measured synthesis;
  public provider queries must not contain unnecessary private text.
- Deep research: explicit step/time/cost budget, checkpoint/cancel, no runaway fan-out.
- Briefs: incremental event state, common BriefDocument, presentation-only export;
  do not pay for re-generation merely to change layout.
- Extraction: cheap/local where quality measured; high-stakes dates verified
  against authoritative structured source, not classifier confidence alone.
- Embeddings/reranking/media/judges: separately permitted provider/data class.
- Routing/cascades: compare with a strong baseline on the same holdout; require
  quality/latency/privacy evidence, not lower token count alone.

## Cache and telemetry

Stable prompt prefix; task-specific suffix. Cache by source version, account,
permission revision, model/prompt identity and transformation. Revocation or
source change invalidates dependent state. Avoid cross-source/private cache leaks.
Record observed model, tariff version, uncached/cached input, output, retries,
latency and total cost per successful task. Unknown tariff stays unknown with
conservative caps, not the cheapest-model estimate. No raw user text in telemetry.

## Required implementation decisions

Before a paid pilot choose actual provider/model IDs, retention settings,
per-request and monthly budgets, allowed fallback providers, deep-research cap,
background allowance and eval budget. User sees expensive-job preview and can
cancel. Budget exhaustion produces useful partial results without unsafe fallback.
PA-02 provides enforcement; PA-16 supplies matched quality/cost evidence.
