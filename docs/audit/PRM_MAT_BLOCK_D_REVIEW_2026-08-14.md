# PRM-MAT Block D review — 2026-08-14

Scope: PRM-MAT-10 and PRM-MAT-12, plus their shared reader path.

The initial deep review identified two integration defects: a derived
professional section was not reliably mapped to the operator workflow, and
the Telegram reader did not display it. It also identified over-broad source
classification for lookalike GitHub/docs hosts. The corrective slice maps one
matching section deterministically, renders its public focus (including the
career workflow's `recurring_requirement`), and accepts an official source
classification only for `github.com`/subdomains or explicit operator-supplied
`official_relation=true`.

Targeted verification after correction:

`PYTHONPATH=src python3 -m pytest tests/test_primary_source_verification.py tests/test_prm_professional_workflows.py tests/test_memory_research.py tests/test_handlers.py -q`

Result after the career regression correction: `87 passed in 12.48s` for the
memory/Telegram slice and `23 passed in 1.99s` for the primary-source/DTO
slice. No full-suite run was performed under the global operator policy. The
correction made no network call, DNS lookup,
redirect follow, provider call, durable write, canonical archive mutation, or
service action.

Boundary: MAT-10 remains fixture-first verification planning. Redirect policy,
response-size limits, a transport fake, and any live execution are not claimed
here; they require a separately approved live-fetch/trust-record scope. This
Block-D review can close only for the deterministic plan and reader-integration
slice, not as evidence that external verification was performed.

Reviewer runtime assignment: requested by procedure, effective model/reasoning
assignment was not exposed by the runtime and is recorded as unverified.

Repeat read-only review after the career regression correction found no
actionable findings. It confirms that Block D closes for this deterministic,
fixture-first plan/reader slice only; it does not authorize live verification,
external cache execution, provider use, or a runtime/service change. The
reviewer did not run tests or access network, database, or services; effective
runtime assignment remained unverified.
