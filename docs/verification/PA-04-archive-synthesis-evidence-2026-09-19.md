# PA-04 archive synthesis evidence — 2026-09-19

Status: locally verified, synthetic/offline implementation of the PA-04 archive
retrieval-to-synthesis boundary. This evidence does **not** change the
mechanical design state `review_required`, create a durable grant, enable a
provider, access a credential/account/archive, modify a database, or claim
runtime, owner-usefulness, release, or human acceptance.

## Implemented boundary

- The application keeps the existing measured local archive retrieval and
  deterministic source-backed renderer as its default. It now exposes separate
  retrieval/generation measurements (candidate and selected-source counts,
  query attempts, generation status and non-durable transport facts) without
  recording source excerpts or the user question.
- `ArchiveEvidenceContext` accepts only the current archive contract's selected
  direct/partial/adjacent findings. Every bounded excerpt must have one HTTPS
  source reference and match an evidence-quality support span. Duplicate,
  oversized, malformed, detached, or unbound input invalidates the entire
  context; it is never partially repaired or sent. Its canonical digest detects
  mutation between selection and transport.
- `ArchiveSynthesisAccess` carries the exact paired PA-02 reservations for one
  OpenAI request: `model.generate` for current `user_provided` text and
  `model.context_egress` for `private_archive`. Both must be allowed, sealed,
  current, have the same owner/connection and opaque operation reference, and
  originate in the same registry. A chat-only PA-03 reservation cannot be
  substituted.
- The dedicated PA-04 transport accepts only those two typed values, requires
  both explicit feature gates and the active credential's opaque connection
  ref, commits the paired reservations atomically, makes at most one request,
  and records accepted versus unknown outcomes. It does not accept a raw
  context, caller-supplied client, fallback provider, or retry.
- Generated text is published only after the existing claim/citation verifier
  succeeds, every direct source remains visible, no archive-only forbidden
  sections leak, and a direct hit is not replaced by a blanket no-evidence
  answer. Rejection, missing authorization, malformed evidence, provider
  unavailability, or unknown outcome retain the useful local source-backed
  response rather than inventing a citation or claim.

The active Telegram runtime has a narrow default-deny ingress seam. It calls an
optional injected paired-access provider only after the local router selects an
archive intent, then forwards only a valid `ArchiveSynthesisAccess` through the
PRM handler to the application. Chat and current-fact turns never ask that
provider; omitted, malformed or failing access remains the local renderer. The
runtime does not mint a grant or credential. No job, service, timer, production
DB, or live provider was changed in this slice.

## Verification

All checks used synthetic source IDs, URLs, excerpts, grants, operation refs,
credentials and a private fake client-builder seam. No real key, provider,
Telegram polling, archive database, live job, account, or network action was
used.

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_prm_application.py tests/test_prm_synthesis.py \
  tests/test_prm_intent_archive_contract.py tests/test_prm_research_planner.py
# 48 passed in 2.48s

python3 -m py_compile src/prm/application.py src/prm/contracts.py \
  src/prm/archive_context.py src/prm/archive_synthesis_transport.py src/prm/synthesis.py

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_prm_application.py tests/test_prm_synthesis.py \
  tests/test_prm_intent_archive_contract.py tests/test_prm_research_planner.py \
  tests/test_prm_bot_dispatch.py tests/test_assistant_conversation.py
# 65 passed in 5.10s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 342 passed in 71.14s (0:01:11)

git diff --check
# passed; no output

python3 tools/check_personal_assistant_plan.py
# PA plan: 19 consistent slices; schemas, references, dependencies and context limits passed.
# Design state: review_required; no product, human-approval or runtime claim.

python3 tools/playbook.py --check-pin
# Playbook pin verified; no model, hook or application runtime enabled.
```

The targeted tests cover an English and a Russian cited source-backed
generation, result publication through the application, retrieval/generation
measurements, paired reservation enforcement, the context supplied to the fake
transport, a wrong citation/false refusal, and a detached-source holdout that
reaches no transport. Retrieval phrase/ranking behavior remains covered by the
existing intent and focused PRM suites.

During preflight, two guessed test paths (`tests/test_prm_archive_contract.py`
and `tests/test_archive_relevance.py`) did not exist and each command ran zero
tests. They were immediately replaced with the repository's actual focused
paths above; this is a command-selection correction, not a product pass/fail
result. The prohibited full historical pytest suite was not run.

## Independent review and remediation

Fresh read-only Role Runner `slice_review` examined initial commit
`0cdd5c100e52b5dbcc6eb738e4217c3bf0b18f32` (`961d1ee..0cdd5c1`) and returned
`STOP_SHIP`. Per the owner-requested review order, the requested and observed
telemetry was `gpt-6-astra` / `high`; run
`20260919T025631Z-slice_review-8edc2055` was validated in a read-only sandbox
with an unchanged workspace. Its report SHA-256 is
`14c175002208077fe11bb6ce7b8670bad46a87dea54eb4b0e424ad16eef1f5b4` at
`.playbook-artifacts/runs/20260919T025631Z-slice_review-8edc2055/report.md`.
It is review evidence only, never design, completion, runtime or release
approval.

The scoped remediation addresses all four P1s and the P2 telemetry advisory:

- context now requires the exact selected `evidence_id` and source URL plus
  `local_archive_provenance=True`, and sends the canonical bounded
  evidence-quality support span rather than a separately truncated or appended
  display summary. Ambiguous duplicate spans, detached IDs, unprovenanced
  evidence and mutation probes all fail before transport;
- generated archive claims require an explicit cited selected source and every
  substantive token to occur in its exact span or a deliberately tiny
  inflection/paraphrase allowlist. This rejects a relationship inversion with
  the correct URL while allowing a bounded useful paraphrase. The generic claim
  ledger remains a diagnostic; publication records this stricter source-bound
  verification method rather than treating lexical overlap as semantic proof;
- canonical support spans make an ordinary 260-character display ellipsis
  irrelevant to model context; a long-excerpt holdout succeeds while appended
  display text never enters the provider input; and
- the registry scope was explicitly amended, while retaining mechanical
  `review_required`, to include the default-deny bot/handler seam and its tests.
  Text, embedded-transcript and voice-transcript paths obtain a typed pair only
  after archive routing. The active ingress test exercises handler → actual
  retrieval → context binding → synthetic provider result → publication.
  `focused-prm` now registers `tests/test_prm_synthesis.py` rather than leaving
  the slice's own security regressions outside its required tier.

After remediation, only synthetic/offline checks were rerun:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_prm_synthesis.py tests/test_prm_application.py \
  tests/test_prm_bot_dispatch.py tests/test_prm_utd_dispatch.py \
  tests/test_prm_intent_archive_contract.py tests/test_prm_research_planner.py \
  tests/test_openai_provider.py
# 97 passed in 6.90s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 354 passed in 80.75s (0:01:20)

python3 -m py_compile src/prm/application.py src/prm/contracts.py \
  src/prm/archive_context.py src/prm/archive_synthesis_transport.py src/prm/synthesis.py \
  src/bot/bot.py src/bot/handlers.py src/bot/prm_handlers.py tools/test_tiers.py
git diff --check
# passed; no output
```

## Independent rechecks and final observed verdict

All reviewer runs below were fresh Role Runner `slice_review` processes with
requested and observed `gpt-5.6-terra` / `high`, Codex CLI `0.154.0`, a
read-only sandbox and an unchanged workspace. Their temporary-directory
restriction meant they could not independently start `focused-prm`; that is an
environment limitation, not a test result. Every reviewer report is evidence
only and grants neither design approval, slice acceptance, runtime authorization
nor release approval.

1. Run `20260919T031019Z-slice_review-8e75ddb8` reviewed remediation
   `ad35e50287cf625770d1b330f2473f6b0eb58206` and returned `STOP_SHIP`
   (report SHA-256
   `a40240cdc5e2d960ed6d95a072143a0adfa0397a7b457326e7d463769617aeb4`).
   Its P1s required actual Russian/English retrieval/ranking holdouts and
   truthful partial/false-refusal/no-result publication paths. Commit
   `7c8c3fe5feaf89851d3b401f898374694dce174d` adds those offline holdouts and
   source-backed partial fallback protection.
2. Run `20260919T032254Z-slice_review-a1f4b3ec` reviewed `7c8c3fe` and
   returned `STOP_SHIP` (report SHA-256
   `992ea94831273d2245838034c76bccfd2764841995ec771de279bf8af96ec5c9`).
   Its P1s required relation-order preservation and a publication set limited
   to the exact provider context. Commit
   `901996ee2943709c2a90a9b066376ec6d13e5965` requires an ordered selected
   span per cited factual sentence and limits rejected-output fallback to the
   exact archive contract selection.
3. Run `20260919T033145Z-slice_review-893264df` reviewed `901996e` and
   returned `STOP_SHIP` (report SHA-256
   `21b58d35ad54c19817606688398a6062bd8841e6fb9ff2dc660a80719ebd97b8`).
   Its P1 found a polarity mutation: a positive answer could omit a cited
   source's `no`/`not`/Russian negation. Commit
   `c4f828cc6c09806de82eca42b9fb1447693f5a5c` preserves negation as a factual
   polarity signal, with English and Russian synthesis and application
   publication mutation tests.
4. Run `20260919T034333Z-slice_review-5895c5cd` reviewed `c4f828c` against
   `081dded..c4f828c` and returned `ADVISORY`, with no P0/P1 design or boundary
   blocker (report SHA-256
   `a1bdc17e33cba1a89d280ca473e9456bb10f8af646055a0b71666c1e8089068a`).
   It confirmed the default-deny paired access, local fallback and selected
   evidence boundary. Its two follow-ups remain open: abandon a pre-reserved
   pair on skipped/exceptional application outcomes, and add an active
   `run_bot` group/non-private message regression for non-invocation of the
   access provider.

The earlier `901996e` review also recorded two P2 limitations that remain
visible rather than being silently closed: the bilingual holdout is an
offline in-memory corpus (application wiring, not FTS recall quality), and
`ResearchResult` remains deferred while measurements live in the existing
`AssistantResult.payload` compatibility DTO. No reviewer asked to expand this
slice beyond its bounded scope to resolve them.

After each remediation the implementer ran offline checks with a freshly
created writable `TMPDIR`; no test accessed a live provider, credential,
Telegram, archive database, account or job:

```text
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_prm_synthesis.py tests/test_prm_application.py
# 32 passed in 2.52s (7c8c3fe)

TMPDIR=<mktemp> PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 tools/test_tiers.py focused-prm
# 358 passed in 76.22s (7c8c3fe)
# 360 passed in 95.84s (901996e)
# 363 passed in 76.82s (c4f828c)

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  tests/test_prm_synthesis.py tests/test_prm_application.py tests/test_prm_bot_dispatch.py
# 41 passed in 4.09s (901996e)
# 44 passed in 5.20s (c4f828c)

python3 -m py_compile src/prm/application.py src/prm/synthesis.py \
  tests/test_prm_application.py tests/test_prm_synthesis.py
git diff --check
python3 tools/check_personal_assistant_plan.py
python3 tools/playbook.py --check-pin
# all passed; plan output retained mechanical design state review_required
```

## Remaining gates and handoff

- PA-04 is locally verified and independently rechecked `ADVISORY`; it has no
  formal human acceptance claim and the mechanical design status remains
  `review_required` because of the historic STOP_SHIP artifact.
- No durable source of paired archive-synthesis authorization is implemented.
  The ingress accepts only an externally injected exact typed pair; neither a
  configured key nor the two environment flags are consent.
- Synthetic fixture verification does not establish FTS-quality multilingual
  recall, model quality, provider behavior, mobile usefulness, actual archive
  freshness or authorized private-data egress. Those remain distinct later
  gates.
- The two pre-existing untracked local files remain unstaged and untouched.

PA-05 is dependency-ready: controlled public search/fetch/evidence without
leaking private archive context or widening the paired archive boundary. Deep
Review remains deferred until the declared PA-04..PA-06 phase boundary.
