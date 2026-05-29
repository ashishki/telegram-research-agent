# Research Brief Receipt

Status: storage implemented; generation, delivery updates, verification, and CLI inspection planned

## Purpose And Boundaries

`research_brief_receipt` is audit metadata for each delivered weekly Research
Brief. The canonical SQLite table and storage helpers exist, but the weekly
generation and delivery pipeline does not create or update receipts yet. The
receipt answers a narrow operator question: "What exact inputs, configuration,
generated artifacts, delivery state, and verification status produced this
brief?"

The receipt solves a single-operator audit problem. A brief may be useful or
not useful, but the operator still needs to inspect why it exists, which
evidence window it covered, which source links and evidence rows were included,
which model/config produced it, where the generated artifacts live, and whether
the delivered result has been checked.

This is not a reader-facing report section and it must not change weekly brief
behavior by itself.

Boundaries:

- `digests` stores the generated weekly artifact record. A receipt points to a
  digest row and snapshots audit metadata around generation, delivery, and
  verification.
- `signal_evidence_items` stores selected source evidence with provenance. A
  receipt references the evidence item IDs and source URLs used by a delivered
  brief; it does not replace the evidence table.
- `decision_journal` stores operator decisions such as acted-on, deferred,
  rejected, and completed. A receipt may cite decision counts or related
  outcomes, but it is not a decision log.
- `weekly_usefulness_logs` stores operator-authored usefulness feedback after a
  weekly reading session. A receipt may link to usefulness log rows, but
  verification status is an audit status, not a usefulness rating.
- Future Channel Intelligence receipts should audit claims, narratives, source
  observations, and referee verdicts. `research_brief_receipt` audits the
  delivered Research Brief artifact and its input window.

Entropy Core is optional receipt vocabulary only. The local receipt may use
compatible names such as `type`, `evidence_window`, `artifacts`, and `verifier`,
but Entropy Core is not a runtime dependency and must not be required for
generation, storage, delivery, verification, or inspection.

## Receipt Fields

The receipt is concrete enough to serialize as JSON and store in SQLite. The
ENT-2 storage implementation uses a flattened SQLite row with JSON snapshot
columns for structured lists and maps.

### Receipt Identity

| Field | Meaning |
|---|---|
| `type` | Constant: `research_brief_receipt`. |
| `receipt_id` | Stable receipt ID, preferably deterministic from week label plus digest row or generated as a UUID and stored. |
| `week_label` | Brief week label such as `2026-W22`. |
| `generated_at` | UTC timestamp when the receipt was first created. |
| `source_project` | Constant: `telegram-research-agent`. |
| `source_version` | Git commit SHA, release label, or local version string available at generation time. |

### Evidence Window

| Field | Meaning |
|---|---|
| `window_start` | Inclusive start date/time for posts considered by the brief. |
| `window_end` | Exclusive or inclusive end date/time; implementation must declare one convention. |
| `week_label` | Same week label repeated inside the evidence window for local querying. |
| `included_channels` | Channel usernames/IDs included in the generation scope. |
| `post_count_total` | Count of posts considered after ingestion/window filtering. |
| `post_count_scored` | Count of posts with scoring available. |
| `strong_count` | Count of strong signals in the window. |
| `watch_count` | Count of watch/keep-in-view signals in the window. |
| `noise_count` | Count of low-signal/noise items in the window. |
| `cultural_count` | Count of cultural/funny items if tracked separately. |

### Source Set

| Field | Meaning |
|---|---|
| `channels` | Channels that contributed at least one cited or selected item. |
| `telegram_source_links` | Concrete `https://t.me/<channel>/<message_id>` links used in the brief. |
| `source_evidence_item_ids` | Referenced `signal_evidence_items.id` values. |
| `source_post_ids` | Referenced canonical post IDs when available. |
| `project_scopes` | Active project IDs/names used for project-scoped retrieval. |
| `topic_scopes` | Topic labels or topic IDs used for retrieval and section routing. |
| `broad_fallback_used` | Boolean indicating whether generation fell back beyond project/topic/source scope. |
| `broad_fallback_reason` | Short reason when broad fallback was used. |

### Model/Config

| Field | Meaning |
|---|---|
| `llm_provider` | Provider used for brief generation, if any. |
| `llm_model` | Model name used for brief generation. |
| `llm_category` | Local category such as `weekly_brief`, `preference_judge`, or `fallback`. |
| `prompt_template_path` | Prompt template path used for generation, for example `docs/prompts/digest_generation.md` or runtime prompt path. |
| `prompt_template_version` | Prompt version, file hash, or commit SHA. |
| `scoring_config_fingerprint` | Fingerprint/hash of `src/config/scoring.yaml` or effective scoring config. |
| `profile_config_fingerprint` | Fingerprint/hash of `src/config/profile.yaml` when profile preferences affect selection. |
| `projects_config_fingerprint` | Fingerprint/hash of `src/config/projects.yaml` when project relevance affects selection. |
| `channels_config_fingerprint` | Fingerprint/hash of `src/config/channels.yaml` when source scope affects selection. |
| `generation_params_fingerprint` | Fingerprint/hash of material generation parameters such as thresholds and limits. |
| `llm_usage_ids` | Optional links to `llm_usage` rows for cost/token audit. |

### Artifact Refs

| Field | Meaning |
|---|---|
| `digest_id` | Linked `digests.id` row for the Research Brief. |
| `markdown_path` | Path to generated Markdown, if stored. |
| `json_path` | Path to generated JSON/structured artifact, if stored. |
| `html_path` | Path to generated HTML or fallback attachment, if stored. |
| `telegraph_url` | Telegraph article URL when publishing succeeds. |
| `telegram_delivery_timestamp` | Timestamp when the Telegram notification or fallback was sent. |
| `telegram_message_id` | Bot-delivered message ID, if available. |
| `fallback_delivery_used` | Boolean indicating whether file/HTML fallback was used. |
| `fallback_delivery_reason` | Telegraph/API/file reason when fallback was used. |

### Verification Status

| Field | Meaning |
|---|---|
| `verification_status` | One of `pending`, `verified`, `needs_review`, `failed`, `waived`. |
| `verifier_method` | Method such as `operator_review`, `deterministic_checks`, `referee_pass`, or `manual_waiver`. |
| `verifier_notes` | Short operator or system notes. |
| `checked_at` | Timestamp when the current verification status was set. |
| `checked_by` | Optional local actor label, usually `operator` or `system`. |

Status semantics:

- `pending`: receipt exists but no verification has happened yet.
- `verified`: deterministic checks passed and/or the operator accepted the
  brief as auditable.
- `needs_review`: non-fatal issue needs operator attention, such as missing
  source links or broad fallback usage.
- `failed`: audit checks failed; the brief should not be treated as verified.
- `waived`: operator explicitly accepted a known issue for this week.

### Health/Quality Flags

| Field | Meaning |
|---|---|
| `empty_week_alert` | No meaningful scored signals were available. |
| `low_signal_alert` | Signal volume or quality fell below configured thresholds. |
| `missing_source_links` | One or more surfaced items lacked concrete Telegram source links. |
| `weak_evidence` | Report relied on sparse evidence, single-source evidence, or low-confidence items. |
| `fallback_delivery` | Telegraph or normal delivery failed and fallback was used. |
| `broad_fallback_usage` | Retrieval expanded beyond the intended project/topic/source scope. |
| `artifact_missing` | Expected generated artifact path or digest row is missing. |
| `llm_usage_missing` | Expected usage/cost linkage is missing. |

Flags should be stored as booleans or a small structured map so CLI inspection
can filter receipts by audit condition.

## State Ownership

### Canonical Stored Fields

The source of truth is a local SQLite `research_brief_receipts` row. These
fields are stored, not recomputed on every inspection:

- `receipt_id`, `type`, `week_label`, `generated_at`
- `source_project`, `source_version`
- evidence window dates and included channel list
- linked `digest_id`
- artifact refs and delivery refs
- verification status fields
- health/quality flags

Canonical receipt state should be immutable for generation-time facts and
append/update-only for delivery and verification facts.

### Derived Snapshots/Fingerprints

These fields are snapshots of other state at generation time:

- post and bucket counts
- source set lists and evidence item IDs
- project and topic scopes
- config fingerprints
- prompt template path/version
- `llm_usage_ids`
- broad fallback reason

They are derived from canonical rows and config files, but the receipt stores
the snapshot so later audits can reproduce the generation context even after
configs or evidence tables change.

### Report-Only Summaries

These should not become canonical receipt facts:

- prose explaining why the brief was useful
- model-authored section summaries
- reader-facing "why this matters" text
- subjective quality language not backed by flags or verifier notes
- Channel Intelligence narrative/claim prose

If such text is needed for inspection, it should be read from the artifact or
linked digest, not copied into receipt state except as an explicit note.

### Source Of Truth, Refresh Rule, Retrieval Path, Debug Surface

| Contract | Design |
|---|---|
| Source of truth | `research_brief_receipts` SQLite row plus linked canonical rows in `digests`, `signal_evidence_items`, `llm_usage`, `quality_metrics`, and delivered artifacts. |
| Refresh rule | Create once after brief generation; update only delivery refs, verification status, verifier notes, and health flags that become known after delivery/checks. Do not silently recompute generation-time snapshots. If a brief is regenerated, create a new receipt or explicit revision. |
| Retrieval path | Fetch by `receipt_id`, `week_label`, `digest_id`, or artifact URL/path; join to digest, evidence rows, source posts, usage rows, and quality metrics only when inspection asks for details. |
| Debug surface | Future CLI commands should print receipt identity, evidence window, source set, model/config fingerprints, artifact refs, delivery refs, verification status, health flags, and linked row IDs. Debug output must show missing source links, weak evidence, fallback delivery, and broad fallback usage prominently. |

This is the explicit source of truth, refresh rule, retrieval path, and debug
surface contract for future receipt implementation.

## Storage Model

ENT-2 implements the primary SQLite storage surface and helper API. Runtime
creation, delivery updates, verification checks, and CLI inspection remain
future tasks.

Primary table: `research_brief_receipts`.

Likely columns:

- identity: `id`, `receipt_id`, `type`, `week_label`, `generated_at`,
  `source_project`, `source_version`
- scope snapshots: `window_start`, `window_end`, `included_channels_json`,
  `post_counts_json`, `source_set_json`, `project_scopes_json`,
  `topic_scopes_json`
- config snapshots: `llm_provider`, `llm_model`, `llm_category`,
  `prompt_template_path`, `prompt_template_version`,
  `config_fingerprints_json`, `generation_params_fingerprint`
- artifact refs: `digest_id`, `markdown_path`, `json_path`, `html_path`,
  `telegraph_url`, `telegram_delivery_timestamp`, `telegram_message_id`,
  `fallback_delivery`, `fallback_delivery_used`
- verification: `verification_status`, `verifier_method`, `verifier_notes`,
  `checked_at`, `checked_by`
- flags: `health_flags_json`
- timestamps: `created_at`, `updated_at`

Implemented linkage:

- `digests`: `digest_id` references `digests(id)` with `ON DELETE SET NULL`.

Future possible linkages:

- `signal_evidence_items`: selected evidence rows referenced by the brief.
- `llm_usage`: provider/model/token/cost rows for generation and judges.
- `quality_metrics`: empty/low-signal or delivery health rows if this table is
  available when implementation begins.
- delivered file paths: Markdown, JSON, HTML, Telegraph URL, and Telegram
  message refs.

The storage implementation uses JSON columns for source sets and flags and
indexes `week_label`, `digest_id`, `verification_status`, and `generated_at`.
ENT-2 intentionally does not create separate link tables.

## Lifecycle

1. Receipt creation happens immediately after a Research Brief is generated and
   the digest/artifact row is known. Initial `verification_status` is `pending`.
2. The creation step snapshots the evidence window, source set, model/config,
   artifact paths available at generation time, and initial health flags.
3. Delivery updates the receipt with `telegraph_url`, Telegram delivery
   timestamp/message ID, fallback delivery fields, and delivery-related health
   flags.
4. Verification updates `verification_status`, `verifier_method`,
   `verifier_notes`, `checked_at`, and any check-derived health flags.
5. If a week is empty or low-signal, a receipt is still created. The receipt
   should record low counts, `empty_week_alert` or `low_signal_alert`, and
   whether the delivered brief intentionally contained little or no content.
6. If Telegraph publishing fails and fallback HTML/file delivery succeeds, the
   receipt remains valid but sets `fallback_delivery_used` and
   `fallback_delivery`. Verification should check that the fallback path exists
   and was delivered.
7. If regeneration is needed, do not overwrite the original generation snapshot.
   Create a new receipt/revision linked to the same `week_label` or `digest_id`
   so the audit trail remains inspectable.

## Verification Workflow

### Operator Review

The operator can mark a receipt `verified`, `needs_review`, `failed`, or
`waived` after reading the brief and inspecting the receipt. Operator review
should capture notes about missing evidence, overbroad fallback, bad source
coverage, or delivery problems.

### Deterministic Checks

Before implementation is accepted, deterministic checks should exist for:

- receipt type is `research_brief_receipt`
- `week_label`, evidence window, and `digest_id` are present
- every reader-facing cited item has a concrete Telegram source link or is
  clearly marked as uncited/insufficient evidence
- `source_evidence_item_ids` resolve when present
- artifact paths or Telegraph URL exist for the delivered route
- fallback delivery is flagged when Telegraph URL is missing after delivery
- config fingerprints are present for configs that materially affected the run
- `llm_usage_ids` resolve when model generation was used
- empty/low-signal weeks set a visible health flag instead of looking normal
- broad fallback usage is visible and not mixed silently into project-scoped
  output

Missing required audit state should fail safe: set `verification_status` to
`failed` or `needs_review`, surface the failing fields in CLI/debug output, and
avoid presenting the brief as verified.

### Optional Future Referee Pass

For high-impact claims, a future referee pass may check that source links,
evidence excerpts, and generated claims align. This can use Gensyn-inspired
roles as a design pattern, such as a source-link lens plus project-relevance
lens plus referee verdict, but it must remain local and optional unless a future
task explicitly implements it.

The referee pass should not convert a weak source set into a verified fact. It
can only flag unsupported claims, confirm citation alignment, or request
operator review.

## Inspection And Outputs

Future CLI/debug questions:

- Which Research Brief receipt exists for `2026-W22`?
- What evidence window and channels did that brief use?
- Which source links and evidence item IDs were included?
- Which model, prompt template, and config fingerprints generated it?
- Where are the Markdown, JSON, HTML, Telegraph, and Telegram delivery refs?
- Was fallback delivery used?
- Is the receipt pending, verified, failed, waived, or waiting for review?
- Which health flags were set?
- Did the brief use broad fallback beyond project/topic/source scope?
- Can this brief be reproduced from the stored digest, evidence, configs, and
  artifacts?

Operator reports should show receipt metadata only when useful. A delivered
Research Brief should not include the full receipt. Acceptable report surfaces
are a short audit footer or debug-only report note such as:

- `Receipt: pending`
- `Audit flags: low signal, fallback delivery`
- `Source links checked: 12/12`

The receipt helps reproduce or audit a weekly brief by preserving:

- the exact time window and source channels
- the source URLs and evidence rows used
- the relevant project/topic scope
- model/provider and prompt/config fingerprints
- generated artifact locations
- delivery route and fallback state
- verification status and notes

## Incremental Implementation Plan

Future work remains split into bounded tasks:

1. `ENT-2`: implemented. `research_brief_receipts` schema and storage helpers
   exist with indexes for `week_label`, `digest_id`, `verification_status`,
   and `generated_at`. No report behavior changes.
2. `ENT-3`: write receipt creation after Research Brief generation. Snapshot
   evidence window, source set, model/config fingerprints, digest ID, artifact
   paths, and initial health flags.
3. `ENT-4`: update receipt delivery refs after Telegraph/Telegram delivery.
   Record Telegraph URL, Telegram timestamp/message ID, fallback delivery, and
   missing artifact flags.
4. `ENT-5`: add deterministic verification checks and status transitions.
   Failed checks must set `failed` or `needs_review` and print actionable debug
   details.
5. `ENT-6`: add CLI/debug inspection for receipts by week, receipt ID, digest
   ID, artifact path, or Telegraph URL. Output must include source of truth,
   refresh rule, retrieval path, and debug surface metadata.
6. `ENT-7`: add optional operator review workflow for marking receipts
   `verified`, `waived`, `needs_review`, or `failed` with notes.
7. `ENT-8`: add an optional concise audit note in operator-only reports after
   CLI inspection and verification behavior are stable.

Keep separate unless explicitly connected by a future task:

- Channel Intelligence schema/extraction/report work (`INTEL-*`)
- production Telegram validation (`OPS-*`)
- weekly quality trend reporting (`QUAL-*`)

Optional dependencies:

- `ENT-5` may consume quality metrics when `QUAL-1` exists.
- future Channel Intelligence receipts may share verification vocabulary, but
  they should have their own source set and claim/narrative audit contract.
