# D07/D08/D09 — frozen independent review and repair ledger

Fresh read-only local reviewer `/root/daily05_readonly_review`; requested inherited
defaults/no override, observed identity/effort unknown. Full committed range
3bb16f35876b3bf1cf49516caa7775fb2dea5aa1..caefb455c009492f3bf5edf1f924b4d75df8666d;
binary SHA-256225f1dcca7d0693eadc8cb354f3b9b2f3b34b9f2960b53a87efed1aa56d78fc9.
Reviewer observed29 files/1326 insertions64 deletions for git diff; root commit
reported1335/73 with rewrite formatting. These stat presentations are distinct;
the frozen byte hash/SHA is identical, not corrected by changing source evidence.

Verdict **STOP_SHIP: seven P1/four P2, no P0**. Frozen findings:

| ID | Severity | Finding and independent evidence |
| --- | --- | --- |
| DAILY05-R01 | P1 | Ordinary `/research` constructs unselected PI facade; archive transport lacks read scopes/selection pause guard. Static native path inspection. |
| DAILY05-R02 | P1 | Saved evidence/result source versions not checked against completed canonical edit/delete/outage; scope guard checks current selection only. Memory/static probe. |
| DAILY05-R03 | P1 | Project list/show/weak applicability drop context source-binding privacy/scopes, including transitive/generic memory routes. Two memory probes served private goal as user_provided. |
| DAILY05-R04 | P1 | Economical fallback selected automatically without paired promotion after balanced cooldown. Actual ModelProfiles memory probe. |
| DAILY05-R05 | P1 | Revision/tombstone key includes resource; overlapping resource rev2 resurrects canonical deletion rev3. Actual apply_page with SQL-dispatch stub. |
| DAILY05-R06 | P1 | Selected top-k/window/reactions filter usernames without canonical channel ID. Static path inspection; reused name can match wrong ID. |
| DAILY05-R07 | P2 | Comparison stamps current role/policy on old observation without observed binding. Memory probe accepted unobserved judge/policy V999. |
| DAILY05-R08 | P1 | Relationship quotes missing from project deletion dependencies and fresh get checks. Confirm SQL stub registered description dependency only. |
| DAILY05-R09 | P2 | `/budget` json.dumps cannot serialize PostgreSQL SUM Decimal. Memory TypeError probe. |
| DAILY05-R10 | P2 | `/projectconfirm` commits wrong-kind memory preview before kind check. Static transaction path. |
| DAILY05-R11 | P2 | Import quota day taken from packet checked_at, permitting historical date quota bypass. Static path. |

Reviewer compiled26 changed Python files in memory, used committed Git-loaded
code and memory/SQL stubs via `PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'`;
Git2.34.1/Python3.10.12, functions.exec/exec_command runner. Harness missing
descriptor/owner/module setup errors corrected before successful probes. No
pytest, DB, HTTP, session, credential, file mutation, commit or push. Root's67
strict passes and other tiers inspected, not independently rerun. Post-freeze
working-tree runbook/receipt excluded. No second full review.

Root reproduced R01/R03/R04/R05 in4 native failing tests22.28s; R02/R06/R08 in3
failing tests13.74s. Repairs use one canonical epoch/state snapshot (including
outage/lag), exact identity filtering, ordinary selected facade and guarded
source egress, transitive project provenance/generic memory validation, common
canonical tombstone fence and relationship deletion edges. All economical
candidates check promotion; role/policy binding is captured at actual attempt;
priced aggregates normalized, kind check atomic, quota day actual execution.
Legacy unknown receipts are preserved; missing selected-source snapshots fail
closed. Existing historical results remain stored; current serving needs valid
source state, broader historical UX remains D19.

At full-review completion repair source SHA/narrow verdict were pending. Required R01–R06/R08 must
be independently rechecked before dependent work; supporting P2 changes may be
inspected in that narrow range, not a repeated package full review. Non-Codex
Go/governed/human/provider/production gates remain separate and open.

Frozen repair source9f5feec9c109c76cc73839259ba626547d52b7eb; binary diff from
caefb45 SHA-256154af44af79c14c82a691f3d98ab812d0498a89ab1fab5d4b16f5da71bfe4371,
26 files/416 insertions76 deletions. Fresh independent local read-only narrow
reviewer `/root/daily05_p1_recheck`; same inherited defaults/observed unknown;
checks seven P1 and supporting P2 fixes only. Initial verdict STOP (R12). No second full
review or dependent source work, no paid/governed/human receipt substitution.


Initial narrow recheck on9f5feec: **STOP**, new P1 DAILY05-R12. Original frozen
R01–R11 closed; R02 original snapshot invalidation closed but reader race added
by that repair remains separately R12. Independent closure evidence:

| ID | Narrow closure evidence on9f5feec |
| --- | --- |
| R01 | Selected native factory rejects missing read scope before retrieval; preserves snapshot/scope; unbound derived route blocked. Synthesis missing snapshot rejected before reservation; Brief/Watch bound readers. |
| R02 | Canonical state hash changes with epoch/outage/lag. Snapshots traverse result layouts, raw origins, focus/synthesis/delivery, Brief/Watch. Final reader race remains R12. |
| R03 | Actual transitive project get, weak applicability and generic memory inspect/export preserve private classes/scopes/snapshots; revoked ancestor blocks child. |
| R04 | Actual select rejects unpromoted economical fallback after balanced cooldown. |
| R05 | Actual apply_page global revision lookup blocks overlapping resource rev2 after tombstone rev3; no canonical text writes. |
| R06 | Actual FTS/reaction SQL uses exact ID+username before LIMIT and COUNT; window uses same filter. |
| R07 | Actual validator rejects missing/mismatched observed role/policy binding; preparation checks binding drift. |
| R08 | Fresh get rejects deleted relationship source; confirmation registers quoted result→project memory dependency for existing deletion traversal. |
| R09 | Actual billing view Decimal340→int340; invoices/overage unknown preserved. |
| R10 | Actual expected_kind rejects note before put/consume in confirmation transaction. |
| R11 | Actual apply_page historical packets charge current UTC execution day; quota1 blocks second packet. |

R12: reader.py49 source_current transaction ends before rendering; final artifact
transaction91 checks deletion/index and reads body99 without a fresh snapshot.
Git-loaded actual artifact+source_current with transaction/context stubs allowed
cooperating canonical edit after early lock release, then returned OLD PRIVATE
SOURCE. Snapshot checked once. Window includes renderer timeout18s. Required
fix is final source_current with manifest scopes/snapshot held through read_bytes.
Root native outage-after-render regression fails before the repair and passes
on the tiny fix; exact argv/results in package ledger.

Initial narrow runner `/root/daily05_p1_recheck`, requested inherited defaults/no
override, observed unknown; Git2.34.1/Python3.10.12.26 changed Python files compiled
in memory; probes via PYTHONDONTWRITEBYTECODE=1 python3 heredoc and Git-show code.
One billing harness missing SQL default args was corrected before successful
probe. All final harness probes exit0. Root tests inspected, not rerun. No
pytest/DB/HTTP/credentials/sessions/file mutation/commit/push by reviewer.

R12 tiny fix frozen8f193bb8feba12f973e0b80730e72e8ad485a817, base9f5feec;
binary SHA-25625db22208d787f0103677b59aa9886f8f37cb558b0a7c0cf4a5a1fe5cce0e5a7,
2 files/38 additions. Same independent reviewer tasked with R12-only follow-up;
final verdict PASS, R12 CLOSED on8f193bb. Original closed defects remain closed on their frozen range;
no dependent work or second full package review. Final source read repeats
source_current inside the artifact transaction through body read, returning
None on denied/stale source. Non-Codex Go/governed/provider/human gates remain.


Final R12-only narrow result: **PASS, no new P0/P1 in this fix**. Actual
Git-loaded artifact and source_current memory probes: edit/outage/grant revocation
between checks and missing snapshot all return None without body read. Unchanged
source reads body while source context is held, both snapshot checks run. Each
scenario releases contexts. Both changed Python files compiled in memory;
compile/probes exit0. Same inherited/default runner and observed unknown; only
committed bytes, handoff excluded. Reviewer did not run DB/HTTP/renderer/tests,
provider/services/credentials or mutate files/Git. Root's native tests are a
separate evidence layer. Required local critical gate closed before next package;
Go/governed/human/provider acceptance remains pending. Combined repair diff
caefb45..8f193bb SHA-2563fe81128007679ae7889f2180f8eb583ca139ff4675aa3597a85268391317c0e.
