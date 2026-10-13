# ADR-020 — local implementation of the daily assistant backlog

Date: 2026-10-13. Status: records the active owner assignment; feature design
and human acceptance remain separate.

The owner explicitly lifts the research/documentation-only stop and assigns
sequential local implementation of the agreed daily backlog. Work uses a
dedicated branch and preserves other agents' changes. Mini App remains excluded;
the full Chat/Search/Brief/Watch/confirmed Act programme continues.

The current assignment supersedes the old ADR-015 implementation-before-all-
verification ordering: implement a coherent package, run the appropriate
checks, obtain one independent read-only Deep Review of the accumulated package,
fix findings, and proceed. P0/P1 fixes receive a narrow independent recheck
before dependent work. No repeated full review for routine corrections.

The first dependency-ready package is D01–D03. Its new acceptance files were
registered in docs/tasks.md before implementation. D56 follows the review gate.
Local synthetic PostgreSQL/HTTP fixtures are authorized; personal connections,
production, paid calls and external actions require separate explicit authority.
No earlier account/cutover/master-merge permission is expanded by this record.

The read-only reviewer selection remains governed by REVIEW_POLICY. Its
non-Codex Go route is a paid provider call; this new daily assignment does not
silently create a new paid scope. A scoped reviewer authorization or explicit
owner-selected local alternative must be recorded before the package gate is
claimed complete. No self-review, model substitution or fabricated receipt.

Engineering evidence updates daily backlog/handoff, never formal PA/PAI approval
states. Local tests, actual provider/account connections, visual evidence and
confirmed operator usefulness are reported separately. Research baseline saved
without content edits at `2a1236c`; initial source base is `23312b8`.
