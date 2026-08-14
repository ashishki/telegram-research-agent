# PRM Mature Acceptance Plan

Status: proposed. Fixtures, local tests, manual runtime receipts and real operator evidence are distinct.

| Area | Required proof | Stop-ship |
| --- | --- | --- |
| Routing | 50 holdouts; workflow target 0.90, clarification <=0.15, unsafe chat 0 | conflicting workflow/date/project selection |
| Retrieval | known/semantic recall, citation precision, stale/no-answer, reacted recall | stale or citationless factual claim |
| Personalization/project | bilingual lens and project-selection comparisons | lens hard-filter or unapproved project action |
| Generation | DTO validation and human mobile review | unsupported claim/technical leakage |
| Tool/write | restart, replay, cancellation, expiry, idempotency, isolation | write before confirmation |
| Verification | class, SSRF, cache and partial-result fixtures | untrusted fetch bypass |
| Operations | freshness isolation, backup/restore, budgets | hidden stale index/restore failure |
| Live and four-week | approved bounded smoke then operator evidence | thresholds claimed without labels |

Focused tests prove a task; integration tests trace the normal path; security/property tests protect identity, writes and network boundaries; full suite is opt-in. Mature completion requires approved gates plus real evidence and is not established today.
