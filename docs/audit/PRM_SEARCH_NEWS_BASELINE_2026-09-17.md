# Personal Search And News Audit Baseline

Date: 2026-09-17
Evidence: inspected code, public GitHub metadata and synthetic local checks.
Audited code SHA: `cee8baae3b8a41f571bd689f2dadf7e6e981863f`, default branch master.
This record imports prior audit observations; task registration did not rerun
product tests, invoke a provider/reviewer or observe production.

## Snapshot and isolation

[CI run 35215290144](https://github.com/ashishki/telegram-research-agent/actions/runs/35215290144)
passed on the audited SHA. Tracked code was unchanged during the audit. Relevant
merged PRs: #4 intent-first archive answers and #3 retrofit. No open PR was
returned by the closing public API check.

Local checks used a tracked snapshot outside the repository, empty environment,
no credentials, disposable SQLite fixtures, fake model/Telegram, disabled pytest
plugin autoload and Python I/O guards. No production archive was copied or read.
73 focused tests passed in 4.96 s; 18 actions/replay/profile/callback tests passed
in 16.03 s. These are regression observations, not performance or UX benchmarks.

The source-of-truth receipt copied into the project is
[synthetic audit results](../../evals/prm_search_news/audit_baseline_2026-09-17.json).
Its labels are model-authored and not independent human gold. They are prior
observations, not a new release gate.

## Confirmed findings and task mapping

| Finding | File/symbol and observation | Task |
|---|---|---|
| Archive intent has improved | prm.routing and PersonalResearchAssistant.answer: archive agent-evals/applicability-now stays archive-scoped without an implicit project | Preserve in PRM-SN-1C |
| Incorrect visible citation can pass | claim_ledger removes URL while matching lexical evidence; citation_precision checks HTTPS refs, not the displayed claim/source relation | PRM-SN-1A |
| Incomplete checking appears successful | Short factual sentence extracted zero claims; unsupported 11th sentence escaped the default limit | PRM-SN-1A |
| False facts pass synthesis | Price 20→900, negation and actor mutations passed; _call_and_verify rejects only unsupported_claim_rate >0.6 plus other structural checks | PRM-SN-1B |
| Final verification is diagnostic | application records final verification without using it as a publication decision; threshold tightening alone misses lexical false positives | PRM-SN-1A/1B |
| Mixed request dispatch fails | _apply_route_boundaries leaves status ok; prm_handlers iterates absent action_codes after sending a boundary answer | PRM-SN-1C |
| Follow-up mis-scopes | Previous topic/directness retained after a new topic; “за неделю” failed to set the actual date window | PRM-SN-2A |
| Save lacks exact item binding | Free-text save-second becomes a generic action; preview may not show the intended full proposal | PRM-SN-2B |
| Refresh health is incomplete | Refresh CLI/timer exist; Telegram refresh is dry-run; status does not show full last-attempt/partial/index state | PRM-SN-2C |
| External watch already exists | collector/profile/store/selection/delivery are implemented; UTD ASK remains a preview, general web answering is not connected | PRM-SN-3/4 |
| Delivery can lose or duplicate | apply_success commits the source change before send; next identical poll has no pending candidate. Two concurrent sends produced one receipt | PRM-SN-5A |
| Confirmation effect is misleading | UTD preview says monitoring is off, whereas the historical timer permission activates polling/delivery after confirmed profile | PRM-SN-5B |

### Reproduction input for the first phase

Synthetic evidence at `https://example.invalid/source-a`:

> Orion service does not retain private messages and costs 20 dollars per month.

Use a fake synthesis result and inspect actual returned text, not only metrics:

- correct price sentence;
- same sentence with a different URL, or with no displayed URL;
- price 900 instead of 20;
- retention assertion instead of its negation;
- a different subject;
- short factual “Цена 900 долларов.”;
- ten apparently supported sentences plus an unsupported eleventh.

The receipt gives exact observed answers and acceptance flags. P1-A covers
citation integrity/completeness; correct-URL semantic mutations remain P1-B.
A refusal/meta line must not be misclassified as a factual failure. Keep paired
useful positives; a system that refuses everything is not acceptable.

## Existing evaluations and unknowns

The advisory UX judge from 2026-09-03 evaluated 50 selected cases / 200 turns:
0 deterministic case failures, 44 below score floor, naturalness 2.62/5,
low cognitive load 2.98/5, safety boundary 4.98/5, human_review_count=0.
See PRM_PRODUCT_UX_JUDGE_2026-09-03.md. This is not a current independent baseline.

August retrieval holdouts use generated/silver labels. They do not justify
assuming a new embedding backend improves current useful answers. Use existing
FTS/sidecar/QA tools and measure the actual loss before adding infrastructure.

Current deployed SHA, flags/providers, archive/index freshness, UTD profile
confirmation, service state, actual deliveries, cost/latency and owner usefulness
were not observed. Historical receipts do not close these gaps. Planned metrics,
28 scenarios and independent holdout rules are in
[the evaluation plan](../PRM_SEARCH_NEWS_EVAL.md).

No Google comparison, real news examples, live Telegram trial or independent
human labels were created by the audit. Task registration and a successful docs
validator are not product implementation or a completed deep review.
