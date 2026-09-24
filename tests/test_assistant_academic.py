from datetime import datetime, timedelta, timezone

import pytest

from prm.academic_inbox import (
    ACADEMIC_READ_CAPABILITY,
    AcademicCandidate,
    AcademicDeadline,
    AcademicFetchRequest,
    CanvasScopeSelection,
    authoritative_deadline,
    build_reminder_preview,
    categorize,
    confirm_reminder,
    conflicting_deadlines,
    deduplicate_candidates,
    derive_stage,
    describe_canvas_scope,
    require_academic_read_access,
)
from prm.capabilities import (
    AuthorizationRequest,
    CapabilityDenied,
    CapabilityGrant,
    CapabilityRegistry,
    ProviderPolicy,
    transport_purpose,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
OWNER = "owner_academic_primary"
CONNECTION = "connection_academic_primary"
ACCOUNT = "account_canvas_primary"


def _scope(**changes):
    values = {
        "provider_id": "provider_canvas",
        "account_ref": ACCOUNT,
        "course_refs": ("course_ai-101",),
        "window_start": NOW - timedelta(days=7),
        "window_end": NOW + timedelta(days=30),
        "local_timezone": "America/Chicago",
        "max_items": 100,
    }
    values.update(changes)
    return CanvasScopeSelection(**values)  # type: ignore[arg-type]


def _deadline(authority="canvas", hours=24, label="Due", source="source_canvas_1"):
    return AcademicDeadline(label=label, due_at=NOW + timedelta(hours=hours), timezone="America/Chicago", authority=authority, source_ref=source)


def _candidate(ref="academic_hw_1", **changes):
    values = {
        "candidate_ref": ref,
        "owner_ref": OWNER,
        "source_kind": "canvas_assignment",
        "title": "Problem set 3",
        "summary": "Submit the problem set.",
        "category": "obligation",
        "authority": "canvas",
        "deadlines": (_deadline(),),
        "source_refs": ("source_canvas_1",),
        "source_version": "v1",
    }
    values.update(changes)
    return AcademicCandidate(**values)  # type: ignore[arg-type]


def _access():
    grant = CapabilityGrant(
        grant_id="grant_academic_primary",
        owner_ref=OWNER,
        connection_ref=CONNECTION,
        capability=ACADEMIC_READ_CAPABILITY,
        resource_refs=(ACCOUNT,),
        operations=("read",),
        data_classes=("private_connector_content",),
        purpose="academic.read",
        provider_policy=ProviderPolicy(("provider_canvas",), maximum_request_count=4),
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
        revision=1,
    )
    registry = CapabilityRegistry((grant,))
    return registry.authorize_and_reserve(
        AuthorizationRequest(
            owner_ref=OWNER,
            connection_ref=CONNECTION,
            capability=ACADEMIC_READ_CAPABILITY,
            resource_ref=ACCOUNT,
            operation="read",
            data_class="private_connector_content",
            provider_ref="provider_canvas",
            purpose="academic.read",
            operation_ref="operation_academic",
        ),
        now=NOW,
    )


def test_canvas_scope_refuses_grades_submissions_and_files():
    with pytest.raises(ValueError):
        _scope(fetch_grades=True)
    with pytest.raises(ValueError):
        _scope(fetch_submissions=True)
    with pytest.raises(ValueError):
        _scope(fetch_attachments=True)
    with pytest.raises(ValueError):
        _scope(provider_id="provider_microsoft_graph")
    text = describe_canvas_scope(_scope())
    assert "Оценки" in text and "не читаются" in text


def test_categorize_is_deterministic():
    assert categorize("canvas_assignment", "Submit the problem set") == "obligation"
    assert categorize("canvas_announcement", "Scholarship application open") == "opportunity"
    assert categorize("canvas_assignment", "Read chapter 4 and article") == "reading"
    assert categorize("mail", "Registration and ISSO deadline") == "administrative"
    assert categorize("mail", "hello there") == "uncertain"


def test_authority_precedence_and_conflicts_are_surfaced():
    candidate = _candidate(
        deadlines=(
            _deadline(authority="canvas", hours=24, source="source_canvas_1"),
            _deadline(authority="official_message", hours=48, source="source_mail_1"),
            _deadline(authority="aggregator", hours=72, source="source_nebula_1"),
        )
    )
    assert authoritative_deadline(candidate).authority == "canvas"
    assert len(conflicting_deadlines(candidate)) == 3
    same = _candidate(
        deadlines=(
            _deadline(authority="canvas", hours=24, source="source_canvas_1"),
            _deadline(authority="official_message", hours=24, source="source_mail_1"),
        )
    )
    assert conflicting_deadlines(same) == ()


def test_stage_and_completion_distinguish_local_vs_source_done():
    assert derive_stage(_candidate(), now=NOW) == "due_soon"
    assert derive_stage(_candidate(deadlines=(_deadline(hours=120),)), now=NOW) == "upcoming"
    assert derive_stage(_candidate(deadlines=(_deadline(hours=-5),)), now=NOW) == "overdue"
    local = _candidate(completion="local_done")
    source = _candidate(completion="source_completed")
    assert local.completion != source.completion
    assert derive_stage(local, now=NOW) == "completed"
    assert derive_stage(source, now=NOW) == "completed"


def test_deduplication_merges_sources_without_losing_evidence():
    canvas = _candidate(source_kind="canvas_assignment", authority="canvas", source_refs=("source_canvas_1",))
    mail = _candidate(
        candidate_ref="academic_hw_1_mail",
        source_kind="canvas_assignment",
        authority="official_message",
        source_refs=("source_mail_1",),
        deadlines=(_deadline(authority="official_message", hours=30, source="source_mail_1"),),
    )
    merged = deduplicate_candidates((mail, canvas))
    assert len(merged) == 1
    assert merged[0].authority == "canvas"
    assert set(merged[0].source_refs) == {"source_canvas_1", "source_mail_1"}
    assert len(merged[0].deadlines) == 2  # both instants preserved


def test_reminder_revision_invalidates_previous_preview():
    candidate = _candidate(source_version="v1")
    preview = build_reminder_preview(candidate, owner_ref=OWNER, lead_minutes=1440, now=NOW)
    confirm_reminder(preview, candidate=candidate, owner_ref=OWNER, now=NOW)
    with pytest.raises(ValueError):
        confirm_reminder(preview, candidate=candidate, owner_ref=OWNER, now=NOW + timedelta(hours=1))
    revised = _candidate(source_version="v2")
    with pytest.raises(ValueError):
        confirm_reminder(preview, candidate=revised, owner_ref=OWNER, now=NOW)


def test_academic_read_fails_closed_without_reservation():
    with pytest.raises(CapabilityDenied):
        require_academic_read_access(
            AcademicFetchRequest(authorization=None, owner_ref=OWNER, connection_ref=CONNECTION, selection=_scope())
        )
    require_academic_read_access(
        AcademicFetchRequest(authorization=_access(), owner_ref=OWNER, connection_ref=CONNECTION, selection=_scope())
    )
    assert (
        transport_purpose(
            provider_ref="provider_canvas",
            capability=ACADEMIC_READ_CAPABILITY,
            operation="read",
        )
        == "academic.read"
    )
