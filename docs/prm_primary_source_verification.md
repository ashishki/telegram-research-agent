# PRM Primary Source Verification

Status: active
Date: 2026-08-15

Module: `src/assistant/primary_source_verification.py`

The first verification slice supports gated fetches for:

- GitHub repositories;
- official documentation;
- official vendor announcements;
- arXiv/research metadata.

This implementation is fixture-only: live fetch has no callable runtime path.
Tests use declarative fixture responses, and only an explicitly approved
trusted-host list (or built-in GitHub/arXiv classification) can select one.

Safety controls:

- HTTPS only;
- no credentials in URL;
- private/loopback/link-local/reserved IP rejection;
- response-size cap;
- content-type allowlist;
- fetched-at timestamp;
- content hash;
- optional caller-supplied fixture cache TTL; it is never proof for claims;
- no third-party code execution.

`www.*` is not automatically official. Official relation must be explicit.
