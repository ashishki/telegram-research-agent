# UTD-2 Public Source Contract Capture — 2026-08-28

Status: externally_verified_public_capture_with_residual_transport_gate
Scope: preparation only; no collector, timer, Telegram send, provider call, credentials, cookies, student records, or production database changes.

## Purpose

Capture enough current, public, primary-source evidence to remove generic-university assumptions from the future UTD watch adapters while preserving the UTD-P0/ADR-008 rule that real polling and delivery require later explicit gates.

## Calendar / Localist

Primary surface: `https://calendar.utdallas.edu/` (Comet Calendar, Localist).

Observed on the live public surface on 2026-08-28:

- The calendar is explicitly powered by Localist.
- Public filtering dimensions include Event Types, Target Audience, Topic, departments, groups, places, keywords/tags, date ranges, and recurring-event controls.
- Registrar has its own public department calendar and exposes academic deadline/change material suitable for the `program` source family.
- Career Center has its own public department calendar suitable for the `career` source family.
- Information Technology/engineering calendar entries include AI/agent/software-development events suitable for the `ai` source family.
- Event detail pages expose title, date/time, location or virtual status, department, target audience, website, description, and accessibility/contact metadata.
- A public UTD-adjacent open-source scraper independently references the Localist endpoint `https://calendar.utdallas.edu/api/2/events`; this is evidence of the expected transport endpoint, not approval to poll it from production.

Material fields for a future adapter:

- stable event identity and occurrence/instance identity;
- title;
- starts/ends and all-day semantics;
- event status/cancellation/reinstatement signal;
- updated timestamp when available from transport JSON;
- location / virtual state;
- department/group;
- target audience;
- event type/topic/tags;
- canonical event URL;
- recurrence/instance information.

Safety contract:

- disappearance from one fetch MUST NOT be treated as deletion/cancellation;
- recurring instances MUST retain event identity plus occurrence identity;
- audience eligibility MUST be explicit; no spouse/family inference from generic public access;
- past events and duplicates are negative controls;
- transport 429/timeout/schema drift become source-health failures, never content changes.

Residual gate before UTD-4 implementation:

A sanitized raw Localist JSON sample plus observed HTTP cache/rate-limit/content-type headers is still required. The current capture intentionally does not claim those transport details because this run did not start a source poller or persist raw network payloads.

## ISSO / International Center

Primary public surfaces:

- UT Dallas International Students / International Center public site;
- UT Dallas 2026 catalog International Student Services Office description;
- UT Dallas Atlas ISSO service catalog;
- Comet Calendar ISSO/International Center event pages.

Current source facts relevant to the contract:

- ISSO is the primary immigration-services resource for UT Dallas international students and covers F/J immigration processing, SEVIS reporting and advising.
- Public UTD material explicitly includes international-student orientation, immigration services, and spouse/family programming in the broader International Center ecosystem.
- Calendar event pages can state target audiences explicitly (for example prospective/international students), which is the required eligibility signal for event matching.

Material change fields for future ISSO HTML/page adapters:

- canonical page URL;
- page title/section heading;
- visible `last updated` / revised date when present;
- deadline/effective date text;
- requirement/action text;
- eligibility/audience text;
- linked official form/service destination;
- material advisory status.

Safety contract:

- immigration claims require a current official UTD page and, where the claim is federal-law dependent, the primary government source before authoritative answer/delivery;
- text supplied by source pages is untrusted data and never executable prompt/instruction text;
- cosmetic navigation/layout changes are ignored;
- a removed paragraph is not treated as rescission until corroborated by the current canonical page or replacement notice.

## Basic Needs Resource Center

Primary public surfaces:

- `https://basicneeds.utdallas.edu/`
- `https://basicneeds.utdallas.edu/resource-hub/`
- `https://basicneeds.utdallas.edu/events/`

Current source facts relevant to the contract:

- BNRC states that enrolled undergraduate, graduate and international students are eligible for BNRC services.
- The Resource Hub includes a visible last-edited date and explicitly warns that off-campus resources can have eligibility requirements and that international students should consult ISSO regarding nonprofit/government-benefit eligibility.
- The Resource Hub tells users to verify details with the corresponding provider/site.
- BNRC event pages include future/announced-event states where details may be incomplete; these must remain `ambiguous` until concrete date/eligibility data exists.

Material fields for future adapter:

- canonical page URL;
- last-edited/revised timestamp if visible;
- service/event title;
- enrolled-student eligibility wording;
- international-student caveat;
- cost/free wording;
- date/time/location where applicable;
- application or resource link;
- explicit disclaimer/caveat text.

Safety contract:

- never convert a resource listing into an unsupported savings/value claim;
- international-student eligibility for government/off-campus benefits remains unknown unless explicitly supported;
- `free` may be stated only when the primary page itself says it;
- stale or incomplete event details do not notify as confirmed opportunities.

## Source-family routing

- `program`: Registrar / official academic calendar pages first.
- `career`: Career Center calendar/pages first.
- `ai`: UTD department/research/IT/engineering calendar pages when event relevance is explicit.
- `isso`: ISSO / International Center official pages first.
- `benefits`: BNRC official pages first; off-campus linked resources remain secondary and eligibility-bounded.
- `spouse_family`: only entries whose primary UTD source explicitly states spouse/family/guest eligibility.

## Readiness decision

This capture is sufficient to define field allowlists, canonical-source families, change semantics and safety negatives. It is NOT sufficient to mark `live_source_samples_verified=true` in `evals/external_watch/manifest.v1.json`, because raw Localist JSON plus transport headers and a minimized raw ISSO/BNRC HTML fixture have not been captured into the repository. Therefore UTD-4 remains blocked and no collector was created.
