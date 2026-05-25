# MVP Weekly Radar Bridge

Status: Active production bridge
Date: 2026-05-25

## Purpose

Telegram Research Agent does not choose the weekly MVP by itself. It exports
high-signal Telegram opportunity seeds, then delegates market validation and
MVP synthesis to `Demand-to-MVP-Radar`.

The split is intentional:

- Telegram Research Agent finds and scores relevant Telegram signals.
- Demand-to-MVP Radar collects broader demand sources and checks whether the
  same pain exists outside Telegram.
- The Telegram bot delivers the final `MVP of the Week` artifact back to the
  operator as a Telegraph article plus a copyable Markdown document.

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
Recommendation: revisit_with_evidence_gap, score 64/100.
Seeds exported: 80.
Source mix: telegram=80; external=119; external_types=github_public, rss, stack_exchange; source_errors=serp_search_intent_live, youtube_creator_tutorial_demand_live.
https://telegra.ph/...
```

The source-mix line is a truth surface: it shows whether the idea was validated
beyond Telegram or still needs credentials/external evidence.
