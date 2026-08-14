# User-first Telegram UX — 2026-08-14

The manual PRM assistant treats ordinary text and voice as the primary surface.
Only research, brief, chat, status, refresh, and reactions remain PRM fallback
commands; legacy report/workbook controls stay in legacy runtime compatibility
but are refused with a plain-language redirect in PRM mode. Confirmed-memory
buttons remain confirmation-gated. No dogfood, provider call, or private data
commit occurred.

Focused handler/callback/proposal checks were run; no full suite was run.

## Local user-path simulation follow-up

Read-only local simulation classified three ordinary Russian messages as
`research`, `brief`, and `clarify` respectively. No Telegram message, provider
call, live fetch, or durable write was performed. The source-backed research
path returned cited local evidence and boundaries. The zero-evidence brief path
was adjusted so that it now offers two plain-language next actions: broaden the
topic or provide a source, rather than ending at a technical no-result state.

Verification command and result:

```text
PYTHONPATH=src python3 -m pytest tests/test_memory_research.py tests/test_handlers.py -q
89 passed in 17.01s
git diff --check
```
