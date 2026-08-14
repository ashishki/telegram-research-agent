# PRM Mature Product Gap Audit

Audit date: 2026-08-13. Target baseline `c282056210c09781cbe45fe00ac2b0008bc35043` on `master`, clean before this documentation edit. Playbook baseline `965612aa463fca1a35a55104633d0e09da33d615` on `master`, clean. Requested target `d27158a…` is an ancestor; later commits added retrieval/Telegram integration and governance. Target docs still pin both `5583eca…` and `965612…`; the former is stale.

| Existing PRM-UX component | Verified maturity | Evidence and remaining gap |
| --- | --- | --- |
| SQLite FTS archive search | integrated | Runtime research uses it; focused tests exist; no new live smoke was run. |
| local SQLite vector sidecar/hybrid retrieval | integrated | Gated runtime path/fixtures; sidecar freshness receipt is not user-value proof. |
| citation-safe context/freshness/no-answer gate | integrated | Research path consumes it; current facts receive verification boundary. |
| ordinary text/voice and auto route | integrated | `/auto` exists, but selects route rather than a canonical workflow contract. |
| Russian answer-first rendering | integrated | Research/brief renderer uses it; technical English remains in some failures/docs. |
| post-answer actions | implemented | Telegram calls it, but state is volatile and success leaks IDs. |
| professional lens | implemented | English lexical soft reranker; not wired to runtime candidates/answer. |
| portfolio V2 helper | contracted | Fixture/in-memory only; runtime still reads legacy config/named lookup. |
| five professional workflows | implemented | Multiple keyword projections attach internal JSON, not one reader-facing workflow. |
| primary-source verification | contracted | Plan-only; `www.*` is wrongly treated official; no fetch/cache/SSRF controls. |
| PRM-19 question receipts | contracted | Non-persisting builder; no automatic answer linkage/button update. |
| weekly recap | implemented | Supplied-payload projection; first project/event/count logic is shallow. |
| refresh receipt and `/refresh` | contracted | Projection exists; Telegram flow is explicitly absent. |
| reaction fast lane | implemented | Searchable receipt/sync logic tested; no reliable routine/ranking/user flow. |
| saved knowledge | integrated | Confirmation writes events, but no durable proposal or mature query lifecycle. |
| report-era templates | deprecated_or_legacy | Retained history; some active docs still expose report commands. |

No row is `live_smoke_verified` or `operator_validated` merely because a service exists or fixtures pass. Existing activation and refresh artifacts are local runtime receipts, not dogfood or product-value evidence.

## Findings

`memory_research.py` can activate every matching workflow; their output is hidden in `professional_workflows` and omitted by normal rendering. Lens scoring splits English preference phrases into tokens and is not called on live candidates. The V2 project helper is not the source of runtime configuration. Dialog/action dictionaries have no TTL, persistence, concurrency protection, chat binding, cancellation or replay barrier. Verification never fetches. PRM-19 does not automatically persist. `/refresh` is planned. Reaction isolation is a contract rather than a complete operator routine. `/start`/help and operator workflow retain internal/provider/report content.

## CI, documentation, risk

GitHub CI is configured for push/PR full pytest plus public-evidence check. At capture, `gh run list` showed five recent failed runs, including current-HEAD run `31733747425`; diagnosis belongs to PRM-MAT-16. Existing task truth marks PRM-UX implemented even where only contracts are present; historical evidence stays intact and narrow successors carry the gap. Root README is concise but contains past host-state claims; `docs/operator_workflow.md` includes old report commands; reaction, verification and backup runbooks are absent.

Reusable foundations: FTS/vector retrieval, context packs, RAG gate, bounded budget, Telegram chunking, confirmation-token writer, reaction searchability receipt and privacy render helpers. Risks: ledger privacy, accidental canonical writes, stale state, false professional advice, Russian recall, CI drift and legacy confusion. Blockers are explicit config/schema/schedule/provider/fetch/dogfood approvals. Do not broad-refactor before normal-path integration proof.
