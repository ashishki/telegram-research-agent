from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from output.reporting_period import ReportingPeriod, register_reporting_period_sqlite


REACTION_EFFECT_SCHEMA_VERSION = "reaction_personalization.v1"
REACTION_SNAPSHOT_SCHEMA_VERSION = "reaction_visibility_snapshot.v1"
REACTION_RANKING_POLICY_VERSION = "reaction-ranking.v1"
MAX_UNCONSUMED_AUDIT_ITEMS = 25
MAX_LINKED_THREAD_AUDIT_ITEMS = 500
MIN_REACTION_ELIGIBLE_CONFIDENCE = 0.5

REACTION_EFFECT_STATUSES = frozenset(
    {
        "effects_applied",
        "linked_no_selection_effect",
        "no_eligible_reactions",
        "partial",
        "unavailable",
    }
)
SNAPSHOT_STATUSES = frozenset({"complete", "partial", "unavailable"})
COUNTERFACTUAL_EFFECTS = frozenset(
    {"selection_changed", "rank_changed", "linked_only"}
)
UNCONSUMED_REASONS = (
    "post_not_found",
    "outside_analysis_period",
    "knowledge_atom_not_extracted",
    "no_thread_link",
    "no_canonical_thread_link",
    "stale_or_low_confidence_evidence",
    "contradicted_or_retracted_evidence",
    "duplicate_signal",
    "superseded_by_confirmed_feedback",
    "report_limit_reached",
    "confirmed_feedback_snapshot_unverified",
    "snapshot_unverified",
)
_UNCONSUMED_PRIORITY = {reason: index for index, reason in enumerate(UNCONSUMED_REASONS)}
_NON_CURRENT_ATOM_STATUSES = frozenset(
    {"superseded", "resolved", "stale", "hype_only"}
)
_INELIGIBLE_THREAD_STATUSES = frozenset(
    {"stale", "hype_only", "resolved", "superseded"}
)
_WEEK_RE = re.compile(r"^(?P<year>\d{4})-W(?P<week>\d{2})$")
_ATOM_REF_RE = re.compile(r"^atom:[1-9]\d*$")
_REACTION_POST_REF_RE = re.compile(r"^reaction-post:[0-9a-f]{24}$")
_REACTION_REF_RE = re.compile(r"^reaction:[0-9a-f]{24}$")
_TELEGRAM_SOURCE_REF_RE = re.compile(r"^telegram:@[^\s:]{1,300}$")


class ReactionPersonalizationError(ValueError):
    """Raised when snapshot, lineage, or receipt identity is inconsistent."""


@dataclass(frozen=True, slots=True)
class ThreadResolution:
    """IRX-3 current-thread attribution with an explicit IRX-4 gap."""

    compatibility_thread_ref: str | None
    current_thread_ref: str | None
    canonical_thread_ref: str | None = None
    resolution_status: str = "compatibility_current_thread_only"

    def to_dict(self) -> dict[str, object]:
        return {
            "compatibility_thread_ref": self.compatibility_thread_ref,
            "current_thread_ref": self.current_thread_ref,
            "canonical_thread_ref": self.canonical_thread_ref,
            "resolution_status": self.resolution_status,
        }


class ThreadResolver(Protocol):
    def resolve(self, thread: Mapping[str, object]) -> ThreadResolution:
        """Resolve current compatibility identity without semantic matching."""


@dataclass(frozen=True, slots=True)
class CompatibilityThreadResolver:
    """IRX-3 resolver; IRX-4 replaces the nullable canonical side."""

    def resolve(self, thread: Mapping[str, object]) -> ThreadResolution:
        slug = str(thread.get("slug") or "").strip()
        reference = f"idea_thread:{slug}" if slug else None
        return ThreadResolution(
            compatibility_thread_ref=reference,
            current_thread_ref=reference,
            canonical_thread_ref=None,
            resolution_status="compatibility_current_thread_only",
        )


@dataclass(frozen=True, slots=True)
class ReactionSnapshotIdentity:
    run_id: str
    snapshot_ref: str
    observed_through: str
    snapshot_status: str
    stage_status: str
    usable: bool


@dataclass(frozen=True, slots=True)
class _ResolvedPost:
    post_id: int
    raw_post_id: int
    posted_at: str
    channel_username: str
    message_id: int


@dataclass(frozen=True, slots=True)
class _AtomLink:
    atom_id: int
    source_urls: tuple[str, ...]
    confidence: float
    staleness_status: str


@dataclass(frozen=True, slots=True)
class _ThreadLink:
    thread_id: int
    slug: str
    status: str
    atom_ids: tuple[int, ...]
    atom_relations: tuple[tuple[int, str], ...]

    def resolver_input(self) -> dict[str, object]:
        return {
            "id": self.thread_id,
            "slug": self.slug,
            "status": self.status,
            "atom_ids": list(self.atom_ids),
            "atom_relations": [
                {"atom_id": atom_id, "relation": relation}
                for atom_id, relation in self.atom_relations
            ],
        }


def primary_unconsumed_reason(reasons: Iterable[str]) -> str:
    clean = {str(reason) for reason in reasons if str(reason) in _UNCONSUMED_PRIORITY}
    if not clean:
        raise ReactionPersonalizationError("at least one known unconsumed reason is required")
    return min(clean, key=lambda reason: _UNCONSUMED_PRIORITY[reason])


def thread_resolution_unconsumed_reason(
    resolution: ThreadResolution,
    *,
    require_canonical: bool,
) -> str | None:
    """Expose the IRX-4 handoff path without rejecting IRX-3 compatibility links."""

    if not resolution.current_thread_ref:
        return "no_thread_link"
    if require_canonical and not resolution.canonical_thread_ref:
        return "no_canonical_thread_link"
    return None


def personalize_thread_candidates(
    connection: sqlite3.Connection,
    *,
    reporting_period: ReportingPeriod,
    snapshot_binding: Mapping[str, object] | None,
    snapshot: Mapping[str, object] | None,
    baseline_candidates: Sequence[Mapping[str, object]],
    feedback_context: Mapping[str, object],
    limit: int,
    receipt_limit: int | None = None,
    feedback_snapshot_usable: bool = True,
    thread_resolver: ThreadResolver | None = None,
    selection_projector: Callable[[Sequence[Mapping[str, object]]], Sequence[str]] | None = None,
    receipt_surface: str = "weekly_brief",
) -> tuple[list[dict], dict | None]:
    """Project a same-run reaction snapshot and apply one-step tie promotions.

    The input order is the established non-reaction order.  With no IRX-3
    binding this function returns the legacy slice and no additive receipt.
    A non-usable orchestrated binding produces a partial/unavailable receipt,
    never a fresh boost.
    """

    connection.row_factory = sqlite3.Row
    clean_limit = max(1, int(limit or 1))
    clean_receipt_limit = min(
        clean_limit,
        max(1, int(receipt_limit if receipt_limit is not None else clean_limit)),
    )
    baseline = [dict(candidate) for candidate in baseline_candidates]
    if snapshot_binding is None:
        return baseline[:clean_limit], None

    identity = _snapshot_identity(snapshot_binding)
    if not identity.usable:
        if snapshot is not None:
            raise ReactionPersonalizationError(
                "an unusable reaction binding cannot carry a snapshot payload"
            )
        receipt = _empty_effect_receipt(
            reporting_period,
            identity,
            status=("partial" if identity.snapshot_status == "partial" else "unavailable"),
        )
        receipt["surface"] = str(receipt_surface)
        validate_reaction_effect(receipt)
        return baseline[:clean_limit], receipt

    observations = validate_reaction_snapshot(
        snapshot_binding=snapshot_binding,
        snapshot=snapshot,
        reporting_period=reporting_period,
    )
    if not feedback_snapshot_usable:
        receipt = _empty_effect_receipt(
            reporting_period,
            identity,
            status="partial",
            event_count=sum(len(item["raw_emojis"]) for item in observations),
            post_count=len(observations),
            unconsumed_reason="confirmed_feedback_snapshot_unverified",
            observations=observations,
        )
        receipt["surface"] = str(receipt_surface)
        validate_reaction_effect(receipt)
        return baseline[:clean_limit], receipt

    ordered, receipt = _project_and_rank(
        connection,
        reporting_period=reporting_period,
        identity=identity,
        observations=observations,
        baseline=baseline,
        feedback_context=feedback_context,
        output_limit=clean_limit,
        receipt_limit=clean_receipt_limit,
        thread_resolver=thread_resolver or CompatibilityThreadResolver(),
        selection_projector=selection_projector,
        receipt_surface=receipt_surface,
    )
    validate_reaction_effect(receipt)
    return ordered, receipt


def validate_reaction_snapshot(
    *,
    snapshot_binding: Mapping[str, object],
    snapshot: Mapping[str, object] | None,
    reporting_period: ReportingPeriod,
) -> list[dict[str, object]]:
    identity = _snapshot_identity(snapshot_binding)
    if not identity.usable or identity.snapshot_status != "complete":
        raise ReactionPersonalizationError("reaction snapshot is not usable and complete")
    if not isinstance(snapshot, Mapping):
        raise ReactionPersonalizationError("usable reaction binding requires a snapshot object")
    if snapshot.get("schema_version") != REACTION_SNAPSHOT_SCHEMA_VERSION:
        raise ReactionPersonalizationError("reaction snapshot schema mismatch")
    expected = reporting_period.to_dict()
    for field in (
        "run_date",
        "generated_at",
        "reporting_week",
        "week_label",
        "period_mode",
        "analysis_period_start",
        "analysis_period_end",
    ):
        if snapshot.get(field) != expected[field]:
            raise ReactionPersonalizationError(
                f"reaction snapshot reporting identity mismatch: {field}"
            )
    for field, expected_value in (
        ("run_id", identity.run_id),
        ("snapshot_ref", identity.snapshot_ref),
        ("observed_through", identity.observed_through),
    ):
        if snapshot.get(field) != expected_value:
            raise ReactionPersonalizationError(
                f"reaction snapshot binding mismatch: {field}"
            )
    coverage = snapshot.get("coverage")
    if not isinstance(coverage, Mapping):
        raise ReactionPersonalizationError("reaction snapshot coverage must be an object")
    candidate_count = _nonnegative_int(coverage.get("candidate_count"), "candidate_count")
    checked_count = _nonnegative_int(coverage.get("checked_count"), "checked_count")
    if checked_count != candidate_count or coverage.get("coverage_complete") is not True:
        raise ReactionPersonalizationError("reaction snapshot coverage is incomplete")
    if coverage.get("visibility_verified") is not True:
        raise ReactionPersonalizationError("reaction snapshot visibility is unverified")
    raw_observations = snapshot.get("observed_personal_posts")
    if not isinstance(raw_observations, list):
        raise ReactionPersonalizationError("observed_personal_posts must be an array")
    if len(raw_observations) > checked_count:
        raise ReactionPersonalizationError("observed post count exceeds checked count")
    observations: list[dict[str, object]] = []
    seen: set[tuple[str, int]] = set()
    seen_post_ids: set[int] = set()
    for index, raw in enumerate(raw_observations):
        if not isinstance(raw, Mapping):
            raise ReactionPersonalizationError(f"reaction observation {index} must be an object")
        post_id = _positive_int(raw.get("post_id"), f"observation {index}.post_id")
        message_id = _positive_int(raw.get("message_id"), f"observation {index}.message_id")
        channel = str(raw.get("channel_username") or "").strip()
        if not channel or len(channel) > 300:
            raise ReactionPersonalizationError(
                f"observation {index}.channel_username is invalid"
            )
        identity_key = (_normalize_channel(channel), message_id)
        if identity_key in seen:
            raise ReactionPersonalizationError("reaction snapshot contains duplicate posts")
        seen.add(identity_key)
        if post_id in seen_post_ids:
            raise ReactionPersonalizationError(
                "reaction snapshot repeats one normalized post identity"
            )
        seen_post_ids.add(post_id)
        posted_at = _canonical_utc(raw.get("posted_at"), f"observation {index}.posted_at")
        raw_emojis = raw.get("raw_emojis")
        if (
            not isinstance(raw_emojis, list)
            or not raw_emojis
            or any(not isinstance(item, str) or not item.strip() for item in raw_emojis)
            or raw_emojis != sorted(set(raw_emojis))
        ):
            raise ReactionPersonalizationError(
                f"observation {index}.raw_emojis must be sorted unique strings"
            )
        observations.append(
            {
                "post_id": post_id,
                "channel_username": channel,
                "message_id": message_id,
                "posted_at": posted_at,
                "raw_emojis": list(raw_emojis),
            }
        )
    return observations


def validate_reaction_effect(receipt: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(receipt, Mapping):
        raise ReactionPersonalizationError("reaction effect must be an object")
    if receipt.get("schema_version") != REACTION_EFFECT_SCHEMA_VERSION:
        raise ReactionPersonalizationError("reaction effect schema mismatch")
    for field in (
        "run_id",
        "surface",
        "reporting_week",
        "analysis_period_start",
        "analysis_period_end",
        "snapshot_ref",
        "snapshot_status",
        "status",
    ):
        if not isinstance(receipt.get(field), str) or not str(receipt[field]).strip():
            raise ReactionPersonalizationError(f"reaction effect {field} is required")
    if receipt["snapshot_status"] not in SNAPSHOT_STATUSES:
        raise ReactionPersonalizationError("reaction effect snapshot_status is invalid")
    if receipt["status"] not in REACTION_EFFECT_STATUSES:
        raise ReactionPersonalizationError("reaction effect status is invalid")
    _canonical_utc(receipt.get("analysis_period_start"), "analysis_period_start")
    _canonical_utc(receipt.get("analysis_period_end"), "analysis_period_end")
    counts = receipt.get("counts")
    if not isinstance(counts, Mapping):
        raise ReactionPersonalizationError("reaction effect counts must be an object")
    required_counts = (
        "personal_reaction_events_detected",
        "unique_reacted_posts",
        "posts_resolved",
        "eligible_period_posts",
        "unique_atoms_linked",
        "unique_canonical_threads_linked",
        "canonical_threads_boosted",
        "unique_compatibility_threads_linked",
        "compatibility_threads_boosted",
        "selected_items_linked",
        "selected_signals_influenced",
        "unconsumed_reaction_events",
    )
    for field in required_counts:
        _nonnegative_int(counts.get(field), f"counts.{field}")
    influenced = _receipt_items(receipt.get("influenced_items"), "influenced_items")
    linked = _receipt_items(receipt.get("linked_only_items"), "linked_only_items")
    lineage_audit = _receipt_items(
        receipt.get("eligible_thread_audit"),
        "eligible_thread_audit",
    )
    if len(lineage_audit) > MAX_LINKED_THREAD_AUDIT_ITEMS:
        raise ReactionPersonalizationError("eligible thread audit is unbounded")
    for item in influenced:
        if item.get("effect") not in {"selection_changed", "rank_changed"}:
            raise ReactionPersonalizationError("influenced item has an invalid effect")
        _validate_compatibility_attribution(item)
        _validate_counterfactual_item(item)
    for item in linked:
        if item.get("effect") != "linked_only":
            raise ReactionPersonalizationError("linked-only item has an invalid effect")
        _validate_compatibility_attribution(item)
        _validate_counterfactual_item(item)
    selected_audit: dict[str, Mapping[str, object]] = {}
    all_audit_refs: set[str] = set()
    for item in lineage_audit:
        _validate_compatibility_attribution(item)
        compatibility_ref = str(item.get("compatibility_thread_ref") or "").strip()
        surface_ref = str(item.get("surface_item_ref") or "").strip()
        if not compatibility_ref or not surface_ref:
            raise ReactionPersonalizationError(
                "eligible thread audit requires surface and compatibility refs"
            )
        if compatibility_ref in all_audit_refs:
            raise ReactionPersonalizationError(
                "eligible thread audit repeats a compatibility thread"
            )
        all_audit_refs.add(compatibility_ref)
        if item.get("boost_applied") is not True:
            raise ReactionPersonalizationError(
                "eligible thread audit requires one bounded boost"
            )
        selected = item.get("selected")
        effect = item.get("counterfactual_effect")
        if not isinstance(selected, bool):
            raise ReactionPersonalizationError(
                "eligible thread audit selected marker must be boolean"
            )
        if selected:
            if effect not in COUNTERFACTUAL_EFFECTS:
                raise ReactionPersonalizationError(
                    "selected thread audit has an invalid counterfactual effect"
                )
            selected_audit[compatibility_ref] = item
        elif effect != "report_limit_reached":
            raise ReactionPersonalizationError(
                "unselected thread audit must record the report limit"
            )
    if int(counts["selected_signals_influenced"]) != len(influenced):
        raise ReactionPersonalizationError("influenced item count does not match receipt")
    if int(counts["selected_items_linked"]) != len(influenced) + len(linked):
        raise ReactionPersonalizationError("linked item count does not match receipt")
    if int(counts["compatibility_threads_boosted"]) != len(lineage_audit):
        raise ReactionPersonalizationError(
            "boosted compatibility-thread count does not match lineage audit"
        )
    canonical_audit_refs = {
        str(item.get("canonical_thread_ref") or "").strip()
        for item in lineage_audit
        if str(item.get("canonical_thread_ref") or "").strip()
    }
    if int(counts["canonical_threads_boosted"]) != len(canonical_audit_refs):
        raise ReactionPersonalizationError(
            "boosted canonical-thread count does not match lineage audit"
        )
    if int(counts["selected_items_linked"]) != len(selected_audit):
        raise ReactionPersonalizationError(
            "selected lineage audit count does not match receipt items"
        )
    item_by_ref: dict[str, Mapping[str, object]] = {}
    for item in [*influenced, *linked]:
        compatibility_ref = str(item.get("compatibility_thread_ref") or "").strip()
        if compatibility_ref in item_by_ref:
            raise ReactionPersonalizationError(
                "reaction receipt repeats a selected compatibility thread"
            )
        item_by_ref[compatibility_ref] = item
    if set(item_by_ref) != set(selected_audit):
        raise ReactionPersonalizationError(
            "selected receipt items do not match eligible thread audit"
        )
    for compatibility_ref, item in item_by_ref.items():
        audit_item = selected_audit[compatibility_ref]
        shared_fields = (
            "surface_item_ref",
            "reacted_post_count",
            "compatibility_thread_ref",
            "current_thread_ref",
            "canonical_thread_ref",
            "thread_resolution_status",
            "boost_role",
            "reader_reason_ru",
            "reacted_post_refs",
            "source_refs",
            "evidence_refs",
            "boost_applied",
        )
        if audit_item.get("counterfactual_effect") != item.get("effect") or any(
            audit_item.get(field) != item.get(field) for field in shared_fields
        ):
            raise ReactionPersonalizationError(
                "selected receipt item contradicts eligible thread audit"
            )
    events = int(counts["personal_reaction_events_detected"])
    posts = int(counts["unique_reacted_posts"])
    resolved = int(counts["posts_resolved"])
    eligible_posts = int(counts["eligible_period_posts"])
    linked_threads = int(counts["unique_compatibility_threads_linked"])
    boosted_threads = int(counts["compatibility_threads_boosted"])
    canonical_linked_threads = int(counts["unique_canonical_threads_linked"])
    canonical_boosted_threads = int(counts["canonical_threads_boosted"])
    selected_items = int(counts["selected_items_linked"])
    unconsumed_events = int(counts["unconsumed_reaction_events"])
    if not (events >= posts >= resolved >= eligible_posts):
        raise ReactionPersonalizationError(
            "reaction event/post funnel counts are not monotonic"
        )
    if (events == 0) != (posts == 0):
        raise ReactionPersonalizationError(
            "reaction events and reacted posts must both be empty or both be present"
        )
    if not (linked_threads >= boosted_threads >= selected_items):
        raise ReactionPersonalizationError(
            "reaction thread/selection funnel counts are not monotonic"
        )
    if not (
        linked_threads >= canonical_linked_threads >= canonical_boosted_threads
        and boosted_threads >= canonical_boosted_threads
    ):
        raise ReactionPersonalizationError(
            "canonical/compatibility thread counts are not monotonic"
        )
    if (
        linked_threads == boosted_threads
        and canonical_linked_threads != canonical_boosted_threads
    ):
        raise ReactionPersonalizationError(
            "canonical linked count contradicts complete boosted lineage"
        )
    if linked_threads and int(counts["unique_atoms_linked"]) == 0:
        raise ReactionPersonalizationError(
            "linked reaction threads require at least one linked atom"
        )
    if int(counts["unique_atoms_linked"]) > 0 and eligible_posts == 0:
        raise ReactionPersonalizationError(
            "linked reaction atoms require an eligible-period post"
        )
    if unconsumed_events > events:
        raise ReactionPersonalizationError(
            "unconsumed reaction events exceed detected events"
        )
    eligible_audit_post_refs = {
        post_ref
        for item in lineage_audit
        for post_ref in item.get("reacted_post_refs") or []
    }
    selected_audit_post_refs = {
        post_ref
        for item in selected_audit.values()
        for post_ref in item.get("reacted_post_refs") or []
    }
    audit_evidence_refs = {
        evidence_ref
        for item in lineage_audit
        for evidence_ref in item.get("evidence_refs") or []
    }
    if len(eligible_audit_post_refs) > eligible_posts:
        raise ReactionPersonalizationError(
            "thread audit references more posts than the eligible-period funnel"
        )
    if len(audit_evidence_refs) > int(counts["unique_atoms_linked"]):
        raise ReactionPersonalizationError(
            "thread audit references more evidence than the linked-atom funnel"
        )
    if len(selected_audit_post_refs) > events - unconsumed_events:
        raise ReactionPersonalizationError(
            "selected and unconsumed reaction accounting overlaps"
        )
    if posts > len(selected_audit_post_refs) + unconsumed_events:
        raise ReactionPersonalizationError(
            "reacted-post lineage is missing from selected or unconsumed accounting"
        )
    complete_effect_status = (
        "effects_applied"
        if influenced
        else "linked_no_selection_effect"
        if lineage_audit
        else "no_eligible_reactions"
    )
    status = str(receipt["status"])
    snapshot_status = str(receipt["snapshot_status"])
    if status in {
        "effects_applied",
        "linked_no_selection_effect",
        "no_eligible_reactions",
    }:
        if snapshot_status != "complete":
            raise ReactionPersonalizationError(
                "a complete reaction effect requires a complete snapshot"
            )
        if status != complete_effect_status:
            raise ReactionPersonalizationError(
                "reaction effect status contradicts its counterfactual items"
            )
    else:
        if influenced or linked:
            raise ReactionPersonalizationError(
                "partial or unavailable receipts cannot contain applied effects"
            )
        if any(
            int(counts.get(field) or 0) > 0
            for field in (
                "canonical_threads_boosted",
                "compatibility_threads_boosted",
                "selected_items_linked",
                "selected_signals_influenced",
            )
        ):
            raise ReactionPersonalizationError(
                "partial or unavailable receipts cannot report ranking effects"
            )
        if status == "unavailable" and snapshot_status != "unavailable":
            raise ReactionPersonalizationError(
                "unavailable receipt requires an unavailable snapshot"
            )
    by_reason = receipt.get("unconsumed_by_reason")
    if not isinstance(by_reason, Mapping):
        raise ReactionPersonalizationError("unconsumed_by_reason must be an object")
    for reason, count in by_reason.items():
        if reason not in _UNCONSUMED_PRIORITY:
            raise ReactionPersonalizationError(f"unknown unconsumed reason: {reason}")
        if _nonnegative_int(count, f"unconsumed_by_reason.{reason}") == 0:
            raise ReactionPersonalizationError(
                "unconsumed reason counts must be positive when present"
            )
    unconsumed = receipt.get("unconsumed")
    if not isinstance(unconsumed, list) or len(unconsumed) > MAX_UNCONSUMED_AUDIT_ITEMS:
        raise ReactionPersonalizationError("unconsumed audit list is invalid or unbounded")
    if len(unconsumed) != min(unconsumed_events, MAX_UNCONSUMED_AUDIT_ITEMS):
        raise ReactionPersonalizationError(
            "unconsumed audit sample does not cover the bounded event total"
        )
    sampled_reasons: Counter[str] = Counter()
    sampled_refs: set[str] = set()
    for item in unconsumed:
        if not isinstance(item, Mapping) or item.get("reason") not in _UNCONSUMED_PRIORITY:
            raise ReactionPersonalizationError("unconsumed audit item has an invalid reason")
        reaction_ref = str(item.get("reaction_ref") or "").strip()
        if (
            _REACTION_REF_RE.fullmatch(reaction_ref) is None
            or reaction_ref in sampled_refs
        ):
            raise ReactionPersonalizationError(
                "unconsumed audit requires unique opaque reaction refs"
            )
        sampled_refs.add(reaction_ref)
        reason = str(item["reason"])
        reasons = item.get("reasons")
        if (
            not isinstance(reasons, list)
            or not reasons
            or any(value not in _UNCONSUMED_PRIORITY for value in reasons)
            or reasons != sorted(set(reasons), key=lambda value: _UNCONSUMED_PRIORITY[value])
            or reason != primary_unconsumed_reason(reasons)
        ):
            raise ReactionPersonalizationError(
                "unconsumed audit reason trace is invalid"
            )
        if item.get("audit_detail") != _audit_detail(reason):
            raise ReactionPersonalizationError(
                "unconsumed audit detail does not match its reason"
            )
        sampled_reasons[reason] += 1
    if sum(int(value) for value in by_reason.values()) != int(
        counts["unconsumed_reaction_events"]
    ):
        raise ReactionPersonalizationError("unconsumed reason totals do not match receipt")
    if len(unconsumed) > unconsumed_events or any(
        sampled_count > int(by_reason.get(reason) or 0)
        for reason, sampled_count in sampled_reasons.items()
    ):
        raise ReactionPersonalizationError(
            "unconsumed audit sample exceeds aggregate reason counts"
        )
    if unconsumed_events <= MAX_UNCONSUMED_AUDIT_ITEMS and dict(
        sorted(sampled_reasons.items())
    ) != dict(sorted((str(key), int(value)) for key, value in by_reason.items())):
        raise ReactionPersonalizationError(
            "unconsumed audit sample does not match aggregate reason counts"
        )
    if status in {"no_eligible_reactions", "partial", "unavailable"} and (
        unconsumed_events != events
    ):
        raise ReactionPersonalizationError(
            "receipt without selected effects must account for every reaction event"
        )
    policy = receipt.get("ranking_policy")
    if not isinstance(policy, Mapping):
        raise ReactionPersonalizationError("ranking_policy must be an object")
    expected_policy = {
        "policy_version": REACTION_RANKING_POLICY_VERSION,
        "strength": "weak",
        "below_confirmed_feedback": True,
        "can_change_evidence_gate": False,
    }
    if any(policy.get(key) != value for key, value in expected_policy.items()):
        raise ReactionPersonalizationError("ranking policy violates IRX-3 precedence")
    expected_summary = _reader_summary(
        status,
        counts,
        snapshot_status=snapshot_status,
    )
    if receipt.get("reader_summary_ru") != expected_summary:
        raise ReactionPersonalizationError(
            "reader_summary_ru does not match the deterministic receipt"
        )
    return dict(receipt)


def reaction_effect_for_surface(
    receipt: Mapping[str, object],
    *,
    surface: str,
) -> dict[str, object]:
    result = validate_reaction_effect(receipt)
    result["surface"] = str(surface)
    validate_reaction_effect(result)
    return result


def build_reaction_pattern_proposals(
    observations: Iterable[Mapping[str, object]],
    *,
    as_of_week_label: str | None = None,
    window_weeks: int = 12,
) -> list[dict[str, object]]:
    """Return approval-gated proposals; this function never mutates state."""

    rows = [dict(item) for item in observations if isinstance(item, Mapping)]
    if not rows:
        return []
    parsed_weeks = [
        value
        for item in rows
        if (value := _parse_week_label(item.get("reporting_week"))) is not None
    ]
    if not parsed_weeks:
        return []
    as_of = _parse_week_label(as_of_week_label) if as_of_week_label else max(parsed_weeks)
    if as_of is None:
        raise ReactionPersonalizationError("as_of_week_label must be a valid ISO week")
    window_start = as_of - timedelta(weeks=max(1, int(window_weeks or 12)) - 1)
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in rows:
        week_start = _parse_week_label(item.get("reporting_week"))
        if week_start is None or week_start < window_start or week_start > as_of:
            continue
        mode = str(item.get("period_mode") or "completed_iso_week")
        if mode not in {"completed_iso_week", "explicit_iso_week"}:
            continue
        # The caller must attest that this exact weekly run completed.  A
        # syntactically valid historical week label is not completion proof.
        if item.get("completed") is not True:
            continue
        canonical_ref = _clean_optional(item.get("canonical_thread_ref"))
        compatibility_ref = _clean_optional(
            item.get("compatibility_thread_ref") or item.get("current_thread_ref")
        )
        pattern_ref = canonical_ref or compatibility_ref
        if not pattern_ref:
            continue
        post_refs = _string_list(
            item.get("reacted_post_refs")
            or item.get("post_refs")
            or item.get("post_ref")
        )
        if not post_refs:
            continue
        grouped[pattern_ref].append(
            {
                **item,
                "reporting_week": _format_week(week_start),
                "canonical_thread_ref": canonical_ref,
                "compatibility_thread_ref": compatibility_ref,
                "post_refs": post_refs,
            }
        )
    proposals: list[dict[str, object]] = []
    for pattern_ref, items in sorted(grouped.items()):
        weeks = sorted({str(item["reporting_week"]) for item in items})
        post_refs = sorted(
            {
                post_ref
                for item in items
                for post_ref in _string_list(item.get("post_refs"))
            }
        )
        if len(weeks) < 3 or len(post_refs) < 4:
            continue
        sources = sorted(
            {
                source
                for item in items
                for source in _string_list(item.get("source_refs") or item.get("source_ref"))
            }
        )
        supporting_feedback = sorted(
            {
                value
                for item in items
                for value in _string_list(item.get("supporting_confirmed_feedback"))
            }
        )
        contradicting_feedback = sorted(
            {
                value
                for item in items
                for value in _string_list(item.get("contradicting_confirmed_feedback"))
            }
        )
        canonical_ref = next(
            (_clean_optional(item.get("canonical_thread_ref")) for item in items if item.get("canonical_thread_ref")),
            None,
        )
        compatibility_ref = next(
            (
                _clean_optional(item.get("compatibility_thread_ref"))
                for item in items
                if item.get("compatibility_thread_ref")
            ),
            None,
        )
        digest = hashlib.sha256(pattern_ref.encode("utf-8")).hexdigest()[:16]
        proposals.append(
            {
                "proposal_id": f"reaction-pattern:{digest}",
                "status": "unapproved",
                "applied": False,
                "requires_approval": True,
                "mutation_policy": "suggestion_only_no_auto_edit",
                "thread_resolution": {
                    "canonical_thread_ref": canonical_ref,
                    "compatibility_thread_ref": compatibility_ref,
                    "resolution_status": (
                        "canonical" if canonical_ref else "compatibility_pending_irx4"
                    ),
                },
                "weeks": weeks,
                "distinct_week_count": len(weeks),
                "distinct_reacted_post_count": len(post_refs),
                "source_diversity": len(sources),
                "recency": {
                    "window_weeks": max(1, int(window_weeks or 12)),
                    "latest_week": weeks[-1],
                    "decay_policy": "rolling_completed_weeks",
                },
                "supporting_confirmed_feedback": supporting_feedback,
                "contradicting_confirmed_feedback": contradicting_feedback,
                "proposed_delta": {
                    "operation": "suggest_interest_pattern",
                    "thread_ref": pattern_ref,
                    "strength": "weak",
                },
                "expected_report_effect": (
                    "Use only after explicit approval as a weak standing preference below confirmed feedback."
                ),
                "rollback": "Remove the approved preference and return to period-scoped reaction signals.",
                "review_by_week": _format_week(as_of + timedelta(weeks=4)),
            }
        )
    return proposals


def _project_and_rank(
    connection: sqlite3.Connection,
    *,
    reporting_period: ReportingPeriod,
    identity: ReactionSnapshotIdentity,
    observations: list[dict[str, object]],
    baseline: list[dict],
    feedback_context: Mapping[str, object],
    output_limit: int,
    receipt_limit: int,
    thread_resolver: ThreadResolver,
    selection_projector: Callable[[Sequence[Mapping[str, object]]], Sequence[str]] | None,
    receipt_surface: str,
) -> tuple[list[dict], dict[str, object]]:
    register_reporting_period_sqlite(connection)
    candidates_by_id = {
        int(candidate["id"]): candidate
        for candidate in baseline
        if isinstance(candidate.get("id"), int) and not isinstance(candidate.get("id"), bool)
    }
    period_start = reporting_period.analysis_period_start
    period_end = reporting_period.analysis_period_end
    event_count = sum(len(item["raw_emojis"]) for item in observations)
    resolved_posts: set[int] = set()
    period_posts: set[int] = set()
    linked_atoms: set[int] = set()
    linked_threads: set[int] = set()
    current_thread_links: dict[int, _ThreadLink] = {}
    thread_resolutions: dict[int, ThreadResolution] = {}
    eligible_thread_posts: dict[int, set[int]] = defaultdict(set)
    eligible_thread_atoms: dict[int, set[int]] = defaultdict(set)
    post_reasons: dict[int, set[str]] = defaultdict(set)
    post_observation: dict[int, dict[str, object]] = {}

    atoms_cache = _load_bounded_atoms(connection, reporting_period)
    for observation in observations:
        snapshot_post_id = int(observation["post_id"])
        post_observation[snapshot_post_id] = observation
        post = _resolve_post(connection, observation)
        if post is None:
            post_reasons[snapshot_post_id].add("post_not_found")
            continue
        resolved_posts.add(post.post_id)
        post_time = _parse_utc(post.posted_at)
        if post_time is None or not (period_start <= post_time < period_end):
            post_reasons[post.post_id].add("outside_analysis_period")
            continue
        period_posts.add(post.post_id)
        atom_links = [atom for atom in atoms_cache if post.post_id in atom["source_post_ids"]]
        if not atom_links:
            post_reasons[post.post_id].add("knowledge_atom_not_extracted")
            continue
        atom_ids = {int(atom["atom"].atom_id) for atom in atom_links}
        linked_atoms.update(atom_ids)
        thread_links = _load_thread_links(connection, atom_ids)
        if not thread_links:
            post_reasons[post.post_id].add("no_thread_link")
            continue
        linked_threads.update(link.thread_id for link in thread_links)
        for thread_link in thread_links:
            current_thread_links[thread_link.thread_id] = thread_link
            resolution = _resolve_thread(thread_resolver, thread_link)
            thread_resolutions[thread_link.thread_id] = resolution
            resolution_reason = thread_resolution_unconsumed_reason(
                resolution,
                require_canonical=False,
            )
            if resolution_reason is not None:
                post_reasons[post.post_id].add(resolution_reason)
                continue
            candidate = candidates_by_id.get(thread_link.thread_id)
            if candidate is None:
                post_reasons[post.post_id].add("report_limit_reached")
                continue
            relevant_atoms = [
                atom["atom"]
                for atom in atom_links
                if int(atom["atom"].atom_id) in set(thread_link.atom_ids)
            ]
            reasons = _candidate_ineligibility_reasons(
                candidate,
                thread_link=thread_link,
                atoms=relevant_atoms,
                feedback_context=feedback_context,
            )
            if reasons:
                post_reasons[post.post_id].update(reasons)
                continue
            eligible_thread_posts[thread_link.thread_id].add(post.post_id)
            eligible_thread_atoms[thread_link.thread_id].update(
                int(atom.atom_id) for atom in relevant_atoms
            )

    personalized = [dict(candidate) for candidate in baseline]
    if selection_projector is not None:
        for baseline_position, candidate in enumerate(personalized):
            candidate["_reaction_baseline_position"] = baseline_position
    boosted: set[int] = set(eligible_thread_posts)
    for candidate in personalized:
        candidate_id = candidate.get("id")
        if isinstance(candidate_id, int) and candidate_id in boosted:
            candidate["_reaction_interest"] = True
    # The compatibility API owns a raw bounded ordering. Production surfaces
    # pass explicit selectors and apply the one-step marker inside those exact
    # selectors, keeping every other reader projection reaction-neutral.
    if selection_projector is None:
        ranking_boundary = min(len(personalized), receipt_limit + 1)
        index = 1
        while index < ranking_boundary:
            candidate = personalized[index]
            candidate_id = candidate.get("id")
            previous = personalized[index - 1]
            previous_id = previous.get("id")
            if (
                isinstance(candidate_id, int)
                and candidate_id in eligible_thread_posts
                and previous_id not in eligible_thread_posts
                and reaction_close_order_key(candidate, feedback_context)
                == reaction_close_order_key(previous, feedback_context)
            ):
                personalized[index - 1], personalized[index] = candidate, previous
                index += 1
                continue
            index += 1
    if personalized:
        first_id = personalized[0].get("id")
        if isinstance(first_id, int) and first_id in eligible_thread_posts:
            personalized[0]["_reaction_interest"] = True

    default_projector = selection_projector is None
    if selection_projector is None:
        selection_projector = lambda values: [
            "thread:"
            + str(item.get("slug") or "thread-{}".format(item.get("id")))
            for item in values[:receipt_limit]
        ]
    baseline_surface_refs = _project_surface_refs(
        selection_projector,
        baseline[:output_limit],
        limit=(receipt_limit if default_projector else None),
    )
    personalized_surface_refs = _project_surface_refs(
        selection_projector,
        personalized[:output_limit],
        limit=(receipt_limit if default_projector else None),
    )
    selected_refs = set(personalized_surface_refs)
    baseline_selected_refs = set(baseline_surface_refs)
    baseline_surface_positions = {
        surface_ref: index for index, surface_ref in enumerate(baseline_surface_refs)
    }
    personalized_surface_positions = {
        surface_ref: index for index, surface_ref in enumerate(personalized_surface_refs)
    }
    influenced_items: list[dict[str, object]] = []
    linked_only_items: list[dict[str, object]] = []
    eligible_thread_audit: list[dict[str, object]] = []
    consumed_posts: set[int] = set()
    if len(eligible_thread_posts) > MAX_LINKED_THREAD_AUDIT_ITEMS:
        raise ReactionPersonalizationError(
            "eligible reaction thread lineage exceeds the bounded audit limit"
        )
    for thread_id in sorted(eligible_thread_posts):
        candidate = next(
            (item for item in personalized if item.get("id") == thread_id),
            candidates_by_id.get(thread_id, {}),
        )
        slug = str(candidate.get("slug") or f"thread-{thread_id}")
        current_slug = str(
            current_thread_links.get(thread_id).slug
            if thread_id in current_thread_links
            else slug
        )
        resolution = thread_resolutions.get(thread_id) or CompatibilityThreadResolver().resolve(
            {"slug": current_slug}
        )
        post_count = len(eligible_thread_posts[thread_id])
        common_attribution = {
            "surface_item_ref": f"thread:{slug}",
            "reacted_post_count": post_count,
            "compatibility_thread_ref": resolution.compatibility_thread_ref,
            "current_thread_ref": resolution.current_thread_ref,
            "canonical_thread_ref": resolution.canonical_thread_ref,
            "thread_resolution_status": resolution.resolution_status,
            "boost_role": "weak_implicit_interest",
            "reader_reason_ru": _reader_item_reason(post_count),
            "reacted_post_refs": sorted(
                _post_ref(post_observation[post_id])
                for post_id in sorted(eligible_thread_posts[thread_id])
            ),
            "source_refs": sorted(
                {
                    "telegram:@"
                    + _normalize_channel(
                        post_observation[post_id].get("channel_username")
                    )
                    for post_id in eligible_thread_posts[thread_id]
                }
            ),
            "evidence_refs": [
                f"atom:{atom_id}" for atom_id in sorted(eligible_thread_atoms[thread_id])
            ],
        }
        surface_ref = str(common_attribution["surface_item_ref"])
        if surface_ref not in selected_refs:
            for post_id in eligible_thread_posts[thread_id]:
                post_reasons[post_id].add("report_limit_reached")
            effect = "report_limit_reached"
        else:
            consumed_posts.update(eligible_thread_posts[thread_id])
            if surface_ref not in baseline_selected_refs:
                effect = "selection_changed"
            elif personalized_surface_positions.get(surface_ref) != baseline_surface_positions.get(surface_ref):
                effect = "rank_changed"
            else:
                effect = "linked_only"
        eligible_thread_audit.append(
            {
                **common_attribution,
                "selected": surface_ref in selected_refs,
                "counterfactual_effect": effect,
                "boost_applied": thread_id in boosted,
            }
        )
        if surface_ref not in selected_refs:
            continue
        item = {
            **common_attribution,
            "effect": effect,
            "boost_applied": thread_id in boosted,
            "rank_changed": effect in {"rank_changed", "selection_changed"},
            "selection_changed": effect == "selection_changed",
            "linked_only": effect == "linked_only",
        }
        if effect == "linked_only":
            linked_only_items.append(item)
        else:
            influenced_items.append(item)

    unconsumed_records: list[dict[str, object]] = []
    reason_counts: Counter[str] = Counter()
    for observation in observations:
        post_id = int(observation["post_id"])
        if post_id in consumed_posts:
            continue
        reasons = post_reasons.get(post_id) or {"report_limit_reached"}
        primary = primary_unconsumed_reason(reasons)
        for raw_emoji in observation["raw_emojis"]:
            reason_counts[primary] += 1
            if len(unconsumed_records) >= MAX_UNCONSUMED_AUDIT_ITEMS:
                continue
            unconsumed_records.append(
                {
                    "reaction_ref": _reaction_ref(observation, str(raw_emoji)),
                    "reason": primary,
                    "reasons": sorted(reasons, key=lambda item: _UNCONSUMED_PRIORITY[item]),
                    "audit_detail": _audit_detail(primary),
                }
            )

    status = (
        "effects_applied"
        if influenced_items
        else "linked_no_selection_effect"
        if eligible_thread_audit
        else "no_eligible_reactions"
    )
    counts = _base_counts()
    counts.update(
        {
            "personal_reaction_events_detected": event_count,
            "unique_reacted_posts": len(observations),
            "posts_resolved": len(resolved_posts),
            "eligible_period_posts": len(period_posts),
            "unique_atoms_linked": len(linked_atoms),
            "unique_canonical_threads_linked": len(
                {
                    resolution.canonical_thread_ref
                    for thread_id, resolution in thread_resolutions.items()
                    if thread_id in linked_threads and resolution.canonical_thread_ref
                }
            ),
            "canonical_threads_boosted": len(
                {
                    thread_resolutions[thread_id].canonical_thread_ref
                    for thread_id in boosted
                    if thread_id in thread_resolutions
                    and thread_resolutions[thread_id].canonical_thread_ref
                }
            ),
            "unique_compatibility_threads_linked": len(
                {
                    resolution.compatibility_thread_ref
                    for thread_id, resolution in thread_resolutions.items()
                    if thread_id in linked_threads and resolution.compatibility_thread_ref
                }
            ),
            "compatibility_threads_boosted": len(
                {
                    thread_resolutions[thread_id].compatibility_thread_ref
                    for thread_id in boosted
                    if thread_id in thread_resolutions
                    and thread_resolutions[thread_id].compatibility_thread_ref
                }
            ),
            "selected_items_linked": len(influenced_items) + len(linked_only_items),
            "selected_signals_influenced": len(influenced_items),
            "unconsumed_reaction_events": sum(reason_counts.values()),
        }
    )
    receipt = {
        **_receipt_identity(reporting_period, identity),
        "surface": str(receipt_surface),
        "status": status,
        "counts": counts,
        "influenced_items": influenced_items,
        "linked_only_items": linked_only_items,
        "eligible_thread_audit": eligible_thread_audit,
        "unconsumed_by_reason": dict(sorted(reason_counts.items())),
        "unconsumed": unconsumed_records,
        "ranking_policy": _ranking_policy(),
        "reader_summary_ru": _reader_summary(
            status,
            counts,
            snapshot_status=identity.snapshot_status,
        ),
    }
    return personalized[:output_limit], receipt


def _snapshot_identity(binding: Mapping[str, object]) -> ReactionSnapshotIdentity:
    if not isinstance(binding, Mapping):
        raise ReactionPersonalizationError("reaction snapshot binding must be an object")
    run_id = str(binding.get("run_id") or "").strip()
    snapshot_ref = str(binding.get("snapshot_ref") or "").strip()
    observed_through = str(binding.get("observed_through") or "").strip()
    snapshot_status = str(binding.get("snapshot_status") or "").strip()
    stage_status = str(binding.get("stage_status") or "").strip()
    usable = binding.get("usable")
    if not run_id or not snapshot_ref or not observed_through or not stage_status:
        raise ReactionPersonalizationError("reaction snapshot binding identity is incomplete")
    _canonical_utc(observed_through, "snapshot observed_through")
    if snapshot_status not in SNAPSHOT_STATUSES:
        raise ReactionPersonalizationError("reaction snapshot binding status is invalid")
    if not isinstance(usable, bool):
        raise ReactionPersonalizationError("reaction snapshot usable marker must be boolean")
    if usable and (snapshot_status != "complete" or stage_status != "succeeded"):
        raise ReactionPersonalizationError("usable snapshot requires complete succeeded binding")
    return ReactionSnapshotIdentity(
        run_id=run_id,
        snapshot_ref=snapshot_ref,
        observed_through=observed_through,
        snapshot_status=snapshot_status,
        stage_status=stage_status,
        usable=usable,
    )


def _empty_effect_receipt(
    period: ReportingPeriod,
    identity: ReactionSnapshotIdentity,
    *,
    status: str,
    event_count: int = 0,
    post_count: int = 0,
    unconsumed_reason: str | None = None,
    observations: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    counts = _base_counts()
    counts["personal_reaction_events_detected"] = max(0, int(event_count))
    counts["unique_reacted_posts"] = max(0, int(post_count))
    unconsumed: list[dict[str, object]] = []
    reason_counts: dict[str, int] = {}
    if unconsumed_reason and event_count:
        reason_counts[unconsumed_reason] = max(0, int(event_count))
        counts["unconsumed_reaction_events"] = max(0, int(event_count))
        for observation in observations:
            for raw_emoji in observation.get("raw_emojis") or []:
                if len(unconsumed) >= MAX_UNCONSUMED_AUDIT_ITEMS:
                    break
                unconsumed.append(
                    {
                        "reaction_ref": _reaction_ref(observation, str(raw_emoji)),
                        "reason": unconsumed_reason,
                        "reasons": [unconsumed_reason],
                        "audit_detail": _audit_detail(unconsumed_reason),
                    }
                )
    receipt = {
        **_receipt_identity(period, identity),
        "surface": "weekly_brief",
        "status": status,
        "counts": counts,
        "influenced_items": [],
        "linked_only_items": [],
        "eligible_thread_audit": [],
        "unconsumed_by_reason": reason_counts,
        "unconsumed": unconsumed,
        "ranking_policy": _ranking_policy(),
        "reader_summary_ru": _reader_summary(
            status,
            counts,
            snapshot_status=identity.snapshot_status,
        ),
    }
    return receipt


def _receipt_identity(
    period: ReportingPeriod,
    identity: ReactionSnapshotIdentity,
) -> dict[str, object]:
    fields = period.to_dict()
    return {
        "schema_version": REACTION_EFFECT_SCHEMA_VERSION,
        "run_id": identity.run_id,
        "reporting_week": fields["reporting_week"],
        "analysis_period_start": fields["analysis_period_start"],
        "analysis_period_end": fields["analysis_period_end"],
        "snapshot_ref": identity.snapshot_ref,
        "snapshot_status": identity.snapshot_status,
    }


def _base_counts() -> dict[str, int]:
    return {
        "personal_reaction_events_detected": 0,
        "unique_reacted_posts": 0,
        "posts_resolved": 0,
        "eligible_period_posts": 0,
        "unique_atoms_linked": 0,
        "unique_canonical_threads_linked": 0,
        "canonical_threads_boosted": 0,
        "unique_compatibility_threads_linked": 0,
        "compatibility_threads_boosted": 0,
        "selected_items_linked": 0,
        "selected_signals_influenced": 0,
        "unconsumed_reaction_events": 0,
    }


def _ranking_policy() -> dict[str, object]:
    return {
        "policy_version": REACTION_RANKING_POLICY_VERSION,
        "strength": "weak",
        "below_confirmed_feedback": True,
        "can_change_evidence_gate": False,
    }


def _resolve_post(
    connection: sqlite3.Connection,
    observation: Mapping[str, object],
) -> _ResolvedPost | None:
    if not _table_exists(connection, "raw_posts") or not _table_exists(connection, "posts"):
        return None
    rows = connection.execute(
        """
        SELECT
            posts.id AS post_id,
            posts.raw_post_id,
            posts.posted_at,
            posts.channel_username AS post_channel,
            raw_posts.channel_username AS raw_channel,
            raw_posts.message_id
        FROM raw_posts
        JOIN posts ON posts.raw_post_id = raw_posts.id
        WHERE raw_posts.message_id = ?
        """,
        (int(observation["message_id"]),),
    ).fetchall()
    expected_channel = _normalize_channel(observation.get("channel_username"))
    expected_post_id = int(observation["post_id"])
    for row in rows:
        channels = {
            _normalize_channel(row["post_channel"]),
            _normalize_channel(row["raw_channel"]),
        }
        if expected_channel not in channels or int(row["post_id"]) != expected_post_id:
            continue
        return _ResolvedPost(
            post_id=int(row["post_id"]),
            raw_post_id=int(row["raw_post_id"]),
            posted_at=str(row["posted_at"] or ""),
            channel_username=str(row["post_channel"] or row["raw_channel"] or ""),
            message_id=int(row["message_id"]),
        )
    return None


def _load_bounded_atoms(
    connection: sqlite3.Connection,
    period: ReportingPeriod,
) -> list[dict[str, object]]:
    if not _table_exists(connection, "knowledge_atoms"):
        return []
    rows = connection.execute(
        """
        SELECT id, source_post_ids_json, source_urls_json, confidence,
               staleness_status, last_seen_at
        FROM knowledge_atoms
        WHERE reporting_utc_micros(last_seen_at) < reporting_utc_micros(?)
        ORDER BY id
        """,
        (period.to_dict()["analysis_period_end"],),
    ).fetchall()
    result: list[dict[str, object]] = []
    for row in rows:
        post_ids = {
            int(value)
            for value in _json_array(row["source_post_ids_json"])
            if str(value).strip().isdigit()
        }
        result.append(
            {
                "atom": _AtomLink(
                    atom_id=int(row["id"]),
                    source_urls=tuple(_string_list(_json_array(row["source_urls_json"]))),
                    confidence=float(row["confidence"] or 0.0),
                    staleness_status=str(row["staleness_status"] or "active"),
                ),
                "source_post_ids": post_ids,
            }
        )
    return result


def _load_thread_links(
    connection: sqlite3.Connection,
    atom_ids: set[int],
) -> list[_ThreadLink]:
    if (
        not atom_ids
        or not _table_exists(connection, "idea_thread_atoms")
        or not _table_exists(connection, "idea_threads")
    ):
        return []
    placeholders = ",".join("?" for _ in atom_ids)
    rows = connection.execute(
        f"""
        SELECT idea_threads.id AS thread_id, idea_threads.slug, idea_threads.status,
               idea_thread_atoms.atom_id, idea_thread_atoms.relation
        FROM idea_thread_atoms
        JOIN idea_threads ON idea_threads.id = idea_thread_atoms.thread_id
        WHERE idea_thread_atoms.atom_id IN ({placeholders})
        ORDER BY idea_threads.id, idea_thread_atoms.atom_id
        """,
        sorted(atom_ids),
    ).fetchall()
    grouped: dict[int, dict[str, object]] = {}
    for row in rows:
        item = grouped.setdefault(
            int(row["thread_id"]),
            {
                "slug": str(row["slug"] or ""),
                "status": str(row["status"] or "active"),
                "atom_ids": [],
                "atom_relations": [],
            },
        )
        item["atom_ids"].append(int(row["atom_id"]))
        item["atom_relations"].append(
            (int(row["atom_id"]), str(row["relation"] or "supports"))
        )
    return [
        _ThreadLink(
            thread_id=thread_id,
            slug=str(item["slug"]),
            status=str(item["status"]),
            atom_ids=tuple(sorted(set(item["atom_ids"]))),
            atom_relations=tuple(sorted(set(item["atom_relations"]))),
        )
        for thread_id, item in sorted(grouped.items())
    ]


def _resolve_thread(
    resolver: ThreadResolver,
    thread_link: _ThreadLink,
) -> ThreadResolution:
    try:
        resolution = resolver.resolve(thread_link.resolver_input())
    except Exception as exc:
        raise ReactionPersonalizationError(
            f"thread resolver failed for thread {thread_link.thread_id}: {type(exc).__name__}"
        ) from exc
    if not isinstance(resolution, ThreadResolution):
        raise ReactionPersonalizationError(
            "thread resolver must return ThreadResolution"
        )
    compatibility_ref = _clean_optional(resolution.compatibility_thread_ref)
    current_ref = _clean_optional(resolution.current_thread_ref)
    canonical_ref = _clean_optional(resolution.canonical_thread_ref)
    status = str(resolution.resolution_status or "").strip()
    if compatibility_ref is None or current_ref is None:
        return ThreadResolution(
            compatibility_thread_ref=compatibility_ref,
            current_thread_ref=current_ref,
            canonical_thread_ref=canonical_ref,
            resolution_status=status or "unresolved",
        )
    if not status:
        raise ReactionPersonalizationError(
            "thread resolver requires a non-empty resolution_status"
        )
    if canonical_ref is None and status != "compatibility_current_thread_only":
        raise ReactionPersonalizationError(
            "a nullable canonical thread requires compatibility_current_thread_only status"
        )
    if canonical_ref is not None and status == "compatibility_current_thread_only":
        raise ReactionPersonalizationError(
            "canonical resolution cannot use compatibility-only status"
        )
    return ThreadResolution(
        compatibility_thread_ref=compatibility_ref,
        current_thread_ref=current_ref,
        canonical_thread_ref=canonical_ref,
        resolution_status=status,
    )


def _candidate_ineligibility_reasons(
    candidate: Mapping[str, object],
    *,
    thread_link: _ThreadLink,
    atoms: Sequence[_AtomLink],
    feedback_context: Mapping[str, object],
) -> set[str]:
    reasons: set[str] = set()
    status = str(candidate.get("status") or thread_link.status or "active")
    if status in _INELIGIBLE_THREAD_STATUSES:
        reasons.add("stale_or_low_confidence_evidence")
    eligibility_fields = (
        "evidence_eligible",
        "safety_eligible",
        "period_eligible",
        "radar_eligible",
        "cited",
    )
    if any(
        field in candidate
        and (
            candidate.get(field) is False
            or (
                isinstance(candidate.get(field), (int, float))
                and not isinstance(candidate.get(field), bool)
                and candidate.get(field) == 0
            )
        )
        for field in eligibility_fields
    ):
        reasons.add("stale_or_low_confidence_evidence")
    if candidate.get("duplicate_signal") is True or candidate.get("duplicate_of"):
        reasons.add("duplicate_signal")
    if candidate.get("contradicted") is True or candidate.get("retracted") is True:
        reasons.add("contradicted_or_retracted_evidence")
    relevant_atom_ids = {atom.atom_id for atom in atoms}
    if any(
        atom_id in relevant_atom_ids and relation in {"contradicts", "supersedes"}
        for atom_id, relation in thread_link.atom_relations
    ):
        reasons.add("contradicted_or_retracted_evidence")
    all_retracted = bool(atoms) and all(
        atom.staleness_status in {"superseded", "resolved"} for atom in atoms
    )
    if all_retracted:
        reasons.add("contradicted_or_retracted_evidence")
    eligible_atoms = [
        atom
        for atom in atoms
        if atom.staleness_status not in _NON_CURRENT_ATOM_STATUSES
        and atom.source_urls
        and atom.confidence >= MIN_REACTION_ELIGIBLE_CONFIDENCE
    ]
    if not eligible_atoms and not all_retracted:
        reasons.add("stale_or_low_confidence_evidence")
    if _explicit_feedback_precedence(candidate, feedback_context) < 0:
        reasons.add("superseded_by_confirmed_feedback")
    if _atoms_have_confirmed_negative_feedback(atoms, feedback_context):
        reasons.add("superseded_by_confirmed_feedback")
    return reasons


def _atoms_have_confirmed_negative_feedback(
    atoms: Sequence[_AtomLink],
    feedback_context: Mapping[str, object],
) -> bool:
    negative_refs = set(_string_list(feedback_context.get("downranked_atom_refs")))
    negative_refs.update(_string_list(feedback_context.get("downranked_target_refs")))
    for atom in atoms:
        atom_id = str(atom.atom_id)
        if {
            atom_id,
            f"atom:{atom_id}",
            f"knowledge_atom:{atom_id}",
        }.intersection(negative_refs):
            return True
    return False


def _explicit_feedback_precedence(
    candidate: Mapping[str, object],
    feedback_context: Mapping[str, object],
) -> int:
    slug = str(candidate.get("slug") or "").strip()
    candidate_id = candidate.get("id")
    refs = {
        slug,
        f"thread:{slug}",
        f"idea_thread:{slug}",
        f"action:{slug}",
        f"experiment:{slug}",
    }
    if isinstance(candidate_id, int):
        refs.update({str(candidate_id), f"idea_thread:{candidate_id}"})
    downranked = set(_string_list(feedback_context.get("downranked_target_refs")))
    downranked.update(_string_list(feedback_context.get("downranked_thread_slugs")))
    promoted = set(_string_list(feedback_context.get("promoted_target_refs")))
    if refs.intersection(downranked):
        return -1
    score_map = feedback_context.get("_thread_feedback_scores")
    if isinstance(score_map, Mapping) and slug in score_map:
        value = score_map.get(slug)
        if isinstance(value, int) and not isinstance(value, bool) and value != 0:
            return value
    if refs.intersection(promoted):
        return 1
    return 0


def reaction_close_order_key(
    candidate: Mapping[str, object],
    feedback_context: Mapping[str, object],
) -> tuple[object, ...]:
    return (
        _explicit_feedback_precedence(candidate, feedback_context),
        bool(candidate.get("changed_this_week")),
        str(candidate.get("status") or "active") == "production_pattern",
        round(float(candidate.get("momentum_30d") or 0.0), 12),
        int(candidate.get("source_channel_count") or 0),
        str(candidate.get("last_seen_at") or ""),
        int(candidate.get("atom_count") or 0),
    )


def _project_surface_refs(
    projector: Callable[[Sequence[Mapping[str, object]]], Sequence[str]],
    candidates: Sequence[Mapping[str, object]],
    *,
    limit: int | None,
) -> list[str]:
    try:
        projected = projector(candidates)
    except Exception as exc:
        raise ReactionPersonalizationError(
            "reaction surface selection projection failed"
        ) from exc
    if isinstance(projected, (str, bytes)) or not isinstance(projected, Sequence):
        raise ReactionPersonalizationError(
            "reaction surface selection projection must return a sequence"
        )
    refs = [str(value or "").strip() for value in projected]
    if limit is not None:
        refs = refs[: max(0, int(limit))]
    if (
        len(refs) > len(candidates)
        or any(not ref.startswith("thread:") or len(ref) <= len("thread:") for ref in refs)
        or len(set(refs)) != len(refs)
    ):
        raise ReactionPersonalizationError(
            "reaction surface selection projection returned invalid item refs"
        )
    return refs


def _reader_summary(
    status: str,
    counts: Mapping[str, int],
    *,
    snapshot_status: str,
) -> str:
    if status in {"partial", "unavailable"}:
        if snapshot_status == "complete":
            if int(counts.get("personal_reaction_events_detected", 0)) == 0:
                return (
                    "Снимок личных реакций за период подтверждён, но контекст "
                    "явной обратной связи не удалось полностью проверить. Поэтому "
                    "персонализация по реакциям не применялась."
                )
            return (
                "Личные реакции на источники периода подтверждены, но контекст "
                "явной обратной связи не удалось полностью проверить. Поэтому "
                "персонализация по реакциям не применялась."
            )
        return (
            "Синхронизация реакций не завершена. Персонализация по реакциям "
            "для этого запуска не применялась."
        )
    if status == "no_eligible_reactions":
        if int(counts.get("compatibility_threads_boosted", 0)) > 0:
            return (
                "Личные реакции связаны с темами, прошедшими условия, но эти "
                "темы остались за пределом краткой выборки и не изменили выпуск. "
                "Это не снижало оценки тем."
            )
        if int(counts.get("personal_reaction_events_detected", 0)) > 0:
            return (
                "Личные реакции на источники периода найдены, но ни одна не прошла "
                "все условия для влияния на выпуск. Это не снижало оценки тем."
            )
        return (
            "Для источников этого периода личные реакции не найдены. Это не снижало "
            "оценки тем и не трактовалось как отсутствие интереса."
        )
    if status == "linked_no_selection_effect":
        if (
            int(counts.get("selected_items_linked", 0)) == 0
            and int(counts.get("compatibility_threads_boosted", 0)) > 0
        ):
            return (
                "Личные реакции связаны с темами, прошедшими условия, но эти "
                "темы остались за пределом краткой выборки и не изменили выпуск. "
                "Это не снижало оценки тем."
            )
        return (
            "Ваши отметки связаны с темами выпуска, но не изменили их место: "
            "они уже прошли по силе доказательств."
        )
    return (
        f"{int(counts.get('personal_reaction_events_detected', 0))} личных реакций → "
        f"{int(counts.get('posts_resolved', 0))} постов найдено → "
        f"{int(counts.get('unique_atoms_linked', 0))} атомов знаний → "
        f"{int(counts.get('unique_compatibility_threads_linked', 0))} тем → "
        f"{int(counts.get('selected_signals_influenced', 0))} сигналов изменили позицию."
    )


def _reader_item_reason(post_count: int) -> str:
    if post_count == 1:
        return "Вы отметили один связанный пост за отчётный период."
    return f"Вы отметили {post_count} связанных поста за отчётный период."


def _reaction_ref(observation: Mapping[str, object], raw_emoji: str) -> str:
    value = ":".join(
        (
            _normalize_channel(observation.get("channel_username")),
            str(observation.get("message_id") or ""),
            raw_emoji,
        )
    )
    return "reaction:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _post_ref(observation: Mapping[str, object]) -> str:
    value = ":".join(
        (
            _normalize_channel(observation.get("channel_username")),
            str(observation.get("message_id") or ""),
            str(observation.get("post_id") or ""),
        )
    )
    return "reaction-post:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _audit_detail(reason: str) -> str:
    return {
        "post_not_found": "stored Telegram identity did not resolve to the same normalized post",
        "outside_analysis_period": "source post timestamp falls outside the half-open analysis period",
        "knowledge_atom_not_extracted": "no bounded atom cites the normalized post identity",
        "no_thread_link": "no current Idea Thread membership exists for the cited atom",
        "no_canonical_thread_link": "canonical resolution is pending IRX-4",
        "stale_or_low_confidence_evidence": "candidate did not pass existing evidence or freshness eligibility",
        "contradicted_or_retracted_evidence": "linked evidence is superseded or retracted",
        "duplicate_signal": "a stronger equivalent signal already represents the idea",
        "superseded_by_confirmed_feedback": "confirmed explicit feedback controls ordering",
        "report_limit_reached": "eligible compatibility thread remained below the report limit",
        "confirmed_feedback_snapshot_unverified": "confirmed-feedback context could not be attested for this run",
        "snapshot_unverified": "current personal reaction visibility could not be attested",
    }[reason]


def _validate_compatibility_attribution(item: Mapping[str, object]) -> None:
    compatibility = str(item.get("compatibility_thread_ref") or "").strip()
    current = str(item.get("current_thread_ref") or "").strip()
    canonical_value = item.get("canonical_thread_ref")
    canonical = str(canonical_value or "").strip()
    resolution_status = str(item.get("thread_resolution_status") or "").strip()
    if not compatibility or not current:
        raise ReactionPersonalizationError(
            "reaction item requires compatibility and current thread attribution"
        )
    if canonical_value is not None and not canonical:
        raise ReactionPersonalizationError(
            "canonical thread attribution must be null or a non-empty string"
        )
    if not canonical and resolution_status != "compatibility_current_thread_only":
        raise ReactionPersonalizationError(
            "nullable canonical attribution requires compatibility-only status"
        )
    if canonical and resolution_status == "compatibility_current_thread_only":
        raise ReactionPersonalizationError(
            "canonical attribution cannot use compatibility-only status"
        )
    if not isinstance(item.get("surface_item_ref"), str) or not str(
        item.get("surface_item_ref")
    ).strip():
        raise ReactionPersonalizationError(
            "reaction item requires a surface item reference"
        )
    if item.get("boost_role") != "weak_implicit_interest":
        raise ReactionPersonalizationError(
            "reaction item boost role violates weak-interest policy"
        )
    if not isinstance(item.get("reader_reason_ru"), str) or not str(
        item.get("reader_reason_ru")
    ).strip():
        raise ReactionPersonalizationError("reaction item requires a reader reason")
    post_refs = item.get("reacted_post_refs")
    source_refs = item.get("source_refs")
    evidence_refs = item.get("evidence_refs")
    if (
        not isinstance(post_refs, list)
        or not post_refs
        or post_refs != sorted(set(post_refs))
        or any(
            not isinstance(value, str)
            or _REACTION_POST_REF_RE.fullmatch(value) is None
            for value in post_refs
        )
    ):
        raise ReactionPersonalizationError(
            "reaction item requires sorted unique reacted_post_refs"
        )
    if (
        not isinstance(source_refs, list)
        or not source_refs
        or source_refs != sorted(set(source_refs))
        or any(
            not isinstance(value, str)
            or _TELEGRAM_SOURCE_REF_RE.fullmatch(value) is None
            for value in source_refs
        )
    ):
        raise ReactionPersonalizationError(
            "reaction item requires sorted unique source_refs"
        )
    if (
        not isinstance(evidence_refs, list)
        or not evidence_refs
        or evidence_refs != sorted(set(evidence_refs))
        or any(
            not isinstance(value, str) or _ATOM_REF_RE.fullmatch(value) is None
            for value in evidence_refs
        )
    ):
        raise ReactionPersonalizationError(
            "reaction item requires sorted unique evidence_refs"
        )
    reacted_post_count = _positive_int(
        item.get("reacted_post_count"),
        "reacted_post_count",
    )
    if reacted_post_count != len(post_refs):
        raise ReactionPersonalizationError(
            "reacted_post_count does not match reacted_post_refs"
        )
    if item.get("reader_reason_ru") != _reader_item_reason(reacted_post_count):
        raise ReactionPersonalizationError(
            "reaction item reader reason does not match its post count"
        )


def _validate_counterfactual_item(item: Mapping[str, object]) -> None:
    effect = str(item.get("effect") or "")
    expected = {
        "selection_changed": {
            "boost_applied": True,
            "rank_changed": True,
            "selection_changed": True,
            "linked_only": False,
        },
        "rank_changed": {
            "boost_applied": True,
            "rank_changed": True,
            "selection_changed": False,
            "linked_only": False,
        },
        "linked_only": {
            "boost_applied": True,
            "rank_changed": False,
            "selection_changed": False,
            "linked_only": True,
        },
    }.get(effect)
    if expected is None or any(
        item.get(field) is not value for field, value in expected.items()
    ):
        raise ReactionPersonalizationError(
            "reaction item counterfactual flags contradict its effect"
        )


def _receipt_items(value: object, field: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ReactionPersonalizationError(f"{field} must be an array of objects")
    return list(value)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _json_array(value: object) -> list[object]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    raw = value if isinstance(value, (list, tuple, set)) else [value]
    result: list[str] = []
    for item in raw:
        clean = str(item or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _clean_optional(value: object) -> str | None:
    clean = str(value or "").strip()
    return clean or None


def _normalize_channel(value: object) -> str:
    return str(value or "").strip().lstrip("@").casefold()


def _parse_utc(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _canonical_utc(value: object, field: str) -> str:
    text = str(value or "").strip()
    parsed = _parse_utc(text)
    if parsed is None or not text.endswith("Z"):
        raise ReactionPersonalizationError(f"{field} must be a canonical UTC timestamp")
    return text


def _nonnegative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReactionPersonalizationError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    result = _nonnegative_int(value, field)
    if result < 1:
        raise ReactionPersonalizationError(f"{field} must be positive")
    return result


def _parse_week_label(value: object) -> date | None:
    match = _WEEK_RE.fullmatch(str(value or "").strip())
    if not match:
        return None
    try:
        return date.fromisocalendar(int(match.group("year")), int(match.group("week")), 1)
    except ValueError:
        return None


def _format_week(value: date) -> str:
    year, week, _day = value.isocalendar()
    return f"{year}-W{week:02d}"
