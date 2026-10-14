# Documents, feedback, memory and rich presentation — local operation

The local package D19/D20/D21/D58 extends the existing durable runtime. It does
not configure a bot, account, provider, private database, service or timer.
Full Chat/Search/beautiful Brief/Watch/confirmed Act remains the programme;
Mini App is excluded. Synthetic acceptance demonstrates mechanics, not quality,
client appearance, real integration or operator usefulness.

Reply to a delivered Brief or use its opaque Sources/Full/Save control to select
that exact document/version. `поясни пункт 2`, `почему это важно`, `покажи
источники`, `что из этого применить`, `сделай короче`, `сравни с прошлой неделей`
reuse its facts and digest. `обзор «Protocol» версия 1: покажи источники` is a
bounded owner-local lookup. Ambiguous versions/stories or unavailable provenance
clarify. Replying to an older document keeps the current foreground task.

`обнови бриф` explicitly re-reads the retained period using currently selected
and permitted sources, creates an immutable version, and reports event revision
changes. Metadata-only refresh can replace a stale snapshot; it does not recover
revoked content. Current source grants and original Telegram input still apply.
Version comparison never bypasses a replaced project/rule or source snapshot.

`экспорт HTML`, `экспорт PDF`, `экспорт Markdown` produce actual local bytes
from that same document, persisted in bounded existing result chunks. The export
manifest records document identity, byte hash and provenance. `read_export` needs
the exact authenticated private owner tuple and current sources. This is not
hosted/mobile delivery; D25/D40 retain that gate.

Explicit labels include `полезно`, `не моя тема`, `это знаю`, `слишком длинно`,
`неверно`, `применил`, optionally `пункт 2`. They create exact-version feedback
events. All owner emojis mean positive interest; no reaction means unknown.
Applied/read/tried are never inferred. Legacy import accepts a supplied row,
confirmed owner and exact document binding; it never scans a personal SQLite DB.
`не показывай тему Protocol` or `больше темы Protocol` previews one scoped rule.
`подтверди сохранение` applies the current exact preview; `отмени правило
memory_<id>` deletes it. A rule changes only its matching topic feature and
cannot hide critical/conflicting changes. Why-shown uses actually included
anchors. The optional weekly prompt is disabled by default and starts no job.

`запомни: …` previews a note; `подтверди сохранение` confirms the current preview.
`исправь память memory_<id>: …` also previews a new version. `найди в памяти …`,
`покажи память`, `экспорт памяти` and `забудь memory_<id>` inspect or remove
confirmed context. Intervening tasks/reset invalidate the confirmation target.
New-source bindings, consumed confirmation, correction, expiry and deletion are
checked. Conversation reset keeps independently confirmed memory.

Automatic context uses at most four lexical matches among128 recent heads,
text only, at most1200 characters per entry. It requires separate current
`model.context_egress` grants with purpose `dialogue.memory` for
`resource_memory/user_provided` and every protected resource/class. Unknown
legacy provenance is excluded. No external embeddings or second memory store.
Source/memory authority stays locked through bounded HTTP. Final response and
origin are atomic. A concurrent forget/correction/revoke can hide the finished
answer and complete with `source_unavailable`, without a retry or stale facts.

The concrete save+undo proposal remains **proposed_inactive**: only an
unambiguous new owner note would qualify; preferences/projects/learning and
private-source promotion are excluded. Owner adoption is still needed. Current
preview/confirmation is preserved until then.

`delivery.rich_messages` is an explicit boolean, false by default. Opt-in
rendering uses the persisted document; model text cannot provide executable
rich blocks, URLs or buttons. The supported no-media subset is validated against
the [official Bot API](https://core.telegram.org/bots/api#rich-messages):
32768 Unicode characters,500 blocks including table rows, depth16,20 columns,
zero media, and local24KiB JSON/part,32-part bounds. Source URLs and callback
tokens are trusted allowlists. Split sections retain content and source identity.

Known first-part format rejection allows a separately recorded compatible send
of the same result. Status reports both attempts. Other rejection, acceptance of
an earlier part, or unknown outcome cannot authorize fallback/resend. Restart
retains those fences. Rich edits require the exact acknowledged own message,
current source/input and result digest; only presentation revision changes.
Unknown edit blocks further edits. Full action previews retain compatible exact
text and existing confirmation semantics.

Baseline action-preview tests still fail closed without required source
provenance; package8 does not grant action/read scopes or repair the unrelated
action provenance contract. Live rich/client/Stop/visual validation, private
logging/retention, non-Codex Go/governed reviews and human acceptance are open.
Rollback disables document dispatch/context/ranking or the rich flag, retaining
immutable versions, consumed/unknown receipts, tombstones and source identities.
