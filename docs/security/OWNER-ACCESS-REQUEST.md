# Owner access request — what to get and what to hand over

Status: preparation checklist. Nothing here is granted yet. **Do not paste any
secret into chat.** Secrets go into files under
`/srv/openclaw-you/workspace/telegram-research-agent/secrets/` (git-ignored) or
a path you name; never into Git, logs, screenshots or Telegram messages.

## 1. What I need from you (in priority order)

| # | Item | Where you get it | Minimal access to grant | What to give me |
| --- | --- | --- | --- | --- |
| 1 | UTD mail + calendar (Microsoft 365) | `entra.microsoft.com` → App registrations (single-tenant) | Delegated `Mail.ReadBasic`, optionally `Mail.Read`; `Calendars.Read`; `Contacts.Read` | Tenant ID, Application (client) ID, client secret (or use public client + PKCE), redirect URI |
| 2 | Canvas (PA-12) | UTD eLearning/IT → developer key / OAuth app | Read-only `GET` scopes: assignments, announcements, calendar | Canvas base URL, client ID, client secret, redirect URI, confirmation that a student personal integration is allowed |
| 3 | UTD Nebula API (optional, public data) | Nebula Labs | Read-only public campus data | API key + endpoint list |
| 4 | Judge model (already available) | — | — | Nothing: OpenCode Go key already at `Georgia-Community-Navigator/secrets/openrouter_api_key` |
| 5 | Telegram archive (already available) | — | — | Nothing further |

## 2. How to hand secrets over (one of these)

- Preferred: create the file yourself, e.g.
  `/srv/openclaw-you/workspace/telegram-research-agent/secrets/microsoft_graph.json`
  and tell me the path; or
- Put single values in a file and tell me its path (I read it by path, I never
  print the value).

Suggested files:

```text
secrets/microsoft_graph_client_id
secrets/microsoft_graph_client_secret
secrets/microsoft_graph_tenant_id
secrets/canvas_client_id
secrets/canvas_client_secret
secrets/canvas_base_url
secrets/nebula_api_key
```

## 3. What you must never send

- Passwords, MFA/Duo codes, recovery codes.
- A token pasted into chat, a commit, an issue, a screenshot or a Telegram DM.
- Broad consent you do not intend to keep (e.g. `Mail.ReadWrite`, tenant-wide
  admin consent) when a read-only scope is enough.

## 4. What happens once you provide them

1. I implement the OAuth authorization-code + PKCE flow and a token vault
   outside Git, with revoke/delete.
2. I run a **read-only** sync against a bounded selection (folder/domain, small
   `max_items`) and show a private preview.
3. Only after you confirm the preview do derived summaries get stored, and only
   then does a reminder policy (PA-12) become possible.
4. Live use stays blocked until you explicitly approve each live path; the
   judge and the local code never create that consent on their own.

## 5. Still needed later (not now)

- Which mailbox folder/labels to treat as university-only.
- Whether Canvas personal integration is permitted by UTD (email to
  eLearning/IT) — this is an institutional permission, not a technical step.
- Whether you want the weekly brief judged on rendered screenshots from the
  phone, desktop HTML, PDF or all three.
