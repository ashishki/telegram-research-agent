# Separate PAI-00 tooling maintenance audit

Status: local changes tested; independent audit pending. No feature approval.
Owner scope: local programme/reviewer invocation maintenance plus 30 total paid
Mimo calls; output/deadline amendments apply to design/rechecks. Nineteen calls
consumed before this audit. Public code/documents and synthetic fixtures only.

Review the complete critical-source list TOOLING_REFS in
tools/opencode_role_review.py. The packet includes policy, bridge, both review
clients, canonical checker, phase finalizer, strict acceptance runner and tests.
Model has no tools/write/commit authority. A real tooling PASS/ADVISORY and
unchanged source/report/result hashes are necessary before design promotion;
a fixture/diagnostic, missing audit or altered policy cannot unlock the gate.
Actual independent reports retain their precise scope and reviewed SHA.

Foundation report on a6a7d00: actual Mimo STOP_SHIP, 23308 input / 10638 output.
The 32/69/10 absence findings concern filtered phase input, not canonical files;
phase packets now retain full canonical registries. Remaining trust/no-skip P1s
are addressed by these code changes, with independent review/recheck pending.
Full architecture/feature reviews and exact human approval are separate gates.

Verification: latest native role/plan/acceptance/strategy suite 92 passed in
16.40 s; pinned design validator zero errors/warnings. Full historical suite
was not run. The corrected packet-size measurement used sys.path tools after
an auxiliary measurement command failed import; no provider call occurred.

Next: fresh independent program_design_review --tooling-review via the local
Role Runner on committed source, then all four programme/product phases.
