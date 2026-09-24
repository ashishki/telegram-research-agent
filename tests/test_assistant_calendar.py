from datetime import date, datetime, timedelta, timezone

import pytest

from prm.capabilities import (
    AuthorizationRequest,
    CapabilityDenied,
    CapabilityGrant,
    CapabilityRegistry,
    ProviderPolicy,
    transport_purpose,
)
from prm.schedule_connectors import (
    CALENDAR_READ_CAPABILITY,
    CalendarConsentPreview,
    CalendarEvent,
    CalendarFetchRequest,
    CalendarScopeSelection,
    RecurrenceRule,
    build_calendar_consent_preview,
    confirm_calendar_scope,
    describe_calendar_scope,
    detect_conflicts,
    free_busy,
    require_calendar_read_access,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
OWNER = "owner_calendar_primary"
CONNECTION = "connection_calendar_primary"
ACCOUNT = "account_calendar_primary"


def _scope(**changes):
    values = {
        "provider_id": "provider_microsoft_graph",
        "account_ref": ACCOUNT,
        "calendar_refs": ("calendar_work", "calendar_personal"),
        "window_start": NOW,
        "window_end": NOW + timedelta(days=7),
        "local_timezone": "Europe/Berlin",
        "max_items": 50,
    }
    values.update(changes)
    return CalendarScopeSelection(**values)  # type: ignore[arg-type]


def _event(ref="event_1", **changes):
    values = {
        "event_ref": ref,
        "calendar_ref": "calendar_work",
        "account_ref": ACCOUNT,
        "title": "Standup",
        "start_at": NOW + timedelta(hours=1),
        "end_at": NOW + timedelta(hours=2),
        "source_timezone": "Europe/Berlin",
    }
    values.update(changes)
    return CalendarEvent(**values)  # type: ignore[arg-type]


def _registry():
    grant = CapabilityGrant(
        grant_id="grant_calendar_primary",
        owner_ref=OWNER,
        connection_ref=CONNECTION,
        capability=CALENDAR_READ_CAPABILITY,
        resource_refs=(ACCOUNT,),
        operations=("read",),
        data_classes=("private_connector_content",),
        purpose="calendar.read",
        provider_policy=ProviderPolicy(("provider_microsoft_graph",), maximum_request_count=4),
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
        revision=1,
    )
    return CapabilityRegistry((grant,))


def _decision():
    return _registry().authorize_and_reserve(
        AuthorizationRequest(
            owner_ref=OWNER,
            connection_ref=CONNECTION,
            capability=CALENDAR_READ_CAPABILITY,
            resource_ref=ACCOUNT,
            operation="read",
            data_class="private_connector_content",
            provider_ref="provider_microsoft_graph",
            purpose="calendar.read",
            operation_ref="operation_calendar",
        ),
        now=NOW,
    )


def test_scope_validation_and_honest_description():
    with pytest.raises(ValueError):
        _scope(calendar_refs=())
    with pytest.raises(ValueError):
        _scope(window_end=NOW - timedelta(hours=1))
    with pytest.raises(ValueError):
        _scope(local_timezone="Mars/Olympus")
    with pytest.raises(ValueError):
        _scope(max_items=0)
    text = describe_calendar_scope(_scope())
    assert "Только чтение" in text
    assert "выбран явно" in text


def test_consent_preview_binds_identity_scope_and_expiry():
    selection = _scope()
    preview = build_calendar_consent_preview(selection, owner_ref=OWNER, connection_ref=CONNECTION, now=NOW)
    confirm_calendar_scope(preview, selection=selection, owner_ref=OWNER, connection_ref=CONNECTION, now=NOW)
    with pytest.raises(ValueError):
        confirm_calendar_scope(
            preview, selection=selection, owner_ref=OWNER, connection_ref=CONNECTION, now=NOW + timedelta(hours=1)
        )
    with pytest.raises(ValueError):
        confirm_calendar_scope(
            preview, selection=_scope(max_items=51), owner_ref=OWNER, connection_ref=CONNECTION, now=NOW
        )


def test_event_timezones_conflicts_and_free_busy():
    a = _event("event_a", start_at=NOW, end_at=NOW + timedelta(hours=1))
    b = _event("event_b", start_at=NOW + timedelta(minutes=30), end_at=NOW + timedelta(hours=2))
    c = _event("event_c", start_at=NOW + timedelta(hours=3), end_at=NOW + timedelta(hours=4))
    cancelled = _event("event_d", start_at=NOW, end_at=NOW + timedelta(hours=5), status="cancelled")
    pairs = detect_conflicts((a, b, c, cancelled))
    assert pairs == (("event_a", "event_b"),)
    assert len(free_busy((a, b, c, cancelled), local_timezone="Europe/Berlin")) == 3
    local_start, _ = a.local_span("Europe/Berlin")
    assert local_start.tzinfo is not None
    with pytest.raises(ValueError):
        _event("event_bad", end_at=NOW - timedelta(hours=1))


def test_recurrence_rules_are_bounded():
    rule = RecurrenceRule(dtstart=NOW, freq="weekly", interval=1, count=3)
    assert rule.occurs_on(NOW.date()) is True
    assert rule.occurs_on((NOW + timedelta(days=7)).date()) is True
    assert rule.occurs_on((NOW + timedelta(days=21)).date()) is False  # count=3 exhausted
    assert rule.occurs_on((NOW + timedelta(days=1)).date()) is False
    monthly = RecurrenceRule(dtstart=NOW, freq="monthly", interval=1)
    assert monthly.occurs_on(NOW.date()) is True
    with pytest.raises(ValueError):
        RecurrenceRule(dtstart=NOW, freq="hourly")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        RecurrenceRule(dtstart=NOW, freq="daily", count=2, until=NOW + timedelta(days=1))


def test_calendar_read_fails_closed_without_reservation():
    selection = _scope()
    with pytest.raises(CapabilityDenied):
        require_calendar_read_access(
            CalendarFetchRequest(authorization=None, owner_ref=OWNER, connection_ref=CONNECTION, selection=selection)
        )
    require_calendar_read_access(
        CalendarFetchRequest(authorization=_decision(), owner_ref=OWNER, connection_ref=CONNECTION, selection=selection)
    )
    assert (
        transport_purpose(
            provider_ref="provider_microsoft_graph",
            capability=CALENDAR_READ_CAPABILITY,
            operation="read",
        )
        == "calendar.read"
    )
