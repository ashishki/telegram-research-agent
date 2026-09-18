# Review Policy — PA

Updated: 2026-09-18
Playbook pin: d570163ab17ec3b4245187c778f1e8d89af9690f
Historical policy: `docs/REVIEW_POLICY.before-pa-20260918.md` (unchanged snapshot).

## Authority and execution

Standard governance, designed_slices programme. Human remains final authority
for exact design, high-risk slice acceptance, account/runtime permissions and
release. Direct implementer writes; independent reviewer reads only. Children
never commit/push, self-review or grant approval. A drafting agent cannot record
its own design as approved. Existing source/privacy/runtime gates stay intact.

## Required reviews

Before capability implementation: independent product_design_review and
program_design_review of the paired PA design, followed by hash-bound human
approval using Feature Workflow. For the four governed feature roles
(product_design_review, program_design_review, slice_review,
maintainability_review), use `tools/run_codex_role.py run` from the pinned kit.
An invalid runner execution is missing evidence; do not silently fall back to
a direct reviewer command. Supply an actually available approved review model
and reasoning effort (high for high-risk work); record the observed identity,
reviewed commit/diff, inputs, verdict, findings and artifact hashes.

For semantic changes use a focused Test Critic and relevant slice review.
Privacy/security review is mandatory on new egress, OAuth/secrets, retention,
confirmation/writes, source-fetch boundaries, scheduling or recovery. Tests must
include useful positives as well as denial/attack cases. A keyword assertion
or model judge cannot prove end-to-end correctness.

## Proportionate batching

Within a phase review the actual changed surface and tests. Batch the full
META -> ARCH -> CODE -> CONSOLIDATED chain at these accumulated boundaries:
foundation (PA-00..02); chat/search (PA-03..06); brief/watch (PA-07..09);
personal sources (PA-10..12); actions/memory/media (PA-13..15); final reliability
and acceptance (PA-16..18). These are risk checkpoints, not a mandatory call
fan-out after each trivial edit. Immediate safety review applies before a
changed risky boundary is exercised or dependent work proceeds.

Preserve old domain-specific gates when maintaining the corresponding legacy
surface. Do not reread every historical report unless a concrete finding needs
it. Freeze findings, fix P0/P1, rerun affected evidence and do not consume
unbounded correction rounds. Missing independent review remains pending.

## Completion evidence

Exact changed files and SHA/diff; new acceptance tests plus appropriate
existing tier; commands and exit/results; visible before/after UX where relevant;
privacy/cost/recovery evidence; limitations; human/live decisions. All PA code
slices must replace generic regression-only evidence with their feature-specific
checks before acceptance. Full historical pytest runs remain prohibited.

Visual report acceptance requires actual Telegram/HTML/PDF render inspection,
not just a schema or model judgment. Real account integration and owner
usefulness remain separate from synthetic/CI evidence. A passing planning
workflow does not imply a passing product or authorize release.
