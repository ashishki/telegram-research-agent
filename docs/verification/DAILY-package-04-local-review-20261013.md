# D04 + D10 — frozen local Deep Review and narrow repair closure

One independent accumulated review: `/root/daily04_readonly_review`, fresh
collaboration process, read-only committed Git bytes and in-memory probes.
Requested model/effort: inherited active defaults, no override; observed: unknown.
No pytest, database, network, provider, credentials, edits or commits by reviewer.
This is local engineering evidence. Non-Codex Go/governed role/design/human
acceptance remains pending; no paid-route replacement is inferred.

Reviewed base `62a2909819c9062e8c2fec7d3dcb62bf58e32934`, head
`71704c43406ee5bff112d654a1329e0b0278f67c`; all23 changed files inspected.
Binary diff SHA-256:
`f62c4be950c46714c85bd005b4e402552299d870b1ff12ad07daaeb33f56ae38`.
Verdict: **STOP_SHIP, six P1, no P0**. These findings remain frozen:

| ID | Severity | Finding and independent evidence |
| --- | --- | --- |
| DAILY04-R01 | P1 | Brief appended batch before item validation; rejected privacy label still yielded1 evidence/unavailable coverage/empty scopes. |
| DAILY04-R02 | P1 | Research trusted collector resource/class after only owner check; archive canary reached fake synthesis with public scope and no private context grant. |
| DAILY04-R03 | P1 | Both native archive hook constructors omitted runtime binding; owner_local_archive was rejected and valid evidence disappeared. |
| DAILY04-R04 | P1 | Raw response aliases ignored canonical response_origin; private canary served as user_provided/empty scopes/zero current source checks. |
| DAILY04-R05 | P1 | Synthesis fenced input but omitted gathered read rechecks; revoked private source reached fake model/zero source-current calls. |
| DAILY04-R06 | P1 | Research stored scopes top-level; delivery read nested only. One stored scope became zero delivery scopes after revocation. |
| DAILY04-R07 | P2 | Received batches replaced by eligible projections before count; rejected projections disappeared. |
| DAILY04-R08 | P2 | Mail items and sync/count read in separate snapshots; concurrent same-count sync could pair old rows/new check time. Static race finding. |

Reviewer ran `PYTHONDONTWRITEBYTECODE=1 .venv-pai/bin/python -`, importing
committed modules with `git show`. Memory probes used stubbed boundaries;
all20 changed Python files compiled in memory (exit0). Initial namespace import
and diagnostic-attribute mistakes were corrected in memory before reported
probes. No independent live race reproduction. Implementer40 strict passes and
61 guard passes were inspected, not rerun or added as unique totals. Later
working-tree transcript was excluded from this committed-byte review.

Implementer reproduced R01/R02 in2 failing nodes (14.55s), R03–R06 in4 failing
nodes (20.32s), then6 regression nodes passed (26.37s). No dependent work began.
Repair implementation: append only validated Brief batches; server-selected
resource/class/connection/snapshot validation during gather and synthesis;
bind both native archive hooks; canonical response origins and input fences;
current read grants held through final model HTTP, after preparation; preserve
both result layouts in delivery and fail closed for protected copies without
read authority. Existing delivery attempts retain their payload/digest and
never dispatch again. R07 preserves received snapshots and separately counts
eligible/rejected projections. R08 binds mail rows/count/sync to one repeatable
read snapshot established before any SQL. No DDL/checksum rewrite.

Initial repair checks also exposed late snapshot-mode setup and a read-lock
held across model preparation. Both corrected before final repair freeze.
Delivery transport fixtures now explicitly authorize their synthetic source
and declare provenance; outcome/replay/race assertions stay intact. Missing
authority has its own denying test. Exact commands/failures remain in the
[package ledger](DAILY-package-04-D04-D10-20261013.md).

Narrow independent P1 repair recheck: frozen fixes
`2a20da43b5c54a3d71b54c559a4e61ed0cff0784`, binary diff from71704c4
`a4e7898ef753ff6697a57fede57f4de8b3d9dc400e8fee54ac7b1d08d9a334f6`;
fresh `/root/daily04_p1_recheck`, verdict pending.
That review exposed a new R06 fix regression: scheduled existing-attempt replay
overwrote its full prior row with SELECT1; committed AST probe produced
KeyError(destination_ref), sender_calls0. Native root reproduction failed at
the same replay, after1 initial synthetic send. Initial fixture mode error and
actual failure are dated in ledger. Fix0287f87 keeps SELECT1 in existing_attempt;
original receipt/digest stays intact. Five related strict nodes passed20.18s.
Additional narrow range2a20da4..0287f87, SHA-256
`46e9edb722d19ae5380aa049831061b9d941dfd5c1849db9f962abed9df7233e`;
same independent reviewer receives this exact two-file follow-up, closure pending.

Frozen narrow verdict on2a20da43b5c54a3d71b54c559a4e61ed0cff0784:
**STOP_SHIP for new P1 DAILY04-R09**, the R06 repair's scheduled receipt collision.
Original DAILY04-R01…R06 are independently closed for their original defects:

- R01 actual memory batch probe: rejected evidence/received/scopes all0.
- R02 actual _source_batch/_read_scopes: valid archive route accepted;16
  resource/privacy/owner/account/connection/scope mismatches denied.
- R03 both native constructor AST bindings root=self/root=root verified.
- R04 actual resolve: canonical private classes/scopes1 and input check1;
  revoked source denied. Origin absence fails closed.
- R05 actual model/source_current probe: prepare → FOR SHARE → send under
  live source lock → release; revoked source sends0.
- R06 actual provenance: nested and top-level layouts both retain1 read scope;
  missing protected-class scopes denied. Original loss repaired, R09 open.
- R07 memory counters received2/candidate1/selected1/rejected1 passed.
- R08 snapshot mode is first SQL; Graph summary uses one transaction, static
  and stub passed. Implementer DB race inspected, not independently rerun.

All14 repair Python files compiled in memory. Harness __name__/AST lineno
setup errors corrected before reported probes; no product or provider run.
Reviewer now checks only additional R09/R06 replay diff on0287f87; no second
full review or dependent implementation. Requested/observed defaults/unknown
and read-only/local route provenance remain unchanged.

## Final narrow closure

Independent `/root/daily04_p1_recheck` returned **PASS on
0287f87c16f400d1a0b48e7a20763d45486ffb65; no open P0/P1 in these repairs**.
R01–R08 stay closed as established on2a20da4; only delivery.py and its native
regression test changed afterwards. Additional R09 committed-code replay probes
on0287f87 returned the unchanged full prior attempt for sent/unknown/not_sent,
without dispatch. Missing effect lease and a corrupted digest were denied.
The old2a20da4 KeyError and STOP_SHIP remain historical evidence, not relabeled.

Verified range hashes:71704c4..2a20da4
`a4e7898ef753ff6697a57fede57f4de8b3d9dc400e8fee54ac7b1d08d9a334f6`;
2a20da4..0287f87
`46e9edb722d19ae5380aa049831061b9d941dfd5c1849db9f962abed9df7233e`;
combined71704c4..0287f87
`c299a852025776bbe84a2db556c464cefc856f83d28fe7b1d1f6fdb8dfe06a34`.
All14 initial repair Python files and both additional files compiled in memory;
final probes and git diff --check exited0. Command/provenance:
`PYTHONDONTWRITEBYTECODE=1 .venv-pai/bin/python -`, Git-loaded committed modules/
methods and memory stubs. No pytest/DB/network/provider/credential/file mutation.
Requested inherited defaults/no override; observed model/effort unknown. Root's
native fixture results were inspected, not independently rerun. No second full
review. Current non-Codex Go/governed/feature/human/live/production/release gates
remain open; this is independent local engineering closure only.
No second full review is requested. The20-turn transcript exercises mechanics
at71704c4 before source-boundary repairs, not provider quality or post-fix
security acceptance. Retained earlier package advisories stay dated.
