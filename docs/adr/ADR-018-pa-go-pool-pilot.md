# ADR-018 — another Go model and current-candidate verification

2026-10-10 owner instruction: «делай, выбери другую моедл ищ пула го,
там у нас есть еще лимиты точно». This supersedes the pending Codex choice and
the GLM-only selection for the requested fresh engineering/content assessment.
Use the SAME Go endpoint and known external key location. No account quota is
assumed merely from a public model list.

Selected text reviewer/judge: deepseek-v4-pro, requested reasoning_effort=max.
Selected synthetic conversation generator: deepseek-v4-flash, explicitly
thinking-disabled for this latency benchmark, not a production model change.
Selected visual judge: existing deepseek-v4-flash-vision-exp. Official Go docs
list all three at /zen/go/v1/chat/completions; public /models confirms their IDs.
DeepSeek documents max effort, JSON-object output and393216 maximum tokens.
The text review retains1MB input/7200s/64MiB SSE/1MiB final-text bounds and uses
the selected model's documented maximum output. Requested/observed effort,
actual tokens, HTTP failure cause and unknown billing stay separate.

One fresh independent read-only engineering request examines the deletion P1
and accumulated product changes on an exact committed candidate, including the
small advisory transport used for this request. It has no tools or write ability.
This is advisory engineering closure, not a governed design/role aggregate or
human/release approval. Existing GLM role-consumer guards/history stay intact;
do not mix model phase sets or relabel old STOP/failures. Register and exercise
new transport holdouts before the public-source request. No full historical
tests or repeated unchanged full PAI tiers.

After usable safety closure, capture current native Chat/Search/Brief with real
Go inference and wholly synthetic input/source data; exercise natural Watch/Act
controls with synthetic external effects. Evaluate complete captured sessions
once through the selected text judge; assess actual current native renders once
through the visual judge. Preserve failures and differences between inference,
fixtures, browser inspection, real connectors and human usefulness.

The user's instruction also advances pilot preparation. Inspect public setup
and make an executable source/operation packet. Specific live account/resource/
destination selection is still missing; a generic instruction does not identify
a mailbox, calendar or Telegram destination. Continue all independent work while
asking for those missing selections. Exact external sends/writes still require
their full owner-bound current preview. No keys/private corpora/account IDs in
Git, private-model egress, production migrations/services/timers or release.
UTD stays owner-deferred. Do not restart superseded programme/design batches.

Sources checked2026-10-10:
- https://opencode.ai/docs/go/#endpoints
- https://opencode.ai/zen/go/v1/models (public metadata only)
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://api-docs.deepseek.com/guides/thinking_mode/
