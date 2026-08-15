# PRM Primary Source Verification

Status: active
Date: 2026-08-15

Module: `src/assistant/primary_source_verification.py`

The first verification slice supports gated fetches for:

- GitHub repositories;
- official documentation;
- official vendor announcements;
- arXiv/research metadata.

Live fetch is disabled unless both operator approval fields are true and runtime
`allow_live_fetch=True` is supplied. Tests use fake transport.

Safety controls:

- HTTPS only;
- no credentials in URL;
- private/loopback/link-local/reserved IP rejection;
- DNS/IP safety check for live fetch;
- redirect limit;
- timeout;
- response-size cap;
- content-type allowlist;
- fetched-at timestamp;
- content hash;
- private gitignored cache TTL;
- no third-party code execution.

`www.*` is not automatically official. Official relation must be explicit.
