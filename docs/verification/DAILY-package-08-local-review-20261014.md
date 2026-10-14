# D19/D20/D21/D58 — frozen independent local review

One accumulated read-only review by fresh `/root/daily08_readonly_review`.
Inherited active model/effort, no override; observed identity/effort unknown.
Reviewer independently confirmed clean Git/branch and base1db5034c8b2374add70d16ef6a354ac26f0bc505
→ source dbf49580c292cb433edefe2fddff3adb60c8bff0:36 files/+2357/-106,
binary253298 bytes/SHA256 d654716c828daafdae18b27502ffd31b31e1e5a4ed53e766a99afea5edefc402.
Git/source/docs/test text reads only; no tests/runtime/DB/network/keys/mutations
or acceptance. This is local collaboration engineering evidence, not non-Codex
Go/governed/design/human/live/client/visual/operator acceptance.

**Frozen STOP:0P0/7P1/2P2.** Source-derived schedules below were not claimed
as reviewer-executed reproductions. Three action-preview failures reproduced
on genuine base are retained limitations, not new regressions or these IDs.

| ID | Priority | Frozen finding and reproducer |
| --- | --- | --- |
| DAILY08-R01 | P1 | delivery.py383/460 checks project/source but not memory immediately before HTTP; correct v1→v2 or expire after initial provenance and plain/rich/edit can send v1 |
| DAILY08-R02 | P1 | memory_dialogue.py39/53 and documents.py63 validate, record raw response, then origin/edges separately; forget/correction between operations leaves orphan text/history after refusal |
| DAILY08-R03 | P1 | delivery.py118/telegram_rich.py180 re-render any document_binding as Brief; feedback/export/comparison/topics/apply/refresh/why signals lose actual view/status/diff on wire |
| DAILY08-R04 | P1 | brief.py112/134/163 binds rules only for included stories, after editorial HTTP; excluding rule loses dependency and private-backed selection reaches model without that memory/source authority |
| DAILY08-R05 | P1 | source_access.py32 reloads passed historical item as head; old export/view after correction+refresh v2 can use v2 memory/project bindings while serving v1 bytes |
| DAILY08-R06 | P1 | documents.py22/48/100 and storage/briefs.py82 lack original native input pointer/dependency; edit/delete original weekly input, then direct/named view/export/refresh/save bypasses the reply/control fence |
| DAILY08-R07 | P1 | composition.py349/ingress.py427/jobs.py198: forget after atomic model response but before completion deletes parent; complete rejects but leaves running300s lease, blocking next assistant claim; diagnostic chunks have same boundary |
| DAILY08-R08 | P2 | feedback.py97/109 reads story pointer but reaction record omits it; reaction to explanation2 becomes whole-document event |
| DAILY08-R09 | P2 | feedback LABELS/runtime parser omit documented “это знаю”, “слишком длинно”, numbered “не моя тема пункт2”; fallback instead of exact event |

Repairs and scoped checks follow on a separate SHA. Critical R01–R07 require
an independent narrow recheck before D22/D23/D24/D57. The full STOP stays frozen;
do not repeat the accumulated review after each fix. Any remaining variants,
limitations and exact narrow SHA/diff will be appended here after the verdict.

## First narrow recheck — frozen STOP R02/R03

Same independent read-only agent, inherited defaults/no override, observed
unknown. Independently verified clean Git and dbf4958→
b2092d6ad4218066567500aee8d33ae4b3e82784:18 files/+558/-57,
binary78154 bytes/SHA256 a49896ae916871a9707bfb18070caab227a6cfd6c41f851203630ff501ea7511.
Only R01–R07 and direct repair risks; adjacent R08/R09 viewed. No second full
review, reviewer tests/DB/network/mutations or acceptance.

Closed R01/R04/R05/R06/R07 and both R08/R09. No new separate P0/P1 in checked
delta. **STOP: two remaining P1 variants, original R02/R03 IDs retained.**

- R02: refresh still used BriefRuntime.answer→legacy application
  record_response→bind_visible→record_origin. Forget current rule/project after
  raw response and before binding rejects publication but leaves unlinked
  response/history. Initial weekly shares this sibling. Require source-bound
  manifest first, atomic response/origin/edges, and no orphan on refused binding.
- R03: large refresh compaction drops brief_refresh.performed, retains
  brief_view=telegram, and delivery re-renders full native rich instead of its
  actual status/diff. Preserve a bounded view discriminator; do not add a large
  dynamic diff to the compact header. Add real compacted refresh wire checks.

No dependent block started. Next recheck scope is only these two variants and
the direct delta. Earlier five critical/P2 closures remain bound to b2092d6.

## Final narrow R02/R03 recheck — PASS

Same independent read-only reviewer verified clean Git/branch and
b2092d6→b00a5cbcc20d5b530631fed8f2a10eade0fa0242:7 files/+184/-18,
binary24033 bytes/SHA256 0d360a2db54652248fe29e6cdc623c4c372f73f0ccd96bb3182ddb9d434728e1.
Scope only remaining R02/R03 variants and direct delta; no new full review,
reviewer tests/runtime/DB/network/keys/mutations or acceptance. Requested model/
effort inherited active defaults/no override; observed unknown.

**PASS: R02/R03 closed, no new P0/P1 in scoped fixes.** Five earlier P1 and
R08/R09 closures remain on b2092d6; all9 package findings closed locally.
No open local package P0/P1, no dependent work before this verdict. Original
full STOP and first narrow STOP stay frozen. Non-Codex Go/governed/design/human,
live/client/visual/operator gates remain open.

- R02: source-bound immutable manifest commits first, then both native weekly
  and refresh use atomic response/origin/dependencies. Forget before response
  refuses it; forget after response follows its graph. Failed visible binding
  explicitly removes refused response/origin/history. Failed refresh returns
  unavailable without announcing a published new version. Untouched legacy
  application seam remains a separate limitation.
- R03: bounded brief_view=refresh survives compact projection; exact compatible
  HTML/text is selected before HTTP even when full diff stays in diagnostics.
  Actual status/diff is preserved, unknown/fallback fences unchanged.

Implementer6 targeted passes54.96s and30 publication passes146.47s correspond
to these boundaries, overlap, and are not reviewer-executed reproductions.
Production concise wire and explicitly synthetic same-document multipart
appendix are separate evidence. No provider/client/usefulness acceptance.
