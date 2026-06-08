# MVP Weekly Radar Bridge

Status: Active production bridge
Date: 2026-06-08

## Purpose

Telegram Research Agent does not choose the weekly MVP by itself. It exports
high-signal Telegram opportunity seeds, then delegates market validation and
MVP synthesis to `Demand-to-MVP-Radar`.

The split is intentional:

- Telegram Research Agent finds and scores relevant Telegram signals.
- Demand-to-MVP Radar collects broader demand sources and checks whether the
  same pain exists outside Telegram.
- The Telegram bot delivers the final Radar artifact back to the operator as a
  Telegraph article plus a copyable Markdown document.

The next Radar iteration should treat this artifact as a Candidate Dossier
unless the source gates clearly support a build-ready recommendation.

## Runtime Flow

1. `src/main.py mvp-weekly` exports opportunity seeds from recent Telegram
   evidence into `data/output/opportunity_seeds/`.
2. The pipeline runs Radar with:
   - `RADAR_REPO_PATH`
   - `RADAR_PYTHON`
   - `DMR_MVP_SOURCE_CONFIG`
   - `DMR_DATA_DIR`
   - `DMR_REPORT_DIR`
   - `DMR_LLM_PROVIDER`
   - `DMR_LLM_MODEL_MVP_WEEKLY`
3. Radar imports Telegram seeds, collects configured external sources, applies
   source-mix and operator-fit gates, and writes Markdown/JSON under
   `Demand-to-MVP-Radar/reports/mvp_of_week/`.
4. Telegram Research Agent publishes the Markdown report to Telegraph.
5. The bot sends:
   - short Telegram notification;
   - Telegraph URL;
   - source-mix summary;
   - Markdown document fallback.

## Source-Mix Contract

Telegram seeds are a hypothesis layer. The weekly MVP report must disclose:

- Telegram seed evidence count;
- external evidence count;
- external source types;
- skipped sources, if any;
- source errors, especially missing credentials.

Radar's active weekly source bundle includes:

- RSS/HN;
- GitHub public search;
- Stack Exchange;
- SERP/SerpApi;
- YouTube Data API;
- Product Hunt;
- Reddit official API.

Confident recommendations are gated in Radar. Telegram-only candidates cannot
become `focused_experiment`.

## Credentials

Primary Telegram Research Agent secrets remain in:

```bash
/srv/openclaw-you/.env
```

Demand-to-MVP Radar live-source credentials should live in:

```bash
/etc/demand-mvp-radar.env
```

The weekly systemd service loads both files:

```ini
EnvironmentFile=/srv/openclaw-you/.env
EnvironmentFile=-/etc/demand-mvp-radar.env
```

Required/optional Radar live-source env vars:

| Variable | Purpose |
|---|---|
| `SERPAPI_API_KEY` | Search intent via SerpApi |
| `GITHUB_TOKEN` | Optional higher GitHub public search quota |
| `YOUTUBE_API_KEY` | YouTube search/tutorial demand |
| `PRODUCT_HUNT_TOKEN` | Product Hunt launch/competitor context |
| `REDDIT_CLIENT_ID` | Reddit API app id |
| `REDDIT_CLIENT_SECRET` | Reddit API app secret |
| `REDDIT_USER_AGENT` | Reddit API user agent |
| `STACK_EXCHANGE_KEY` | Optional Stack Exchange quota key |

Do not commit real values or paste them into reports/logs.

## Commands

Dry-run without Telegram delivery:

```bash
python3 src/main.py mvp-weekly --no-deliver
```

Manual delivery run:

```bash
python3 src/main.py mvp-weekly
```

Export only Telegram seeds:

```bash
python3 src/main.py export-opportunity-seeds --days 7 --limit 80
```

## Expected Operator Output

The owner should receive a message shaped like:

```text
MVP of the Week 2026-W22 is ready.
<selected title>
Status: investigate, score 64/100.
Recommendation: revisit_with_evidence_gap.
Seeds exported: 80.
Source mix: readiness=credential_limited; telegram=80; external=119; external_types=github_public, rss, stack_exchange; reddit=missing_credentials; missing_credentials=reddit_demand_live; source_errors=serp_search_intent_live, youtube_creator_tutorial_demand_live.
https://telegra.ph/...
```

The source-mix line is a truth surface: it shows whether the idea was validated
beyond Telegram or still needs credentials/external evidence. `readiness` is
`telegram_only`, `externally_corroborated`, or `credential_limited`.

## Candidate Dossier Contract

Radar should not present every selected candidate as a build-ready MVP. The
reader-facing artifact should use one canonical final status:

- `build` - evidence is strong enough to build now.
- `focused_experiment` - evidence supports a narrow 7-day experiment.
- `investigate` - candidate is interesting but missing evidence remains.
- `reject` - source mix, operator fit, or risk makes it not worth pursuing.

The Markdown and JSON must agree on the same status. A report must not say the
Decision Gate passed and later say the candidate was downgraded.

Expected dossier shape:

```text
# Candidate Dossier: <title>

Status: investigate
Decision: Run one validation experiment before building.
Confidence: low

## Why This Candidate
## Source Mix
## Evidence
## Missing Evidence
## Next Experiment
## Kill Criteria
## Operator Fit
## Anti-Complexity Guardrail
```

## Cross-Repo AI Handoff

Radar implementation work happens in:

```text
/srv/openclaw-you/workspace/Demand-to-MVP-Radar
```

Primary files for the next Radar tasks:

- `demand_mvp_radar/mvp_weekly.py`
  - `run_mvp_of_week`
  - `_synthesize_or_render`
  - `_apply_synthesis_gates`
  - `_append_gate_notes`
  - `_append_report_quality_sections`
  - `_render_report`
- `tests/test_mvp_of_week.py`
- `config/mvp_weekly_sources.json`
- `reports/mvp_of_week/` for generated local outputs only; do not commit private
  generated reports unless a task explicitly asks for sanitized fixtures.

Run Radar tests from the Radar repo:

```bash
cd /srv/openclaw-you/workspace/Demand-to-MVP-Radar
.venv/bin/python -m pytest tests/test_mvp_of_week.py
```

Detailed Telegram-side and Radar-side tasks live in
`docs/report_quality_roadmap.md` as `RADAR-1` through `RADAR-4`.
