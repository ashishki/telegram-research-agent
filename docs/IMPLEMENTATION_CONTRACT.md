# Implementation Contract
_v3.0 · telegram-research-agent · change only with explicit architecture approval_

---

## Universal Rules

### SQL Safety

- All SQLite queries parameterized.
- Never interpolate values into SQL.

### Secrets And Credentials

- No credentials in source control.
- All secrets via environment variables.
- Telegram session files never committed.

### LLM Calls

- All LLM calls go through `src/llm/client.py`.
- LLMs may consume scoped context, not arbitrary corpus dumps.
- New memory work must reduce prompt ambiguity, not hide logic inside prompts.

### Memory Architecture Rules

- Structured operational state remains canonical.
- Summaries and snapshots are derived, bounded, and refreshable.
- Verbatim evidence storage is selective and provenance-preserving.
- Retrieval must narrow by project/topic/time/source before broad search.
- Decision history must be explicit and inspectable.
- No decorative memory abstractions such as wings, halls, rooms, diaries, or compression dialects.
- No second generic memory engine unless the scoped SQLite design is proven insufficient.

### Product Contract

- Output remains a weekly decision-support artifact.
- Signal intelligence and decision support remain the product center.
- Memory exists to improve continuity and evidence quality, not to become a separate product.

### Bot Access

- Telegram bot responds only to the owner chat id.

### Error Handling

- Delivery and LLM failures degrade gracefully.
- Missing memory context must fail safe and visibly, never silently invent facts.

---

## Scope Discipline

- Do not skip from planning straight into broad implementation.
- Do not combine schema design, retrieval redesign, and prompt rewrites in one patch set.
- Every new memory or feedback layer must declare:
  - source of truth
  - refresh rule
  - retrieval path
  - debug surface
- Every backlog item must have explicit success criteria and validation steps.

---

## Mandatory Pre-Task Protocol

1. Read `docs/tasks.md`.
2. Read `docs/memory_architecture.md` if the task touches memory, retrieval, prompts, or weekly outputs.
3. Verify which state is canonical versus derived before editing code.
4. Add tests or fixtures for new retrieval, feedback, continuity, or delivery behavior.
5. Do not add broad abstractions without a concrete caller.

---

## Governing Documents

- `README.md`
- `docs/architecture.md`
- `docs/memory_architecture.md`
- `docs/tasks.md`
- `docs/CODEX_PROMPT.md`
