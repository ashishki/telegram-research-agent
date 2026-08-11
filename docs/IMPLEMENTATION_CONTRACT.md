# Implementation Contract

Status: immutable after ADR approval; changes require a new ADR under
`docs/adr/`.

Version: 4.0-proposed

Effective date: proposed 2026-07-26

## Product Authority

The proposed product center is Personal Telegram Research Memory + Grounded
Assistant. Weekly reports are derived secondary projections. The report-centered
v3 contract is superseded only after
`docs/adr/ADR-001-product-pivot-to-personal-research-memory.md` is accepted by
the human operator.

Until acceptance, implementation tasks that change product direction require
explicit human approval.

## Universal Rules

### SQL Safety

- All SQLite queries are parameterized.
- Never interpolate values into SQL strings.
- Dynamic table or column names require an allowlist.

### Secrets And Credentials

- No credentials in source control, comments, fixtures, logs, or generated
  public artifacts.
- Telegram session files stay outside the repo.
- Provider keys come from environment variables or documented secret paths.

### Private Telegram Data

- The Telegram corpus is private operator data.
- No raw corpus dump may be sent to an LLM.
- Retrieval context sent to a model must be bounded, source-cited, and
  task-relevant.
- Ordinary logs must not contain raw post text or chat transcript text.
- Generated public fixtures must be sanitized and contain no private Telegram
  content.

### Canonical Storage

- Local SQLite `raw_posts` and `posts` remain the canonical archive where
  possible.
- Do not duplicate full post text into a second store unless an ADR records the
  measured need, rollback path, and privacy boundary.
- PRM-27 local vector sidecar is derived index state, not canonical storage;
  it stores bounded snippets and local hashed vectors under `data/vector/`.
- `posts_fts` or its successor is an index, not a second source of truth.
- Knowledge Atoms, topics, notes, watch topics, decisions, and experiments are
  curated/derived layers.

### RAG And Retrieval

- Basic archive search must not require a Knowledge Atom, topic, report, Atlas,
  or curated retrieval item.
- Full-archive FTS baseline comes before embeddings.
- Do not install or select Qdrant, FAISS, sqlite-vec, Chroma, or a provider
  vector store without evaluation and ADR approval. ADR-004 approves only the
  built-in local SQLite sidecar with deterministic hashing.
- External embedding APIs require explicit data-egress approval.
- Assistant answers must support `insufficient_evidence` instead of filling
  gaps from model background.

### Assistant Tooling

- The assistant has one user-facing entrypoint.
- Read-only search and context tools may run without confirmation.
- Writes are proposal-and-confirmation gated.
- No assistant tool may edit code, profile, project config, provider config, or
  permanent preferences automatically.
- Child agents or subagents never commit, push, self-review, or grant
  completion authority.

### Reaction Semantics

- Any visible personal reaction means positive implicit interest.
- Emoji type is audit metadata only.
- No reaction means unknown, never negative.
- A reacted post must remain searchable even when enrichment fails.
- A reaction may propose a preference only after repeated evidence and human
  approval.

### Learning State

Do not infer user learning from source existence.

Allowed states are:

- indexed
- surfaced
- opened
- read
- understood
- explained
- tried
- applied
- measured
- rejected
- stale

The additive migration must preserve legacy rows and must not fabricate higher
states.

### Cost

- AI calls must use documented workload classes and budgets in
  `docs/COST_BUDGET.md`.
- Full archive LLM backfill is forbidden without a new human-approved ADR.
- Enrichment batches must be bounded, cheap-model first, and retry-limited.

### External Skills

- External skills and community runtimes are untrusted until reviewed.
- Skills may not inspect broad filesystem areas, secrets, or private Telegram
  data without a trust record and explicit human approval.
- During this planning retrofit all listed external skills are
  project-disabled or pending trust tasks; none is approved.

## Playbook Execution

- Adoption mode: Standard.
- Runtime tier: T1.
- Bootstrap model: Codex Direct.
- Ongoing delivery model: split_orchestrated.
- Human remains final completion authority.
- Optional `codex exec` subagents may be used only after bootstrap for isolated
  read-only review, Test Critic, privacy review, scoped fixes, and doc sync.

## Mandatory Pre-Task Protocol

1. Read `docs/tasks.md`.
2. Read `docs/CODEX_PROMPT.md`.
3. Read the context docs listed in the task block.
4. Verify canonical versus derived data boundaries before editing code.
5. Run the task-specific verification and record evidence.
6. Do not claim product value, RAG availability, or dogfood success without the
   relevant eval and human evidence.

## Governing Documents

- `README.md`
- `docs/PROJECT_BRIEF.md`
- `docs/ARCHITECTURE.md`
- `docs/IMPLEMENTATION_CONTRACT.md`
- `docs/personal_research_memory_product_contract.md`
- `docs/tasks.md`
- `docs/CODEX_PROMPT.md`
- `.playbook/delivery_execution_model.json`
