# Implementation Contract
_v2.0 · telegram-research-agent · Immutable rules. Require ADR to change._

---

## Universal Rules

### SQL Safety
- All SQLite queries parameterized — `cursor.execute("... WHERE id = ?", (value,))`
- Never f-strings or string concatenation in SQL
- FTS5 queries use `MATCH ?` with bound params

### Secrets & Credentials
- No credentials in source code
- All secrets via environment variables: `LLM_API_KEY`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_CHAT_ID`, `GITHUB_TOKEN`
- Telethon session file (`.session`) never committed to git

### LLM Calls
- All LLM calls go through `src/llm/client.py` — never call Anthropic SDK directly from modules
- Model routing must be explicit and tiered: `CHEAP`, `MID`, `STRONG`
- Strong models are reserved for filtered high-value subsets only
- Every LLM call logged to `llm_usage` table (model, tokens_in, tokens_out, cost_usd, category)
- Cost tracking is mandatory — no untracked LLM calls

### Signal-First Product Contract
- Output is a decision-support artifact, not a generic digest
- The target section model is: `Strong signals`, `Project relevance`, `Weak signals`, `Think layer`, `Light/cultural`, `Ignored`
- Ignored/noise handling must remain visible somewhere in the output contract

### Personalization Guardrails
- Personalization may re-rank but must not replace evidence-based signal quality
- Preference memory must be explainable and reviewable
- Personalization work must not be implemented before routing and project relevance gates are met

### Bot Access
- Telegram bot responds only to `TELEGRAM_OWNER_CHAT_ID`
- No public access, no group access, no unauthenticated commands

### PII Policy
- No user data in logs beyond owner's own messages
- Telegram post content stored in SQLite only — not in logs or external services

### Error Handling
- Telethon `FloodWaitError` — always sleep + retry, never abort
- LLM failures — log, return fallback (empty digest, error message), never propagate exception to bot
- PDF rendering failure — graceful fallback to Markdown text

### CI
- CI must pass before any PR is merged
- `python3 -m unittest discover tests/` must exit 0

---

## Project-Specific Rules

| ID | Rule | Reason |
|----|------|--------|
| A | SQLite WAL mode always on | Parallel reads from bot + ingest without locking |
| B | Clustering is deterministic (no LLM in cluster step) | Reproducible results across runs; LLM only for labeling |
| C | `message_url` stored as `t.me/channel/message_id` | Audit trail; source attribution in PDF appendix |
| D | Output files written to `data/output/` only (gitignored) | Keeps repo clean; data is ephemeral |
| E | systemd timers define the schedule — never cron | Consistent with existing deployment |
| F | Routing policy must expose tier usage and escalation rate | Cost-aware behavior must be measurable |
| G | Personalization cannot suppress globally important signals without explicit rule trace | Prevents opaque bias |

---

## Forbidden Actions

- String interpolation in SQL
- Direct `anthropic.Anthropic()` calls outside `src/llm/client.py`
- Committing `.session` files or `.env` files
- Responding to non-owner Telegram IDs in bot handlers
- Skipping pre-task baseline capture
- Self-closing review findings without code verification
- Implementing future-phase capabilities inside the current phase without roadmap approval

---

## Mandatory Pre-Task Protocol

1. Read full task entry in docs/tasks.md
2. Run `python3 -m unittest discover tests/` — record baseline
3. Check no uncommitted changes: `git status`
4. Write tests before or alongside implementation
5. Every acceptance criterion must have a passing test

---

## Governing Documents

| Document | Role |
|---|---|
| `docs/architecture.md` | System design, data flow, component table |
| `docs/spec.md` | Feature specification |
| `docs/tasks.md` | Task graph — authoritative |
| `docs/CODEX_PROMPT.md` | Session handoff — current state |
| `docs/IMPLEMENTATION_CONTRACT.md` | This file — immutable rules |
| `docs/audit/` | Review cycle reports (append-only) |
| `docs/adr/` | Architectural Decision Records (append-only) |
