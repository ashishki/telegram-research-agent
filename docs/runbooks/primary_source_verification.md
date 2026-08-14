# Primary-Source Verification Runbook

Status: proposed PRM-MAT runbook. No live fetch is authorized by this document.

Supported initial classes are GitHub repositories, approved official documentation/vendor announcements, arXiv metadata and classification-only independent sources. Telegram remains discovery context. Live operation requires separate approval for fetch, trust policy, approved host/source relation and budget. `www.*` is never proof of official status.

The implementation must enforce HTTPS, DNS/IP/SSRF controls, redirect limit, content-type allowlist, response-size/time limits, bounded retries and cache TTL/fetched-at/content hash. It never executes third-party code. Cache is separate from canonical Telegram archive. Reject/timeout/unsupported content returns partial or verification-required result with a visible boundary, not an inferred claim. Store no raw archive corpus in the cache or public receipts.
