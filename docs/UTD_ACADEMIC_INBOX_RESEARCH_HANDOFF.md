# UTD Academic Inbox: Research Handoff

Status: research brief only — **not** an approval to connect an account, poll a
new source, store private records, start a timer, or send a notification.

Last verified: 2026-09-18

## Purpose

This brief gives a future research agent a bounded way to investigate an
optional **Academic Inbox** for one operator. The intended outcome is a calm,
actionable view of university obligations and opportunities, not a second
student-information system and not an autonomous agent.

The user problem is:

> Combine relevant university email, Canvas deadlines and selected UTD public
> information; classify it; show what needs action; rank it by importance and
> deadline; and deliver only requested reminders.

The desired categories are:

- instructor/course communications;
- new coursework, assignments and exams;
- opportunities: scholarships, mentoring, research, jobs and applications;
- administration: housing, insurance/benefits, immigration/ISSO,
  registration and payment; and
- other or uncertain, which must remain visible rather than be silently
  discarded.

The future feature is separate from the current Personal Telegram Research
Memory archive. It must not re-purpose the private Telegram archive, its
canonical database, or existing UTD watch consent as consent to inspect email
or Canvas.

## Current repository truth

No mail or Canvas connector exists in this repository. No OAuth client,
credential store, personal-email parser, Canvas API client, Academic Inbox
database, timer, profile type, or notification policy is implemented.

The nearest existing components are useful boundaries, not a completed
integration:

| Existing component | What it does today | What it does **not** authorize or provide |
| --- | --- | --- |
| `src/external_watch/collector.py` | Polls a small allowlist of public UTD sources only after a confirmed UTD profile permits collection. | OAuth, authenticated requests, email, Canvas, or a general fetcher. |
| `src/external_watch/fetch.py` | Enforces HTTPS, host allowlisting, no redirects/private addresses, content-type and response-size limits for public sources. | Reuse with a private OAuth host or arbitrary redirect URI without a separate security design and tests. |
| `src/external_watch/store.py` | Keeps derived public-watch state in a sidecar and records source health and changes. | Storage of raw emails, attachments, grades, submissions, or Canvas payloads. |
| `src/external_watch/delivery.py` | Applies delivery switches, profile checks, quiet hours, caps and idempotency receipts. | Permission to alert from a new source; the new source needs its own consent and policy. |
| `src/assistant/utd_profile.py` | Creates confirmation-gated scope for the current public UTD watch. | A mailbox/Canvas permission grant or a durable Academic Inbox profile. |

The repository's current UTD watch is source-bounded and confirmation-gated;
its detailed security boundary is [ADR-008](adr/ADR-008-confirmed-external-watch.md).
The operating model says that an unconfirmed profile must fail closed. This
research brief does not change that status.

## Source inventory and provenance policy

Every normalized item needs an immutable source reference, a retrieval time,
an observed freshness value and a link that a person can open. A convenience
aggregator may help discover an item; it must not silently become the authority
for a high-stakes deadline.

| Candidate source | Appropriate use | What is known | Required research before adoption |
| --- | --- | --- | --- |
| UTD Nebula API | Public campus context: academic calendar, events, course catalog/context, rooms and similar public data. | Nebula Labs documents a central API and tools that scrape, parse and upload several UTD public datasets. Access to its production API requires a provisioned API key. | Confirm endpoint inventory, data licence/terms, rate limits, update cadence, outage behavior, canonical UTD URL per record and API-key handling. Treat it as a secondary discovery source until every notification has primary-source evidence. |
| Official UTD pages already used by the watch | Public calendar, ISSO and basic-needs changes within the existing explicit scope. | The current collector has three fixed official hosts and safe public-fetch controls. | Do not widen its allowlist merely because an Academic Inbox exists. Any new public source needs the ADR-008-style source contract, fixtures and approval. |
| UTD Canvas | Personal course list, published assignments, due/lock dates, announcements and calendar events. | UTD moved academic courses to Canvas for Fall 2026. Canvas exposes a REST API authenticated with OAuth2; institution-controlled developer keys can restrict endpoints to read-only scopes. | Ask UTD eLearning/IT whether a student-facing personal integration is permitted and how a developer key is issued/enabled. Confirm the actual Canvas domain, supported redirect URI, token lifetime, minimal `GET` scopes and relevant records. No personal access token is to be pasted into chat or committed. |
| University email | Instructor, departmental, administrative and opportunity messages. | The provider is not confirmed in this repository. Microsoft Graph and Gmail both use OAuth rather than a password. | First identify the actual provider. Obtain a privacy review of the exact delegated read scope, university consent requirements, retention and whether access can be limited to a dedicated folder/mailbox. Never assume a provider from an email address. |

Primary-source rule:

1. Canvas is the authority for a Canvas assignment's current due date.
2. An explicitly dated official university message may support an administrative
   deadline, with a link/message reference and timezone.
3. Nebula or another public aggregator can create a discovery candidate, but a
   user-facing urgent alert must include the original UTD/Canvas source when
   one is available.
4. Conflicting dates are not merged. Surface the conflict, identify sources and
   ask the user to verify.

## Minimum viable read-only scope

The first product slice should be intentionally small:

```text
Canvas assignments + Canvas calendar/events
      + selected university mail
      -> normalized action candidates
      -> deterministic category, deadline and priority
      -> private preview
      -> explicitly confirmed reminder policy
      -> Telegram delivery with receipt
```

It must not read grades, submissions, peer data, course files, email
attachments, all historical mail, housing records, immigration case records or
financial account data. It must never submit coursework, change a Canvas item,
mark email as read, create mail rules, apply for an opportunity, register for a
course, or contact a university office.

### Mail data minimization

Even a delegated `Mail.Read` permission can be broad at the provider level.
The application-level filter is not equivalent to a provider-enforced limited
scope. Prefer, in this order:

1. a user-maintained dedicated university mailbox, if available;
2. a user-created folder/label containing only university messages, with a
   clear explanation if the provider scope still technically covers the
   mailbox; or
3. a narrowly documented sender/domain and date-window query, followed by a
   reviewable preview before persistence or notifications.

Retrieve headers and the smallest text fields required to classify a message.
Do not fetch attachments by default. Do not retain raw bodies when a
normalized action, content hash, source ID and bounded redacted excerpt are
sufficient.

### Canvas data minimization

Request only read endpoints required for:

- current/enrolled course identity;
- assignment title, URL, due/availability/lock time and submission state when
  it is necessary to avoid a false reminder; and
- course calendar events and announcements.

Do not request or persist grades, grading comments, submissions, roster data,
files or discussion text in the first slice. An OAuth developer key must
enforce exact `GET` endpoint scopes where the institution supports them.

## Normalized item contract

Before building any provider adapter, write synthetic fixtures against one
provider-neutral contract. The contract is a proposal, not a production schema:

```json
{
  "schema_version": "academic_inbox_item.v1",
  "item_id": "stable-hash-or-provider-id",
  "source": "canvas|mail|utd_nebula|official_utd",
  "source_kind": "assignment|calendar_event|announcement|mail|opportunity|administrative_notice",
  "source_url": "https://…",
  "source_ref": "provider record ID; never an access token",
  "title": "bounded user-facing title",
  "course_or_sender": "bounded label",
  "category": "coursework|instructor|opportunity|administration|other",
  "administration_area": "housing|benefits|immigration|registration|payment|null",
  "action": "submit|read|register|apply|respond|verify|null",
  "deadline_at": "RFC 3339 timestamp or null",
  "deadline_precision": "provider_exact|explicit_text|inferred|unknown",
  "timezone": "America/Chicago|…|null",
  "priority": "critical|high|normal|low",
  "priority_reasons": ["deadline_within_24h"],
  "confidence": "high|medium|low",
  "observed_at": "RFC 3339 timestamp",
  "content_hash": "sha256:…",
  "dedupe_key": "stable non-secret fingerprint",
  "status": "active|completed|cancelled|uncertain",
  "evidence": [{"source_url": "https://…", "field": "due_at"}]
}
```

Required invariants:

- `deadline_at` is absent rather than guessed when the time is unclear.
- Text-derived dates use `explicit_text` or `inferred`; only a provider field
  is `provider_exact`.
- A high-priority notification needs both a source reference and a concrete
  reason. `confidence=low` must never be silently escalated merely because a
  classifier used an alarming word.
- Cross-source deduplication preserves every source reference. It never
  overwrites Canvas data with an email paraphrase.
- A delete/revocation disconnect removes derived local data according to a
  documented retention rule, without altering the Telegram archive.

## Deterministic classification and ranking

Start with auditable rules, synthetic cases and a visible correction path. A
model may be evaluated later only through a separate egress/privacy decision;
it is not required to make the first version useful.

Suggested multi-label classification:

| Signal | Category / labels | Default action |
| --- | --- | --- |
| Canvas assignment, quiz, exam, module due date | `coursework`, plus course label | `submit` or `verify` |
| Professor/TA sender or course announcement | `instructor`, possibly `coursework` | `read`, `respond` or `verify` |
| Scholarship, fellowship, research, mentoring, internship, career fair | `opportunity` | `apply`, `register` or `read` |
| Housing, insurance/benefits, ISSO/immigration, registration, payment, holds | `administration` plus a specific area | `respond`, `register`, `pay` or `verify` |
| Ambiguous mailing-list content | `other`, `uncertain` | `read` |

Priority must be explainable and stable. A candidate policy is:

1. a verified deadline inside 24 hours is `critical`;
2. a verified deadline inside three days, a material cancellation, or an
   immigration/registration/payment action with a clear deadline is `high`;
3. an action inside seven days or a relevant opportunity is `normal`;
4. reference material and uncertain/general announcements are `low`;
5. missing, conflicting or inferred dates do not receive deadline escalation;
   they get a visible `verify date` cue.

Use `America/Chicago` only when the authoritative source has not supplied a
timezone and the user explicitly selects UTD's campus timezone. Store the
source timezone and render the user-local equivalent without changing the
original fact.

## Notification and reminder policy

The default outcome after a new connection is a private preview, not a
notification. A user must separately confirm which categories, urgency rules,
quiet hours and destination are enabled.

Recommended initial policy:

- immediate alert only for a source-backed `critical` item or material
  cancellation;
- one daily digest for ordinary items, capped at five;
- reminders for a confirmed deadline at 7, 3 and 1 day, with no duplicate after
  completion/cancellation;
- a weekly opportunities digest only if explicitly enabled;
- explicit `done`, `not relevant`, `mute category`, `snooze`, `open source`
  feedback; and
- idempotency key over `connection + item + event/change + reminder stage`.

Quiet hours, expiry, pause, cancellation, daily cap and a kill switch must be
checked at both collection and final-send boundaries. Existing
`external_watch.subscription` and `external_watch.delivery` are useful
behavioral references, but the Academic Inbox needs separate consent/version
binding so an old public-watch profile cannot authorize it.

## Storage, secrets and egress

If an implementation is later approved, use a dedicated gitignored sidecar
(for example `data/academic_inbox.db`), not the canonical Telegram archive DB.
The initial design should retain normalized facts, source references, hashes,
delivery receipts and minimal diagnostics. Raw provider payloads and mail
bodies must be transient, redacted or explicitly retention-bounded.

OAuth access/refresh tokens, client secrets and API keys must:

- live outside source control and test fixtures;
- be referenced in application data only by an opaque connection ID or secret
  reference, never by their value;
- be revocable by the user; and
- be excluded from logs, exception text, screenshots and model prompts.

There is no approved provider/model egress for personal email or Canvas data.
The default classifier, ranking and reminder path must be local and
deterministic. Sending a full email, attachment, Canvas page or batch export to
an LLM is prohibited unless a future ADR and explicit operator consent describe
the data, provider, budget, retention and rollback.

## Research phases and gates

| Phase | Permitted work | Required evidence | Stop condition |
| --- | --- | --- | --- |
| R0 — discovery | Read public documentation and inspect local code/fixtures. No credentials, accounts or live user data. | Source inventory, official URLs, licensing/terms notes and unanswered questions. | A source cannot be identified as official or permitted. |
| R1 — consent/security design | Design OAuth redirect, minimum scopes, token storage, revocation, retention and threat model using synthetic data. | Security review and a precise consent screen draft. | Scope is broader than necessary or university policy is unknown. |
| R2 — fixture contract | Build provider-neutral synthetic fixtures and deterministic classification/ranking/remainder tests. | Passing fixtures for false urgency, date ambiguity, conflict, duplicate and delete cases. | A reminder cannot explain source, deadline and priority. |
| R3 — adapter proposal | Prepare a read-only adapter design for one source, with no user connection. | Endpoint map, rate/backoff plan, source schema samples approved for sanitization, rollback plan. | Adapter needs a broad crawl, password, write permission or unbounded payloads. |
| R4 — human-approved pilot | Only after explicit approval, connect one account/source, preview locally and measure precision before Telegram delivery. | Signed approval, operator-reviewed samples, privacy receipt and disable/delete test. | Any unapproved egress, unexpected data class or incorrect critical notification. |

No phase starts PRM-19 dogfood, releases a product, enables a legacy timer,
widens the existing UTD public watch, or authorizes university-system actions.

## Questions the research agent must answer

1. Does UTD authorize a student-facing Canvas OAuth integration, and which
   exact read-only endpoints/scopes may it use?
2. Which mail provider serves the operator's UTD account, and can consent be
   limited to a dedicated mailbox/folder in a provider-enforced way?
3. Which Nebula API endpoints are stable, licensed for this use, appropriately
   fresh, and link to canonical UTD records?
4. Which official UTD sources cover scholarships, mentoring, housing,
   benefits/insurance and ISSO without harvesting private records?
5. What evidence makes a deadline authoritative, and how will ambiguity,
   changed due dates and timezone differences be rendered?
6. What data is retained, for how long, and how does connection revocation
   delete or invalidate it?
7. What measured precision/false-urgent threshold is needed before any
   notification delivery?

## Suggested assignment for a research agent

```text
Goal: produce a read-only, source- and privacy-validated integration proposal
for the optional UTD Academic Inbox described in
docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md.

Read first:
- docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md
- docs/adr/ADR-008-confirmed-external-watch.md
- docs/PRIVACY_THREAT_MODEL.md
- docs/IMPLEMENTATION_CONTRACT.md
- src/external_watch/{collector,fetch,store,subscription,delivery}.py

Deliver:
1. a verified source/endpoint matrix with primary-source links;
2. minimum OAuth scope and token/revocation design for each viable connector;
3. a synthetic fixture and evaluation plan for classification, deadlines,
   dedupe and reminders;
4. a separate list of approvals/ADRs needed before implementation or runtime;
5. a recommendation: proceed / needs-human-decision / do-not-integrate.

Hard boundaries:
- do not request, view, paste, transmit or log any password, token, chat ID,
  email, Canvas record, attachment, private Telegram archive or live account;
- do not start a service/timer, call a private provider endpoint, create a
  developer key, or change mail/Canvas state;
- do not make an LLM/provider call with personal academic data;
- do not claim that a public aggregator is an official source without direct
  evidence.
```

## Public references inspected for this brief

- [UTD Nebula API repository](https://github.com/UTDNebula/nebula-api) — says
  that it exposes UTD data through internal/public endpoints and documents an
  API-key request path.
- [UTD Nebula API Tools](https://github.com/UTDNebula/api-tools) — documents
  its scraper/parser/uploader pipeline and the public UTD data types it covers.
- [UTD Canvas migration](https://ets.utdallas.edu/elearning-services/canvas-migration/)
  — states that Canvas is the LMS for Fall 2026 courses.
- [Canvas OAuth2](https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth_endpoints)
  and [developer-key scopes](https://developerdocs.instructure.com/services/canvas/oauth2/file.developer_keys)
  — describe institution-controlled OAuth clients and endpoint scopes.
- [Canvas Assignments API](https://canvas.instructure.com/doc/api/assignments.html)
  — documents assignment records and read/write endpoints; this proposal permits
  only reviewed `GET` endpoints.
- [Microsoft Graph permissions](https://learn.microsoft.com/en-us/graph/permissions-reference)
  and [Gmail server-side OAuth](https://developers.google.com/workspace/gmail/api/auth/web-server)
  — document the provider permission models; neither proves which provider the
  operator uses.

No credentials, private UTD records, email content, Canvas data or Telegram
archive data were accessed to create this document.
