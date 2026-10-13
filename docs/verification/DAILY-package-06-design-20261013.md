# D11/D12/D14/D16 — local implementation boundary

Base d825ce5, branch codex/pa-daily-implementation-20261013. Previous package
critical gate closed on8f193bb. No concurrent source changes. One coherent
package: selected retrieval → public discovery/read → supported answer blocks
and whole-week Brief candidates. Full programme retained; Mini App excluded.

- D11: one canonical retrieval service, original FTS baseline retained, bounded
  deterministic RU/EN variants and dedup/diversity. Optional existing hashed
  sidecar candidates must be revalidated against canonical content and every
  filter; no implicit index creation or external embedding. Freeze synthetic
  labels before implementation; compare FTS/expanded FTS/current hashed fusion
  with recall@20/nDCG@10/MRR/no-answer errors and per-language/filter receipts.
  Learned candidate remains explicitly not run, D46 needs measured miss classes.
- D12: extend typed planner with a bounded public-search proposal for ordinary
  questions. Public query can only project current owner text, never remembered
  private context or source text; private-context requests need a separate public
  formulation. Reuse Brave/safe fetch, exact selected domain policy, prepared
  no-repeat scope gates. Snippets remain discovery, fetch timestamps/versions
  remain distinct; stale/unknown-date content cannot establish a current fact.
  RSS is conditional on a measured repeat-search benefit; no new connector chosen.
- D14: additive fact/inference/recommendation blocks with exact quote/span and
  IDs. Preserve legacy verifier; verify each fact against its own quoted source
  with strict ordered wording/critical slots. Accept independently supported
  subset and explicitly report rejected blocks. Inference binds admitted facts
  and uncertainty; advice binds admitted premises, requested goal and conditions,
  never effect authority. Free translation beyond the bounded deterministic
  vocabulary remains unverified; matched synthetic cases record false rejects
  and fact recall separately from mechanical precision/provider quality.
- D16: bounded paginated canonical enumeration in one read snapshot before
  selection; per-source ranking/quota and channel diversity preserve late small
  sources and early important material. Calendar-week/rolling options use aware
  half-open timezone windows. Persist candidate/selected/model-omitted metadata
  separately with exact source refs; owner may open omitted source links without
  sending additional corpus to a model. Caps/unknown publication are explicit.

Acceptance before source edits: tests/test_daily_retrieval.py,
tests/test_daily_web_route.py, tests/test_daily_synthesis.py,
tests/test_daily_brief_selection.py. Native isolated PG/SQLite, fake providers
and literal loopback only. Existing archive/documents/vector, public-web/DNS,
claim-ledger/synthesis, Brief/report/source guards are the affected floors.
No full historical pytest, .env/private DB/accounts/paid calls, production DDL,
services/timers, external writes, push/master integration or human approval.

One independent read-only Deep Review of the accumulated committed package:
retrieval canonical/filter authority, planner/public query egress and DNS/ref
integrity, block verifier/premise safety, enumeration/selection/manifest/privacy,
native composition and evaluation provenance. Fix findings, narrow independent
P0/P1 rechecks before dependent work. Local collaboration is engineering evidence;
non-Codex Go/governed/human/provider gates remain separate and pending.

Rollback: disable new proposals/selection or restore compatible code, preserve
canonical IDs, old immutable documents, prepared/unknown operations, tombstones
and source snapshots. No database schema/checksum migration in this package.
