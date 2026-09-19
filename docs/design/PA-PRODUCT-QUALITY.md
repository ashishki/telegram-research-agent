# Product quality amendment — 2026-09-19

The owner requested integrating the brief/content/conversation diagnosis into
the active programme through PA-15 and starting implementation without repeated
cosmetic review loops. This authorizes local implementation and plan changes;
it does not invent formal design approval, live account/model consent or release.
The programme remains PA-00..PA-18; nothing after PA-15 is removed.

## One product contract

An answer helps the owner understand what happened, why it matters, what is
uncertain and what can reasonably happen next. A brief selects and explains
events rather than reproducing a feed. Factual support, editorial importance,
personal applicability and verified urgency are distinct. Missing priority
metadata does not forbid reasoned editorial selection. Missing deadlines do
not produce repetitive empty urgency labels. No invented personal relevance.

Candidate collection and visible story count have separate budgets. Separate
topic from time-window instructions; preserve period filtering before selection.
Merge accounts of an event, split multi-event roundups, exclude noise with
inspectable omissions, and retain material disagreements and temporal context.
Do not imply full weekly coverage from a bounded result set.

One immutable BriefDocument holds source excerpts plus editorial stories:
event headline, concise takeaway, explanation, selection rationale, optional
conditional next step, material caveat and exact supporting source anchors.
Its editorial content participates in identity, storage and all views.
Citation/quote validation alone is not semantic verification. The initial
implementation reserves two calls under the existing grant: generation and an
isolated source/content review. It reports `source_anchored_reviewed`, never
`fact_verified`; a missing review budget or failed review preserves the source
selection. It still requires
the separate content evaluation and authorized real-use gates below.

Short view gives takeaways; expanded view adds explanation rather than shorter
snippets. Discussion preserves story numbering and report identity. Explanation,
simplification, relevance and application are substantive responses. A bounded
set of local follow-ups is an initial implementation, not full natural dialogue.
Additional research is explicit and preserves the distinction from saved facts.
Tables compare alternatives, timelines explain sequence, and charts require
actual comparable measurements. Decorative scores are not evidence.

## Integration by slice

| Slice | Required user-visible outcome |
| --- | --- |
| PA-03 | Natural corrections and multi-turn questions resolve the current object; genuine explanations, not command memorization. |
| PA-04 | Retrieve relevant content across RU/EN topic aliases; measure missed important material separately from source support. |
| PA-05 | Verify material current claims from primary sources; unavailable providers yield a useful bounded answer. |
| PA-06 | Synthesize multiple sources and justify project applicability from actual current context; distinguish facts and recommendations. |
| PA-07 | Source-backed event selection, synthesis, explanation, noise/duplicate accounting, readable Telegram and meaningful report follow-ups. |
| PA-08 | Render the same editorial content; mobile hierarchy, comparisons and measured visualizations; formats never compensate for poor content. |
| PA-09 | Notify on a meaningful change and explain what changed and why it matters; repeated evidence is not a new event. |
| PA-10 | Explain mail threads, requested decisions and supported deadlines; distinguish obligations from promotional opportunities. |
| PA-11 | Explain schedule implications, conflicts and options with source timezones; no event dump or fabricated urgency. |
| PA-12 | Separate academic obligations, optional opportunities and reading; explain eligibility uncertainty and conflicting deadlines. |
| PA-13 | Convert a discussed finding into a concrete editable proposal with rationale, then exact confirmation and a truthful result. |
| PA-14 | Inspectable interests, projects and length/depth preferences; feedback changes future selection only under explicit memory policy. |
| PA-15 | Voice/document/image questions continue the same discussion; readable explanations and page/source references survive modality changes. |
| PA-16..18 | Measure quality before cost optimization; recover exact report objects; accept the complete programme on actual use. |

## Development and evidence

The first correction spans the active brief path, its narrow source-bound
transport, source DTO/schema, topical query normalization, focused tests and
this programme's task/design records. It permits these local edits without a
separate approval for every file. Keep ownership, grants, retention and unknown
delivery boundaries intact. No production access, migration or deployment.

Run the new content tests with the existing PA-07 suites and focused-prm once
the coherent change is complete. One independent slice review covers the batch;
recheck only changed P0/P1 findings. Accumulate Deep Review at the established
phase boundaries. Human/provider/mobile gates remain explicit, but their
absence does not stop independent local implementation through ready slices.

Separate four acceptance dimensions: factual support/coverage, editorial
usefulness, personal applicability, and conversation/mobile usability. Use
sanitized source packets and actual generated outputs, not just prepared prose.
Include noise, duplicates, contradictions, quiet/partial weeks, missing personal
context and multi-turn refinement. Freeze held-out cases before tuning; validate
judge output against one 0-4 scale and calibrate it against owner ratings.
Hallucination, missed critical supported information, feed dumping or broken
follow-up cannot be averaged away by presentation scores. Synthetic passes do
not establish live provider quality or owner acceptance.

Initial verification command:

`PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_assistant_brief_editorial.py tests/test_assistant_briefs.py tests/test_assistant_report_dialogue.py tests/test_prm_synthesis.py`
