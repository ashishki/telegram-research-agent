"""Bounded editorial stories, kept separately from source excerpts and priority facts.

Anchor validation proves citation identity and quoted support, not semantic truth.
Human-calibrated content evaluation remains a separate acceptance requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import uuid
from typing import Mapping, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from prm.briefs import BriefDocument, BriefEvidence
    from prm.contracts import ArchiveSynthesisAccess


@dataclass(frozen=True, slots=True)
class StoryAnchor:
    evidence_ref: str
    quote: str


@dataclass(frozen=True, slots=True)
class BriefStory:
    title: str
    summary: str
    explanation: str
    why_selected: str
    next_step: str
    caveat: str
    anchors: tuple[StoryAnchor, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title, "summary": self.summary,
            "explanation": self.explanation, "why_selected": self.why_selected,
            "next_step": self.next_step, "caveat": self.caveat,
            "anchors": [{"evidence_ref": a.evidence_ref, "quote": a.quote} for a in self.anchors],
        }


@dataclass(frozen=True, slots=True)
class BriefEditorial:
    stories: tuple[BriefStory, ...]
    omitted_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"stories": [story.to_dict() for story in self.stories], "omitted_refs": list(self.omitted_refs)}

    @classmethod
    def from_dict(cls, value: object, evidence: Sequence[BriefEvidence]) -> BriefEditorial:
        if not isinstance(value, dict) or set(value) != {"stories", "omitted_refs"}:
            raise ValueError("invalid editorial object")
        rows, omitted = value["stories"], value["omitted_refs"]
        if not isinstance(rows, list) or len(rows) > 5:
            raise ValueError("invalid editorial story count")
        sources = {item.evidence_ref: item for item in evidence}
        if (not isinstance(omitted, list) or any(not isinstance(ref, str) or ref not in sources for ref in omitted)
                or len(set(omitted)) != len(omitted)):
            raise ValueError("invalid editorial omissions")
        stories = []
        used = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "title", "summary", "explanation", "why_selected", "next_step", "caveat", "anchors",
            }:
                raise ValueError("invalid editorial story")
            anchors = row["anchors"]
            if not isinstance(anchors, list) or not 1 <= len(anchors) <= 8:
                raise ValueError("invalid editorial anchors")
            bound = []
            for anchor in anchors:
                if not isinstance(anchor, dict) or set(anchor) != {"evidence_ref", "quote"}:
                    raise ValueError("invalid editorial anchor")
                ref = anchor["evidence_ref"]
                quote = _text(anchor["quote"], 1200)
                if (not isinstance(ref, str) or ref not in sources or len(quote) < 16
                        or quote not in sources[ref].summary):
                    raise ValueError("editorial anchor lacks exact selected support")
                bound.append(StoryAnchor(ref, quote))
                used.add(ref)
            story = BriefStory(
                title=_text(row["title"], 140), summary=_text(row["summary"], 300),
                explanation=_text(row["explanation"], 900), why_selected=_text(row["why_selected"], 300),
                next_step=_text(row["next_step"], 300, optional=True),
                caveat=_text(row["caveat"], 300, optional=True), anchors=tuple(bound),
            )
            if story.title.startswith("@"):
                raise ValueError("editorial headline must describe an event")
            # Reject new numeric factual claims. This is deliberately not a
            # semantic verifier and must never be reported as one.
            support = " ".join(anchor.quote for anchor in bound)
            factual = " ".join((story.title, story.summary, story.explanation))
            if set(re.findall(r"\d+(?:[.,]\d+)?", factual)) - set(re.findall(r"\d+(?:[.,]\d+)?", support)):
                raise ValueError("editorial introduces an unsupported numeric claim")
            stories.append(story)
        if used & set(omitted) or used | set(omitted) != set(sources):
            raise ValueError("editorial must account for every selected source")
        if len({story.title.casefold() for story in stories}) != len(stories):
            raise ValueError("duplicate editorial stories")
        return cls(tuple(stories), tuple(omitted))


def _text(value: object, maximum: int, *, optional: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid editorial text")
    clean = " ".join(value.split())
    if len(clean) > maximum or (not clean and not optional) or re.search(r"https?://|<[^>]+>", clean):
        raise ValueError("invalid editorial text")
    return clean


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate editorial JSON key")
        result[key] = value
    return result


def synthesize_brief_editorial(
    document: BriefDocument, *, question: str, access: ArchiveSynthesisAccess | None,
) -> tuple[BriefEditorial | None, Mapping[str, object]]:
    """Generation and isolated content review, each with its own reserved call."""
    from prm.archive_context import ArchiveEvidenceContext
    from prm.archive_synthesis_transport import (
        ArchiveSynthesisTransportEmptyResponse, ArchiveSynthesisTransportOutcomeUnknown,
        ArchiveSynthesisTransportUnavailable, complete_archive_synthesis,
    )
    from prm.contracts import ArchiveSynthesisAccess
    from prm.synthesis import _abandon_archive_access

    if type(access) is not ArchiveSynthesisAccess:
        return None, {"status": "authorization_required", "provider_egress_attempted": False}
    # The existing archive transport has an eight-source bound. Never silently
    # send just a prefix while presenting the whole selection as synthesized.
    if not document.evidence or len(document.evidence) > 8:
        _abandon_archive_access(access)
        return None, {"status": "context_unavailable", "provider_egress_attempted": False}
    evidence = [{
        "evidence_id": item.evidence_ref, "source_url": item.source_ref,
        "support_span": item.summary, "local_archive_provenance": True,
    } for item in document.evidence]
    findings = [{
        "evidence_id": item.evidence_ref, "source_url": item.source_ref,
        "title": item.title, "relevance_label": "partial",
    } for item in document.evidence]
    context = ArchiveEvidenceContext.from_payload(
        question=question,
        archive_contract={"direct_findings": [], "partial_findings": findings, "adjacent_findings": []},
        evidence_items=evidence,
    )
    if context is None:
        _abandon_archive_access(access)
        return None, {"status": "context_unavailable", "provider_egress_attempted": False}
    review_access = _reserve_content_review(access)
    if review_access is None:
        _abandon_archive_access(access)
        return None, {"status": "review_budget_or_authorization_required", "provider_egress_attempted": False}
    try:
        result = complete_archive_synthesis(context=context, access=access, response_mode="brief_editorial")
    except ArchiveSynthesisTransportEmptyResponse as exc:
        _abandon_archive_access(review_access)
        return None, {**exc.receipt.public_measurement(), "status": "provider_empty_response"}
    except ArchiveSynthesisTransportOutcomeUnknown:
        _abandon_archive_access(review_access)
        return None, {"status": "provider_outcome_unknown", "provider_egress_attempted": True}
    except ArchiveSynthesisTransportUnavailable:
        _abandon_archive_access(review_access)
        return None, {"status": "provider_unavailable_or_denied", "provider_egress_attempted": False}
    try:
        if len(result.text) > 18000:
            raise ValueError("editorial response too large")
        editorial = BriefEditorial.from_dict(json.loads(result.text, object_pairs_hook=_unique_object), document.evidence)
    except (ValueError, TypeError, RecursionError):
        _abandon_archive_access(review_access)
        return None, {**result.receipt.public_measurement(), "status": "editorial_rejected"}
    try:
        review = complete_archive_synthesis(
            context=context, access=review_access, response_mode="brief_review", editorial_candidate=editorial,
        )
        if len(review.text) > 2000:
            raise ValueError("content review too large")
        verdict = json.loads(review.text, object_pairs_hook=_unique_object)
        if (not isinstance(verdict, dict) or set(verdict) != {"verdict", "issues"}
                or verdict != {"verdict": "pass", "issues": []}):
            raise ValueError("content review rejected editorial")
    except (ArchiveSynthesisTransportEmptyResponse, ArchiveSynthesisTransportOutcomeUnknown,
            ArchiveSynthesisTransportUnavailable, ValueError, TypeError, RecursionError):
        _abandon_archive_access(review_access)
        return None, {**result.receipt.public_measurement(), "status": "content_review_failed"}
    return editorial, {
        **result.receipt.public_measurement(), "status": "source_anchored_reviewed",
        "semantic_verification": "model_review_passed", "provider_request_count": 2,
        "story_count": len(editorial.stories),
        "omitted_source_count": len(editorial.omitted_refs),
    }


def _reserve_content_review(access: ArchiveSynthesisAccess) -> ArchiveSynthesisAccess | None:
    """Reserve under the same existing grants; never create/expand a grant.

    A one-call grant cannot generate an unreviewed briefing. Both review scopes
    must be reserved before spending the generation call. Revocation and expiry
    are checked again by the transport for each distinct operation.
    """
    from prm.capabilities import AuthorizationRequest
    from prm.contracts import ArchiveSynthesisAccess

    operation_ref = "operation_brief_review_" + uuid.uuid4().hex
    decisions = []
    for original in (access.query_authorization, access.context_authorization):
        reservation = original.reservation
        if reservation is None:
            return None
        decision = reservation.registry.authorize_and_reserve(AuthorizationRequest(
            owner_ref=original.owner_ref, connection_ref=original.connection_ref,
            capability=original.capability, resource_ref=original.resource_ref,
            operation=original.operation, data_class=original.data_class,
            provider_ref=original.provider_ref, purpose=original.purpose,
            expected_grant_revision=original.grant_revision, grant_ref=original.grant_ref,
            operation_ref=operation_ref,
        ))
        decisions.append(decision)
        if not decision.allowed:
            for item in decisions:
                if item.reservation is not None:
                    item.reservation.abandon_before_transport()
            return None
    return ArchiveSynthesisAccess(
        query_authorization=decisions[0], context_authorization=decisions[1],
        owner_ref=access.owner_ref, connection_ref=access.connection_ref,
        query_resource_ref=access.query_resource_ref, context_resource_ref=access.context_resource_ref,
    )
