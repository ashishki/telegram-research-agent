# PA-10 — UTD mail/Canvas access and parsing plan

Status: research + implementation-boundary note. This is **not** consent, an
OAuth grant, a credential, a connector activation, or permission to read any
account. No token may be pasted into chat, committed or logged. The provider is
selected explicitly and never guessed from an email address.

Last verified: 2026-09-23.

## 1. Actual provider (evidence)

UT Dallas email is Microsoft 365 / Exchange Online, protected by Duo and modern
authentication; IMAP/SMTP work only via OAuth2, and automatic external
forwarding is disabled by UTD policy. Therefore the first mail adapter is
**Microsoft Graph (delegated)**, not Gmail and not IMAP-with-password.

- UTD service catalog: `https://atlas.utdallas.edu/TDClient/30/Portal/Requests/Service/29/Individual-UTD-Email`
- Graph permissions reference: `https://learn.microsoft.com/en-us/graph/permissions-reference`
- Canvas OAuth2 developer keys: `https://developerdocs.instructure.com/services/canvas/oauth2/file.developer_keys`

## 2. How the owner would grant access (later, separately authorized)

1. Register an app in Microsoft Entra (`entra.microsoft.com`) as a **single
   tenant** app owned by the owner's UTD tenant if UTD policy allows it;
   otherwise a multi-tenant app whose consent an admin must approve.
2. Add a **delegated** redirect URI that points at the operator's own loopback
   or private client (authorization code + PKCE). Never a public server.
3. Request the smallest delegated read scopes:
   - `Mail.ReadBasic` (headers/metadata only) — preferred first;
   - `Calendars.Read` and `Contacts.Read` only when PA-11 needs them;
   - `Mail.Read` only if classification genuinely needs body text.
4. Complete interactive sign-in. Duo/conditional access is handled by Microsoft
   at sign-in; the app never sees the password and never bypasses MFA.
5. Store the refresh/access tokens in an encrypted local vault (OS keyring or a
   file with restrictive permissions outside Git). Support **revoke** (Graph
   `/revokeSignInSessions` or deleting the token) and **delete** of derived data.
6. Canvas (PA-12): ask UTD eLearning/IT whether a student-facing personal
   integration is permitted and how a developer key is issued. Use OAuth2 with
   read-only `GET` scopes for assignments/announcements/calendar only.

## 3. What is open / public without account access

| Source | Access | Use |
| --- | --- | --- |
| UTD Nebula API | Public campus data; production API requires a provisioned key | Secondary **discovery** only; urgent alerts must cite the primary UTD/Canvas source |
| Canvas REST API | OAuth2; read-only scopes possible for institutional keys | Canvas assignment/announcement authority (PA-12) |
| UTD public pages already used by the watch | Existing allowlisted collector | Must not be widened just because PA-10/12 exist |

## 4. Parsing rules (implemented direction)

- Normalize allowed messages into bounded thread summaries: takeaway, requested
  decisions, supported deadlines (with timezone + source), opportunities, and a
  category of `obligation | opportunity | reading | administrative | uncertain`.
- Retrieve headers and the smallest text field needed to classify. **No
  attachments by default; no raw body retention.** Store only a normalized
  summary, a content hash and source references.
- A folder/domain selection is an **application filter**, never a
  provider-enforced token restriction; the UI must say so.
- Conflicting deadlines are surfaced, not merged. An aggregator record is never
  the authority for an urgent deadline.

## 5. Implemented vs. not implemented

Implemented in this slice (`src/prm/mail_connector.py`, synthetic tests only):

- documented provider profiles with honest scope description;
- bounded read-only `MailScopeSelection` that refuses bodies/attachments;
- owner-bound, expiring consent preview/confirmation with a scope digest;
- `require_mail_read_access` fail-closed PA-02 reservation check for the
  `mail.read` transport purpose;
- normalized `MailThreadSummary`/`MailDeadline` with conflict detection;
- an explicit-path derived store for normalized summaries with revoke/delete.

Not implemented and not authorized here: OAuth flow, token storage, any live
Graph/Canvas call, a scheduler, Telegram delivery, or a default database.
