# Implementation pass — 2026-10-07

Owner sequencing: ADR-015. No tests, test tiers, validators, provider diagnostics
or independent review have been run in this pass. No dependency was installed.
No server, worker, scheduler, account, migration or deployment was activated.
Engineering status is implementation_unverified, not accepted/local_verified.

Code now covers the local PAI-10..25 components:

| Cards | Added implementation |
|---|---|
| 10–11 | Explicit composition, credential/endpoint binding, HTTP model transport, independently authorized bounded history, canonical source-bound archive synthesis |
| 12–13 | Brave discovery, DNS-pinned source reads, exact commit GitHub reads, persistent research gather/synthesis/verification checkpoints |
| 14–15 | Selected source hooks, structured editorial, immutable PostgreSQL Brief manifests/documents, visible version bindings, restricted subprocess exports and authenticated loopback reader |
| 16–19 | Graph OAuth/PKCE, one-use state, encrypted vault, account identity, refresh/disconnect, mail delta/page state, calendar/contacts, minimal paged Canvas and academic conflict/local completion |
| 20–22 | Exact action preview/edit/confirmation/receipt, Graph executor, memory previews/tombstones/dependencies, media download/extract/STT/vision and actual temporary-file cleanup |
| 23–25 | Versioned usage/tariffs, scoped caches, health/epoch/drain/kill, private PostgreSQL dump/restore and monotone receipt/tombstone transfer |
| 26 | Candidate inventory code, prepared per-card suites and ten scenario/load-recovery entrypoints; execution and independent acceptance deferred |

CLI and one-role service entrypoints select target/config explicitly. Service
examples are inactive. Restores disable egress and drain intake; old unknown
attempts never authorize resend. Historical SQLite archive/watch sender paths
were retained. No Redis/vector/archive migration was introduced.

Remaining implementation/acceptance obligations are deliberately not hidden:
the 69 individually named requirement cases still need full binding and scope
assessment; all new cases are unexecuted. Production storage selection,
actual provider/account access, visual/operator evidence and measured RPO/RTO
remain gates. Metadata-only mail cannot establish body-level reply obligations;
the runtime produces an exact additional selected-message scope request.
Canvas requires an institutional reference before a live path. Provider
reconciliation without authoritative lookup remains unknown.

Publication commits: d4d45a2 (initial composition) and 19477b2 (source/media/
recovery components), plus subsequent integration/doc commits in this branch.
Neither commit has independent review. Mimo stays 23/30 consumed; no new call.

Prepared validation is under tests/test_pai_*.py and tools/run_pai_acceptance.py.
PAI-27..29 packages below record exact prerequisites; they do not claim canary,
deployment or owner acceptance. PAI-30/31 conditions are unmeasured, so no
conditional infrastructure change or not_needed verdict is manufactured.

Primary API sources used during implementation: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
[OpenAI transcription](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create),
[Brave Web Search](https://api-dashboard.search.brave.com/app/documentation/web-search/codes),
[GitHub commits](https://docs.github.com/en/rest/commits/commits),
[GitHub contents](https://docs.github.com/en/rest/repos/contents),
[Graph delegated OAuth](https://learn.microsoft.com/en-us/graph/auth-v2-user),
[Graph delta](https://learn.microsoft.com/en-us/graph/api/message-delta?view=graph-rest-1.0),
[Graph sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0),
[Graph event creation](https://learn.microsoft.com/en-us/graph/api/user-post-events?view=graph-rest-1.0),
[Graph event update](https://learn.microsoft.com/en-us/graph/api/event-update?view=graph-rest-1.0),
[Canvas assignments](https://developerdocs.instructure.com/services/canvas/resources/assignments).
