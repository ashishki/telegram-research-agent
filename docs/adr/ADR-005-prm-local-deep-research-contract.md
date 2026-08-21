# ADR-005: PRM Local Deep Research Contract

Status: accepted_for_manual_runtime
Date: 2026-08-21
Approval: operator instruction to implement the local deep-research slice

## Context

Archive answers could be citation-grounded while still being unhelpful: the
first few lexical matches were treated as the whole research space, and a
model synthesis could only reason over that narrow set. A public architecture
example suggested a useful phase discipline: plan, gather, gap-check,
synthesise, verify.

The example's self-hosted web-search, extraction, Docker-sandbox, and agent
runtime are not in scope for PRM. This decision adopts the phase discipline
only for local archive research.

## Decision

For `archive_to_action`, use this bounded flow:

1. `plan`: construct deterministic phrase-preserving local query variants.
2. `gather`: retrieve and deduplicate at most 32 local archive candidates.
3. `gap-check`: classify source roles and identify missing direct-topic or
   replayable-practice evidence. When a gap exists, run at most one additional
   local archive-search wave with targeted variants.
4. `synthesise`: rank the gathered pool deterministically. If the existing
   provider-egress switches are enabled, a model receives at most 12 cited
   excerpts and may select at most eight supplied source IDs. It cannot add
   facts, URLs, or actions. A deterministic role-aware fallback is mandatory;
   when no source supports an action, it exposes at most three clearly marked
   context sources rather than presenting a long weak-match list as evidence.
5. `verify`: retain archive response contracts, source-role gates, claim
   verification, and final-answer verification.

The response contract receives only the selected sources. Private receipts may
record bounded counts, IDs/hashes, retrieval provenance, and gap-check status;
they must not export raw corpus text.

## Boundaries

| Control | Decision |
| --- | --- |
| Canonical archive DB | read-only |
| Candidate pool | maximum 32 local rows |
| Provider context | maximum 12 cited excerpts, 320 characters each |
| Provider authority | choose supplied IDs only |
| Visible evidence | maximum 8 actionable sources or 3 context-only sources |
| Additional search | one local gap-search wave within request budget |
| External embeddings | not used |
| Hosted vector service | not used |
| Live web search/extraction | not used |
| Containers or Docker socket | not used |
| Durable writes | not performed by research flow |

## Rollback

Disable the optional synthesis switches to use deterministic source selection.
The local search and gap-check remain read-only. Reverting the application and
planner modules removes the feature; no archive restoration is required.

## Validation

```text
PYTHONPATH=src python3 -m pytest tests/test_prm_research_planner.py tests/test_prm_application.py tests/test_memory_research.py -q -k 'not retrospective_project_question_uses_archive_evidence'
python3 -m py_compile src/prm/research_planner.py src/assistant/memory_research.py src/prm/application.py
```

The excluded test is a pre-existing date-sensitive fixture: its requested
relative time window is now older than the fixture evidence.

## Non-approvals

This ADR does not approve PRM-19 dogfood, live web research, a SearXNG/Tavily
adapter, URL extraction service, Hermes or other child agent runtime, Docker
socket access, external embeddings, hosted vector storage, production archive
writes, or release claims.
