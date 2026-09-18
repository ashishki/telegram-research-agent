# PA — Personal Assistant Programme Design

Status: review_required. Planning depth: designed_slices. Risk: high.
The owner requested this design and its publication; exact hash-bound human
approval has not been recorded. Never manufacture that approval.

## Product outcome

One natural conversation unifies Chat, archive/web AI Search, attractive weekly
and topical Briefs, controlled Watch and confirmed Act. The full requirements
are `docs/PERSONAL_ASSISTANT_SPEC.md`; this compact map is not a replacement
for them. Do not stop after the first useful slice or declare an MVP the target.

## Current system and reuse

`src/prm/` remains the application seam; `src/bot/` is transport/presentation.
Reuse SQLite archive identity, evidence/citation contracts, saved-action
confirmation and tested external-watch delivery behavior. Existing archive
research must continue to work. Current free chat/synthesis gates and heuristic
short-lived dialogue need intentional redesign, not accidental flag changes.
The baseline CI failure is identified in the current handoff; diagnose first.

## Shape and responsibilities

Use a modular monolith with bounded capability adapters and a durable worker
for long/repeated work. No second bot, duplicated source-of-truth database or
unjustified microservice/vector-platform migration. New logical modules under
`src/prm/` may cover conversation, policy/capabilities, research, briefs,
connectors, actions, jobs and academic rules. Do not create empty frameworks
in advance of working vertical slices.

Request flow:
message -> ConversationState -> task understanding -> bounded plan -> permission
check -> typed tool results -> evidence/objects -> answer or ActionProposal ->
verification -> delivery receipt. Permission checks also run before data
leaves the system and immediately before an external write/send. The model
chooses among explicitly available tools; it never grants its own authority.

## Interfaces and invariants

- ConversationState: topic, object refs, versioned drafts/results, memory refs,
  pending proposal and jobs. A compressed summary is not write authority.
- CapabilityGrant: owner/account/resource/operation/data/provider, expiry and
  revision. Mail read is not mail write; voice is not an egress exception.
- ToolResult/EvidenceItem: status, sources/versions, timestamps, coverage and
  bounded evidence; distinguish absent, inaccessible, stale and partial.
- ResearchResult: useful answer, claim-evidence mapping, gaps and next steps.
- BriefDocument: immutable report version, period/timezone, sections, selection
  reasons, evidence and coverage. Telegram/HTML/PDF/Markdown use this SAME
  object. Reformatting does not silently regenerate or update facts.
- AcademicActionCandidate: obligation/opportunity, source, deadline precision,
  importance/applicability/confidence, lifecycle. Local done != Canvas submit.
- ActionProposal/Confirmation/ActionReceipt: exact arguments/versions, one-use
  approval bound to owner/content, actual provider result and reconciliation.
- WatchSubscription/Job: grant revision, schedule, quiet hours, cap, lifecycle,
  checkpoints, lease and bounded retries. Unknown send != failed send.

All schemas versioned, account identity preserved even for one operator,
cache/index derived and revocable. No unbounded raw-corpus or mail export.

## UX and briefs

Natural language, object-aware followups and clean topic changes are required.
A greeting is not an archive query; shorten means shorten the selected result.
Show truthful progress, cancellation and understandable connection/error state.
Weekly brief starts with what matters, actions and genuinely useful changes,
not 40 links. Personal relevance must have a reason. Do not invent read counts.
Telegram overview targets 1–2 screens; details unfold. Private mobile HTML is
accessible/light-dark; PDF has readable Cyrillic, hierarchy, sources and proper
page breaks. Visual inspection of real renderings is an acceptance gate.

## Academic integration

Implement the original `docs/UTD_ACADEMIC_INBOX_RESEARCH_HANDOFF.md` as a
subject module on common connectors, permissions, briefing and jobs. No reuse
of public-watch consent for private mail/Canvas. Verify institution policy and
provider scopes. Selected mail plus permitted assignments/events/announcements
come first; unsupported institution access remains an external blocker, not a
fake implemented connector. Preserve conflicting dates, unclear deadlines,
eligibility uncertainty and source versus local completion state.

## Failure and recovery

Test revoked grants while queued, expired confirmation, duplicate updates,
changed recipient/time, provider timeout, 429, injection in every source type,
missing/stale source, restart, DST and disk/restore failures. Never convert a
failed delivery into a visible-success state. Return useful partial answers;
make unavailable source coverage explicit. Finalized writes are not rolled
back by forgetting a conversation.

## Migration and rollback

Additive changes and measured rerouting, no rewrite of the archive or restart
of completed PRM-SN work. Rehearse migrations/backup restore on disposable
copies; production requires separate approval. New capabilities default off
until configured/granted. Each slice registry entry declares its own rollback.
Old report timers remain off. Read-only/archive fallback survives new-feature
outages. Avoid legacy handler growth; extract shared delivery only with tests.

## Vertical slices and acceptance

The 19 entries in `PA.design.json` are the dependency/scope registry, mirrored
by task IDs PA-00..PA-18 in `docs/tasks.md`. The existing commands are regression
floors, NOT sufficient feature evidence. Before starting each code slice,
register exact new acceptance test functions and add them to its executable
verification list/project verifier; show intended failures for required
semantic test-first changes. Split an oversized slice by revising the registry
and approval as necessary, not by silently exceeding its budget.

Independent product/program design review precedes exact human approval.
Slice/Test Critic/privacy reviews follow risk; full review is batched at phase
boundaries, never replaced by a model's self-review. Required human acceptance,
live account grants and release decisions remain explicit. Continue through
all ready assigned work after passed gates; independent external access blockers
do not cancel unrelated work or justify falsely claiming whole completion.

## Requirement coverage by slice

CHAT/UX -> PA-03; MEM -> PA-03/14; SEARCH/EVIDENCE/RAG -> PA-04/05/06;
BRIEF/VISUAL -> PA-07/08; WATCH -> PA-09; CONNECT -> PA-10/11;
ACADEMIC -> PA-12; PERM/SEC/ACT -> PA-02/13/17; MEDIA -> PA-15;
MODEL/COST -> PA-02/16; ARCH/OPS/MIGRATION -> PA-00/01/17;
EVAL/DONE -> all slices and PA-18. Read corresponding spec sections on demand.

No test result, working provider, visual approval or token-saving percentage
is asserted by this design. Full product acceptance needs current project
checks, adversarial/positive holdouts, real authorized integration and owner
usefulness/visual evidence.
