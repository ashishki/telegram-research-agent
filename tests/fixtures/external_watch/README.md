# UTD external-watch sanitized fixtures

This directory is reserved for **manually captured and sanitized** UTD source samples used by UTD-2/UTD-3 review.

Allowed fixture envelope: `utd_source_fixture.v1` with source `calendar`, `isso`, or `basic_needs`; kind `localist_json` or `html_excerpt`; `contains_private_data=false`; `sanitized=true`; a canonical public URL; and minimized content containing only fields needed to prove source identity, recurrence/status/update semantics, deadline/resource fields, or eligibility.

Do not store cookies, Authorization headers, Set-Cookie headers, email addresses, student records, personal names, Telegram data, credentials, full unrelated pages, or raw browser/session exports here. Capture is manual/offline; no collector or web job is enabled by this directory.
