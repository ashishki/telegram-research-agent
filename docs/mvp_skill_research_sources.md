# MVP Skill-Assisted Research Sources

Date: 2026-07-11
Status: installed locally; auxiliary research layer

This document records the local Codex skill layer installed from:

```text
https://github.com/artwist-polyakov/polyakov-claude-skills
```

The skills are useful for broad MVP discovery and validation research, but they
do not replace the Radar evidence gates. Raw skill output is not a build-ready
signal until it is normalized, attached to a concrete selected candidate, and
classified as matched external evidence by Radar or an equivalent adapter.

## Installed Skills

Installed under `/root/.codex/skills/`:

| Skill | Current role | Readiness |
|---|---|---|
| `reddit-skill` | Reddit search, subreddit posts, submissions, comments | scripts tested; needs Reddit credentials for live API |
| `x-research` | X/Twitter public discussion research via xAI Grok `x_search` | scripts tested; needs `XAI_API_KEY` |
| `yandex-search-api` | Yandex SERP evidence and Russian search intent | shell syntax checked; needs Yandex Cloud service account config |
| `yandex-wordstat` | Yandex demand/keyword volume and regional demand | scripts tested; needs Wordstat/Yandex Cloud config |
| `telegram-channel-parser` | Public `t.me/s/` channel parsing without MTProto | scripts tested; no API key required |
| `crawl4ai-seo` | Competitor/workaround page crawl and landing comparison | scaffold ready; `crawl4ai`/Playwright not installed yet |

The Codex runtime only discovers newly installed skills on the next user turn.
The files exist now, but future agents should still follow each skill's
`SKILL.md` before running its scripts.

## Evidence Boundary

| Source | Default evidence role | Gate rule |
|---|---|---|
| Telegram channel parser output | `context_only` unless normalized as source observation | Public channel commentary cannot satisfy Radar demand gates by itself |
| Reddit API output | possible matched external evidence | Must be same ICP/pain/candidate, with public URL and query provenance |
| X research output | lower-confidence corroboration | Never satisfies gates by itself |
| Yandex Search API output | possible matched search-demand evidence | Must match candidate intent, not adjacent/SEO noise |
| Yandex Wordstat output | demand context or possible search-demand support | Volume alone is not WTP; intent must be verified through SERP |
| crawl4ai competitor pages | possible matched competitor/workaround evidence | Must be bounded to explicit URLs/domains and carry ICP/pain relevance |

Market/business context remains `context_only`. No skill output may upgrade a
candidate to `build` or `focused_experiment` without matched external evidence
from at least two independent source types, per Radar gates.

## Full MVP Research Pass

Use this order for a broad, bounded run:

1. Export Telegram Research Agent opportunity seeds.
2. Run Radar with the production source bundle.
3. Read Radar's selected candidate list, validation query pack, missing
   evidence, and decision-change action.
4. Use skills only to answer the Radar query pack or fill specific missing
   evidence categories.
5. Store skill artifacts outside git, preferably under the skill cache or
   ignored runtime output.
6. Summarize skill findings as:
   - query;
   - source;
   - URL;
   - excerpt/snippet;
   - whether it matches the same ICP, pain, workaround, and candidate;
   - role: `matched_external`, `context_only`, `negative`, or `irrelevant`.

Do not run unbounded scraping, full archive backfills, write-capable Reddit
actions, or production config changes from this workflow.

## Prompt Shape

When asking an LLM to synthesize the final three candidates, use a gate-aware
request:

```text
Select the top 3 MVP candidates for this operator from the attached Radar
dossier and skill-assisted research artifacts.

Rules:
- Treat Telegram seeds and market/business context as context_only.
- Do not count unmatched external research as evidence.
- Do not count X/Twitter as a gate-satisfying source by itself.
- For each candidate, separate matched evidence, context-only evidence,
  negative evidence, missing evidence, and operator fit.
- Prefer narrow Python/LLM/workflow/evaluation/knowledge-ops products.
- Return build/focused only if Radar gates are satisfied; otherwise use
  investigate or reject.
- Include the next repeatable validation query for each candidate.
```

## Verification

Installed-skill checks run on 2026-07-11:

```bash
cd /root/.codex/skills/reddit-skill && bash scripts/tests/run.sh
cd /root/.codex/skills/telegram-channel-parser && bash scripts/tests/run.sh
cd /root/.codex/skills/x-research && bash scripts/tests/run.sh
cd /root/.codex/skills/yandex-wordstat && bash scripts/tests/run.sh
cd /root/.codex/skills/yandex-search-api && bash -n scripts/*.sh
cd /root/.codex/skills/crawl4ai-seo && python3 scripts/doctor.py
```

`crawl4ai-seo` doctor currently reports scaffold-only/partial readiness because
`crawl4ai` and Playwright are not installed in the skill environment.
