# 1. Repository Understanding
- The project is a private Telegram intelligence pipeline: Telethon ingests channel posts, SQLite stores raw and normalized content, TF-IDF + KMeans groups posts, an Anthropic client synthesizes weekly artifacts, and a polling Telegram bot delivers them. The real runtime path is in [src/main.py](/srv/openclaw-you/workspace/telegram-research-agent/src/main.py#L69), [src/ingestion/bootstrap_ingest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/ingestion/bootstrap_ingest.py#L154), [src/processing/cluster.py](/srv/openclaw-you/workspace/telegram-research-agent/src/processing/cluster.py#L54), [src/output/generate_digest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_digest.py#L196), and [src/bot/bot.py](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/bot.py#L71).
- Main flow: Telegram posts are written into `raw_posts`, normalized into `posts`, assigned to `topics`, then used to generate Markdown digest/recommendations/study-plan/insight artifacts stored in SQLite and `data/output/*`; the bot mostly reads those Markdown files and sends them as chunked text. See [src/db/schema.sql](/srv/openclaw-you/workspace/telegram-research-agent/src/db/schema.sql#L3), [src/processing/normalize_posts.py](/srv/openclaw-you/workspace/telegram-research-agent/src/processing/normalize_posts.py#L57), [src/processing/detect_topics.py](/srv/openclaw-you/workspace/telegram-research-agent/src/processing/detect_topics.py#L162), and [src/bot/handlers.py](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/handlers.py#L225).
- Core modules/components:
  - Ingestion: [src/ingestion/bootstrap_ingest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/ingestion/bootstrap_ingest.py#L20), [src/ingestion/incremental_ingest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/ingestion/incremental_ingest.py#L32)
  - Processing: [src/processing/normalize_posts.py](/srv/openclaw-you/workspace/telegram-research-agent/src/processing/normalize_posts.py#L13), [src/processing/cluster.py](/srv/openclaw-you/workspace/telegram-research-agent/src/processing/cluster.py#L13), [src/processing/detect_topics.py](/srv/openclaw-you/workspace/telegram-research-agent/src/processing/detect_topics.py#L13)
  - Output: [src/output/generate_digest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_digest.py#L22), [src/output/generate_recommendations.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_recommendations.py#L13), [src/output/generate_study_plan.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_study_plan.py#L17), [src/output/map_project_insights.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/map_project_insights.py#L12)
  - Delivery: [src/bot/handlers.py](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/handlers.py#L89), [src/bot/bot.py](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/bot.py#L42)
  - LLM/config/db: [src/llm/client.py](/srv/openclaw-you/workspace/telegram-research-agent/src/llm/client.py#L10), [src/config/settings.py](/srv/openclaw-you/workspace/telegram-research-agent/src/config/settings.py#L19), [src/db/migrate.py](/srv/openclaw-you/workspace/telegram-research-agent/src/db/migrate.py#L21)
- Important observations:
  - Architecture docs still describe an OpenClaw gateway path, but implementation uses Anthropic SDK directly. Compare [docs/spec.md](/srv/openclaw-you/workspace/telegram-research-agent/docs/spec.md#L19) and [docs/architecture.md](/srv/openclaw-you/workspace/telegram-research-agent/docs/architecture.md#L24) with [src/llm/client.py](/srv/openclaw-you/workspace/telegram-research-agent/src/llm/client.py#L76).
  - Report generation is "LLM Markdown first"; there is no intermediate structured report model, no HTML renderer, no PDF renderer, and almost no output validation beyond heading checks. See [src/output/generate_digest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_digest.py#L277), [src/output/generate_recommendations.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_recommendations.py#L231).

# 2. What Is Already Good
- The pipeline boundary is conceptually sensible: deterministic ingestion/normalization/clustering, then LLM only for interpretation. That is the right cost/reliability shape for this product. See [src/main.py](/srv/openclaw-you/workspace/telegram-research-agent/src/main.py#L69).
- SQLite + FTS5 is a pragmatic fit here. The schema is small, WAL is enabled consistently, and the FTS triggers keep search in sync without extra jobs. See [src/db/schema.sql](/srv/openclaw-you/workspace/telegram-research-agent/src/db/schema.sql#L84).
- The LLM client has task-based model routing and retry logic, which is a good baseline for cost control. See [src/llm/client.py](/srv/openclaw-you/workspace/telegram-research-agent/src/llm/client.py#L16) and [src/llm/client.py](/srv/openclaw-you/workspace/telegram-research-agent/src/llm/client.py#L95).
- The systemd units are reasonably hardened for a small VPS deployment. See [systemd/telegram-digest.service](/srv/openclaw-you/workspace/telegram-research-agent/systemd/telegram-digest.service#L18).
- Prompt templates are externalized instead of being hardcoded into Python, which makes iteration faster. See [docs/prompts/digest_generation.md](/srv/openclaw-you/workspace/telegram-research-agent/docs/prompts/digest_generation.md#L16).

# 3. Main Problems and Rough Edges
For each issue provide:
- Title
- Severity: High / Medium / Low
- Where found
- Why it matters
- Recommended fix

## Output contract drift
- Severity: High
- Where found: [docs/prompts/digest_generation.md](/srv/openclaw-you/workspace/telegram-research-agent/docs/prompts/digest_generation.md#L33), [src/output/generate_digest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_digest.py#L287), [data/output/digests/2026-W12.md](/srv/openclaw-you/workspace/telegram-research-agent/data/output/digests/2026-W12.md#L1)
- Why it matters: the prompt requires exact sections, but the code only checks the opening heading, and the sample digest violates the requested structure entirely. That makes downstream rendering and consistent UX impossible.
- Recommended fix: make digest generation return structured JSON first, validate with schema, then render Markdown/HTML/PDF deterministically.

## Reports have no real evidence model
- Severity: High
- Where found: [src/output/generate_digest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_digest.py#L266), [src/db/schema.sql](/srv/openclaw-you/workspace/telegram-research-agent/src/db/schema.sql#L3)
- Why it matters: the digest only gets topic counts and text excerpts; there are no canonical source ids, permalinks, or evidence references in the output, so "professional research brief" quality is not reachable.
- Recommended fix: store source metadata per post and emit report sections with evidence ids like `S1`, `S2`, linked to an appendix.

## Topic quality is weak for multilingual data
- Severity: High
- Where found: [src/processing/cluster.py](/srv/openclaw-you/workspace/telegram-research-agent/src/processing/cluster.py#L79), [src/processing/detect_topics.py](/srv/openclaw-you/workspace/telegram-research-agent/src/processing/detect_topics.py#L15), [data/output/digests/2026-W12.md](/srv/openclaw-you/workspace/telegram-research-agent/data/output/digests/2026-W12.md#L11)
- Why it matters: clustering uses English stop words only, and topic tokenization is ASCII-only. The result is a huge "Unlabeled" bucket and noisy topic maps.
- Recommended fix: add language-aware tokenization/stopword handling and persist cluster diagnostics.

## Study plan uses global topics, not this week's topics
- Severity: High
- Where found: [src/output/generate_study_plan.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_study_plan.py#L146)
- Why it matters: `_fetch_topics_this_week()` ignores week bounds and just loads top topics overall, so the plan can easily drift from actual weekly signal.
- Recommended fix: filter by current week like recommendations already do.

## Project matching is brittle because keyword storage/consumption disagree
- Severity: High
- Where found: [src/integrations/github_sync.py](/srv/openclaw-you/workspace/telegram-research-agent/src/integrations/github_sync.py#L171), [src/output/map_project_insights.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/map_project_insights.py#L57)
- Why it matters: GitHub sync stores keywords as JSON arrays, while project mapping splits on commas as if it were a CSV string. That hurts FTS queries and relevance scoring.
- Recommended fix: normalize project keywords to one format and parse it centrally.

## Telegram UX feels like a file dump
- Severity: Medium
- Where found: [src/bot/handlers.py](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/handlers.py#L225), [src/bot/handlers.py](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/handlers.py#L355)
- Why it matters: `/digest` and `/study` send raw Markdown chunks; there is no progress indicator, no summary-first response, no "send full report as file" path, and no compact in-chat preview.
- Recommended fix: reply with a short executive summary plus buttons/commands for full Markdown/PDF download.

## Significant duplication in delivery code
- Severity: Medium
- Where found: [src/bot/handlers.py](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/handlers.py#L52), [src/output/generate_digest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_digest.py#L87), [src/output/generate_study_plan.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_study_plan.py#L206)
- Why it matters: chunking, Telegram HTTP calls, and formatting logic are repeated across modules, which will make PDF/file delivery harder to add cleanly.
- Recommended fix: extract a `telegram_delivery.py` module with `send_text`, `send_document`, `send_report_preview`.

## Recommendation de-duplication likely does not work reliably
- Severity: Medium
- Where found: [src/output/generate_recommendations.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_recommendations.py#L75), [data/output/recommendations/2026-W12.md](/srv/openclaw-you/workspace/telegram-research-agent/data/output/recommendations/2026-W12.md#L1)
- Why it matters: the parser expects `### N. ...`, but the sample output uses `## 1. ...`; this breaks last-week label extraction.
- Recommended fix: either schema-validate recommendations or parse from structured JSON rather than Markdown headings.

## Documentation is materially out of date with runtime
- Severity: Medium
- Where found: [docs/spec.md](/srv/openclaw-you/workspace/telegram-research-agent/docs/spec.md#L19), [docs/architecture.md](/srv/openclaw-you/workspace/telegram-research-agent/docs/architecture.md#L130), [src/llm/client.py](/srv/openclaw-you/workspace/telegram-research-agent/src/llm/client.py#L76)
- Why it matters: the docs say OpenClaw gateway; the code calls Anthropic directly. That will mislead future contributors and operators.
- Recommended fix: rewrite docs to match reality and explicitly document the current/non-goals architecture.

## No test suite
- Severity: Medium
- Where found: repository-wide; no `tests/` directory present
- Why it matters: prompt-format drift, SQL query bugs, and parser mismatches are already visible and would be caught cheaply with a few focused tests.
- Recommended fix: add unit tests for prompt loaders, report validators, topic-week queries, and project keyword parsing.

# 4. Improvement Opportunities by Category
## 4.1 Product / UX
- Add a split delivery model: Telegram gets a concise "brief" message; full report is sent as attachment.
- Replace `/run_digest` blocking behavior with "started / ready" messaging.
- Make `/status` product-facing instead of operator-facing by reporting freshness, report availability, and last successful run.

## 4.2 Architecture
- Introduce a typed `ResearchReport` domain object instead of using free-form Markdown as the system contract.
- Separate "data assembly" from "rendering" in output modules.
- Move Telegram delivery into its own boundary; output generators should not call Telegram directly.

## 4.3 Code Quality
- Consolidate duplicated helper functions: week-label, section extraction, chunking, Telegram requests.
- Replace ad hoc dicts with dataclasses or `TypedDict` for cluster/topic/report payloads.
- Make keyword parsing a single shared utility used by GitHub sync and project mapping.

## 4.4 Research Quality
- Pass richer source context into digest generation: source ids, channel, date, view count, topic, excerpt, and maybe confidence.
- Force abstention behavior in `/ask` and report sections when evidence is thin.
- Add minimal validation for generated claims against available sources.

## 4.5 Report / PDF Generation
- Stop treating Markdown as the final contract.
- Introduce structured sections, evidence references, confidence/source quality indicators, and a designed appendix.
- Add a real rendering layer with HTML templates and CSS paged media.

## 4.6 Developer Experience
- Pin dependencies, add a lock strategy, and document system packages needed for rendering.
- Add `make`/script entrypoints for `lint`, `test`, `generate-sample-report`.
- Update docs to reflect actual Anthropic-based runtime and current deployment assumptions.

## 4.7 Reliability / Production Readiness
- Persist run state and failures per pipeline stage.
- Add idempotent job records for digest/recommendation/study generation.
- Track delivery success/failure for Telegram sends and avoid silent partial success.

# 5. Polished PDF Report Upgrade Plan
Must be detailed and implementation-oriented.

Include:
- current state
- target state
- recommended stack / rendering path
- proposed report template structure
- styling recommendations
- rollout phases

## Current state
- Digest generation in [src/output/generate_digest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_digest.py#L277) sends a prompt with topic counts and excerpts, stores raw Markdown in `digests.content_md`, writes `YYYY-WXX.md`, and often sends that Markdown directly to Telegram.
- The sample at [data/output/digests/2026-W12.md](/srv/openclaw-you/workspace/telegram-research-agent/data/output/digests/2026-W12.md#L1) reads like a prototype memo, not a publication-quality brief.

## Why the current output feels raw
- No cover/meta page
- No consistent information hierarchy
- No citation system
- No appendix
- No visual rhythm
- No tables/charts/callouts
- No validation of section structure
- Project notes are appended after the fact by [src/output/map_project_insights.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/map_project_insights.py#L217), which reinforces the "dumped on at the end" feeling

## Target state
- `research JSON -> templated HTML -> styled PDF`
- `report.json`: `meta`, `executive_summary`, `key_findings[]`, `sections[]`, `evidence[]`, `project_relevance[]`, `confidence_notes`, `appendix`
- HTML template: cover page, one-page exec summary, finding cards, evidence callouts, charts/tables, appendix with source list
- PDF: generated artifact plus a shortened Telegram preview and file delivery

## Recommended stack / rendering path
- Keep Python stack.
- Use `jinja2` for HTML templates.
- Use `weasyprint` for HTML->PDF. It fits the repo better than Playwright because this is already a Python/systemd service, not a web app.
- Use `markdown-it-py` only if legacy Markdown compatibility is needed during migration.
- Use `matplotlib` or small SVG generators for deterministic charts.

## Proposed report template structure
- Cover: title, query/scope, week/date range, generated timestamp
- Executive Summary: 3-5 bullets and one "so what"
- Key Findings: 3-6 cards, each with evidence refs
- Market/Theme Sections: each with summary, significance, evidence table
- Notable Evidence: short quoted snippets with source/date/channel badges
- Project Relevance: scorecard per repo, not a long flat list
- Confidence & Risks: what is noisy, under-sourced, or inferred
- Sources Appendix: ordered `S1..Sn` list with metadata

## Styling recommendations
- One serif + one sans pairing, generous whitespace, narrow text measure, muted neutral palette with one accent color.
- Fixed heading scale, shaded callout boxes, zebra-striped data tables, consistent page headers/footers.
- Keep charts sparse and explanatory: topic distribution bar chart, channel activity sparkline, maybe a project overlap matrix.

## Rollout phases
- Phase 1: add `report_schema.py`, generate validated JSON alongside Markdown.
- Phase 2: build a single digest HTML template and render PDF locally.
- Phase 3: add evidence appendix, charts, project scorecards, and Telegram file delivery.
- Phase 4: migrate recommendations/study-plan to the same rendering system and introduce reusable style tokens/templates.

# 6. Prioritized Action Plan
Make a table with columns:
- Priority
- Improvement
- Impact
- Effort
- Why now
- Files / Areas affected

Group into:
- Quick wins (1-2 days)
- Short-term improvements (up to 1 week)
- Medium refactors
- Larger redesigns

| Priority | Improvement | Impact | Effort | Why now | Files / Areas affected |
|---|---|---:|---:|---|---|
| Quick wins | Fix study-plan weekly topic query | High | Low | Current output can be factually off-week | [src/output/generate_study_plan.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_study_plan.py#L146) |
| Quick wins | Parse GitHub/project keywords consistently | High | Low | Project relevance is currently noisier than it should be | [src/integrations/github_sync.py](/srv/openclaw-you/workspace/telegram-research-agent/src/integrations/github_sync.py#L171), [src/output/map_project_insights.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/map_project_insights.py#L57) |
| Quick wins | Add strict post-generation validation for digest/recommendation headings/sections | High | Low | Output contract is already drifting | [src/output/generate_digest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_digest.py#L287), [src/output/generate_recommendations.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_recommendations.py#L240) |
| Quick wins | Stop appending project insights as free text; render a dedicated section in the main report assembly step | Medium | Low | Improves polish immediately | [src/output/map_project_insights.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/map_project_insights.py#L210) |
| Short-term | Introduce `telegram_delivery` module | Medium | Medium | Reduces duplication before PDF/file delivery work | [src/bot/handlers.py](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/handlers.py#L89), [src/output/generate_digest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_digest.py#L114) |
| Short-term | Add source ids/permalinks to stored posts and pass them into report assembly | High | Medium | Required for citations and professional reports | [src/db/schema.sql](/srv/openclaw-you/workspace/telegram-research-agent/src/db/schema.sql#L3), ingestion modules |
| Short-term | Add minimal tests for report contracts and SQL query helpers | High | Medium | Cheap protection against current regressions | output + processing modules |
| Short-term | Rewrite docs to match actual Anthropic architecture | Medium | Medium | Prevents operator confusion | [docs/spec.md](/srv/openclaw-you/workspace/telegram-research-agent/docs/spec.md#L19), [docs/architecture.md](/srv/openclaw-you/workspace/telegram-research-agent/docs/architecture.md#L126) |
| Medium refactor | Create `ResearchReport` schema and generate JSON first | High | Medium | Foundation for HTML/PDF and consistent Telegram previews | output layer + DB |
| Medium refactor | Improve multilingual topic detection and reduce "Unlabeled" | High | Medium | Directly improves report quality | [src/processing/cluster.py](/srv/openclaw-you/workspace/telegram-research-agent/src/processing/cluster.py#L79), [src/processing/detect_topics.py](/srv/openclaw-you/workspace/telegram-research-agent/src/processing/detect_topics.py#L25) |
| Larger redesign | Add Jinja2 + WeasyPrint report renderer | High | Medium/High | Unlocks polished PDF output | new `src/reporting/` package |
| Larger redesign | Add charts/scorecards/evidence appendix | Medium/High | High | Moves product from prototype to finished tool | report templates + asset generation |

# 7. Concrete Refactoring Suggestions
Give at least 10 repo-specific suggestions.
Each suggestion must reference actual code locations.

1. Replace the raw `dict` return contract of `run_digest()` with a typed result object in [src/output/generate_digest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_digest.py#L196).
2. Move `_extract_markdown_section()` into one shared prompt utility; it is duplicated across multiple modules such as [src/output/generate_digest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_digest.py#L60) and [src/output/generate_recommendations.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_recommendations.py#L32).
3. Replace `_split_keywords()` in [src/output/map_project_insights.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/map_project_insights.py#L57) with the JSON-aware parser pattern already used in [src/output/generate_insight.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_insight.py#L35).
4. Add week filtering to `_fetch_topics_this_week()` in [src/output/generate_study_plan.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_study_plan.py#L146).
5. Stop using `del settings` and `get_db_path()` in [src/output/generate_recommendations.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_recommendations.py#L203); accept a `Settings` object consistently like the rest of the code.
6. Extract Telegram send/chunk logic from [src/bot/handlers.py](/srv/openclaw-you/workspace/telegram-research-agent/src/bot/handlers.py#L52), [src/output/generate_digest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_digest.py#L87), and [src/output/generate_study_plan.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_study_plan.py#L206).
7. Add a `report_artifacts` table rather than storing only `content_md` in [src/db/schema.sql](/srv/openclaw-you/workspace/telegram-research-agent/src/db/schema.sql#L51); include `content_json`, `content_html`, `pdf_path`, `status`.
8. Persist cluster diagnostics in the DB instead of keeping them in memory only in [src/processing/cluster.py](/srv/openclaw-you/workspace/telegram-research-agent/src/processing/cluster.py#L93); it will help debugging topic quality.
9. Add schema validation around `complete_json()` consumers in [src/processing/detect_topics.py](/srv/openclaw-you/workspace/telegram-research-agent/src/processing/detect_topics.py#L212) and [src/output/map_project_insights.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/map_project_insights.py#L287).
10. Fix recommendation label extraction in [src/output/generate_recommendations.py](/srv/openclaw-you/workspace/telegram-research-agent/src/output/generate_recommendations.py#L75) so it matches actual/generated heading shapes.
11. Add permalink/source metadata at ingestion time in [src/ingestion/bootstrap_ingest.py](/srv/openclaw-you/workspace/telegram-research-agent/src/ingestion/bootstrap_ingest.py#L46) so the report appendix can cite real sources.
12. Rewrite the stale architecture statements in [docs/spec.md](/srv/openclaw-you/workspace/telegram-research-agent/docs/spec.md#L19) and [docs/architecture.md](/srv/openclaw-you/workspace/telegram-research-agent/docs/architecture.md#L126) to match [src/llm/client.py](/srv/openclaw-you/workspace/telegram-research-agent/src/llm/client.py#L76).

# 8. If I Were Polishing This Project Personally
Write a concise opinionated roadmap:
- what I would change first
- what I would postpone
- what I would avoid overengineering

I would change three things first: make weekly outputs structurally valid, fix the data bugs that poison relevance quality, and add a real report-rendering pipeline. That gives you immediate product lift without rewriting the whole system.

I would postpone bigger retrieval/RAG additions. The repo's current problem is not lack of sophistication; it is weak contracts, weak evidence presentation, and rough delivery. I would also avoid overengineering orchestration frameworks or moving off SQLite right now. The biggest win is turning "LLM wrote some Markdown" into "the system produces a designed research artifact with explicit evidence and stable structure."
