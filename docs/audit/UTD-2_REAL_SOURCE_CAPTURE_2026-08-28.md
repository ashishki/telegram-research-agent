# UTD-2 Real Source Capture — 2026-08-28

Status: source-contract evidence captured and sanitized

A one-shot GitHub Actions job fetched only the three operator-approved public allowlisted sources. No credentials, cookies, authenticated systems, Telegram data, provider calls or delivery were used. The generated fixtures passed `tools/utd_evidence_review.py validate-fixture` before inspection.

Evidence captured at `2026-08-28T17:19:16Z`:

- Calendar: `https://calendar.utdallas.edu/api/2/events?days=14&pp=10&page=1` returned HTTP 200 JSON, `Cache-Control: max-age=600, public`, and an ETag. The sanitized contract proves `event.id`, `event_instance.id`, RFC3339 `start`, explicit `status`, `updated_at`, pagination (`current`, `size`, `total`), date range, topic/audience/department IDs and names.
- ISSO: `https://isso.utdallas.edu/` returned HTTP 200 HTML with `Last-Modified` and cache metadata. The minimized fixture keeps only stable service/navigation concepts relevant to F/J status, employment, financial requirements and international-student success.
- Basic Needs: `https://basicneeds.utdallas.edu/resource-hub/` returned HTTP 200 HTML with `Last-Modified` and cache metadata. The minimized fixture preserves the explicit warning that international students should prefer on-campus resources and consult ISSO regarding nonprofit resources and government-benefit eligibility.

Public fixtures intentionally exclude descriptions, contact fields, email addresses, phone numbers and unrelated page content. The short-lived capture artifact was used only to derive these minimized fixtures.
