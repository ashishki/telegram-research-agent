# D19 + D20 + D21 + D58 — local package boundary

Base/handoff1db5034c8b2374add70d16ef6a354ac26f0bc505; reviewed source1717567.
Assigned branch codex/pa-daily-implementation-20261013 was clean. Owner requested
the next block after package7. Full Chat/Search/beautiful Brief/Watch/confirmed
Act and Mini App exclusion persist. This registers implementation before edits,
not human design/feature approval. No private corpus/account/key, paid calls,
production/DDL/service/timer, hosting, external effects or master integration.

Context: four BACKLOG cards, PRODUCT_ARCHITECTURE document/focus/memory/feedback
sections, TELEGRAM shared document/delivery contracts, full-spec UX-02..05,
MEM-01..03 and BRIEF-05..07. Existing immutable BriefDocument, runtime object
versions/dependencies, previews, focus and delivery ledgers stay canonical.

D19: resolve document/version/story from exact reply/callback or named object,
then admitted foreground focus. Natural explain/why/apply/shorten/filter/compare/
refresh/export use the persisted document, not generic text slicing. Restyle
retains facts/digest; explicit refresh re-reads the selected window, creates a
new immutable version and reports source/event changes. Ambiguous, revoked,
deleted or stale provenance fails with a useful bounded choice/status. No
revoked content becomes accessible through a historical label. Returning to
older versions does not steal foreground focus or revive confirmations.

D20: immutable versioned FeedbackEvent for explicit useful/not-topic/known/
too-long/incorrect/applied and positive personal reaction interest. No reaction
is unknown, every visible emoji is positive interest; read/applied are never
inferred. Legacy feedback adapters accept explicitly supplied exact bindings,
not automatic scans of private SQLite databases. Only an explicit preview and
confirmation creates a scoped preference rule; rules can be inspected/removed,
affect one matching topic/feature and cannot hide required critical/conflict
events. Why-shown includes the actual signals; weekly feedback prompt optional
and foreground only. Passive signals never change durable project/profile.

D21: bounded lexical retrieval of current confirmed notes/preferences/projects,
separate from JSON substring metadata matches, newest corrected version only.
Natural save/correct/inspect/search/forget/export retain the existing preview/
confirmation flow. Concrete save+undo policy remains proposed, inactive until
owner adoption; no missing decision blocks independent context/retrieval work.
Typed exact source bindings/expiry/confirmation and dependencies accompany new
memory. Context uses at most four relevant bounded entries with explicit model
context grants per resource/data class and current source checks through HTTP.
Deletion/correction/expiry/revoke invalidates cached/derived answers; reset clears
conversation focus/history and keeps independently confirmed memory. No second
memory service or external embeddings. Unknown legacy provenance is not silently
admitted to automatic model context.

D58: opt-in pure server renderer over exact BriefDocument/answer. Heading,
paragraph, compact table, details, source links/references and opaque trusted
controls. Validate aggregate text/block/depth/media/table limits; split on
sections without silent loss. sendRichMessage and exact-message rich edits use
the existing delivery ledger/route and per-attempt source checks. Known format
rejection permits a separately recorded compatible presentation of the same
document; unknown outcomes cannot resend/fallback. Exact full action previews
keep existing confirmation semantics. Rich off, old receipts and plain exports
remain readable. No remote media fetch or Mini App. Telegram contract checked
against [official Bot API](https://core.telegram.org/bots/api#rich-messages) on
2026-10-14; documentation reads are not live/client/visual validation.

One native synthetic outcome: create/version a Brief, reply/callback to its exact
story across restart/another foreground task, record explicit feedback, confirm
a scoped rule/note, use relevant memory under separate grants, render/deliver the
same document through opt-in rich and compatible fallback without unknown replay.

One fresh independent local read-only accumulated Deep Review after scoped checks
covers all four cards: owner/version/focus, provenance/deletion, memory/rule
confirmation and egress, callback trust, payload bounds and delivery/recovery.
P0/P1 receive narrow independent rechecks before dependent work; no repeated full
review per fix. Inherited active defaults/no model/effort override; observed
unknown. Local collaboration evidence does not fill non-Codex Go/governed/design/
human gates. Reviewer has no mutations, tests/DB, credentials or provider calls.

Registered acceptance command:

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-pai/bin/python -m pytest -q tests/test_daily_document_dialogue.py tests/test_daily_feedback.py tests/test_daily_memory_context.py tests/test_daily_telegram_rich.py
```

Cases: two docs/two versions/ambiguous story2/old reply/restart/late completion;
refresh vs restyle/provenance parity/revoke; explicit signals/all emoji/no reaction/
undo rule/scoped A-B selection/learning-state provenance; relevant vs unrelated
memory/correction/reset/expiry/revoke/forget/context grants; real loopback transport
schema/Cyrillic/emoji/nested bounds/table/sources/spoofed controls/full preview/
known reject vs unknown/route substitution. Small affected floors: existing
report dialogue, native Brief, memory/conversation, Telegram and delivery tests.
No full historical pytest or immutable Go reruns.

Rollback disables new document dispatch/context/ranking or rich flag; retain
immutable versions, consumed previews, unknown receipts, tombstones and source
IDs. New metadata uses existing version store; no schema/checksum rewrites.
