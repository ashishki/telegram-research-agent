"""PA-10 read-only mail connector holdouts; all state is temporary SQLite."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from prm.capabilities import (
    AuthorizationRequest,
    CapabilityDenied,
    CapabilityGrant,
    CapabilityRegistry,
    ProviderPolicy,
    transport_purpose,
)
from prm.mail_connector import (
    MAIL_READ_CAPABILITY,
    MAIL_READ_PROVIDER,
    MAIL_READ_PURPOSE,
    MailConsentConfirmation,
    MailDeadline,
    MailDerivedStore,
    MailFetchPage,
    MailFetchRequest,
    MailMessage,
    MailScopeSelection,
    MailThreadSummary,
    build_mail_consent_preview,
    confirm_mail_scope,
    describe_mail_scope,
    mail_owner_ref_from_authenticated_private_tuple,
    require_mail_read_access,
    resolve_mail_provider,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
OWNER_TUPLE = ("42", "42", "42")
OWNER_REF = mail_owner_ref_from_authenticated_private_tuple(*OWNER_TUPLE)
assert OWNER_REF is not None
MAILBOX = "mailbox_private_utd_101"
CONNECTION = "connection_microsoft_101"
_OPERATION_SEQUENCE = count(2000)


def _scope(**changes: object) -> MailScopeSelection:
    values: dict[str, object] = {
        "provider_id": MAIL_READ_PROVIDER,
        "resource_ref": MAILBOX,
        "folders": ("Inbox/UTD",),
        "sender_domains": ("utdallas.edu",),
        "max_items": 25,
    }
    values.update(changes)
    return MailScopeSelection(**values)  # type: ignore[arg-type]


def _summary(**changes: object) -> MailThreadSummary:
    values: dict[str, object] = {
        "summary_ref": "summary_mail_101",
        "owner_ref": OWNER_REF,
        "provider_id": MAIL_READ_PROVIDER,
        "thread_ref": "thread_mail_101",
        "subject": "Registration deadline",
        "category": "administrative",
        "takeaways": ("Registration closes Friday.",),
        "decisions": ("Confirm enrollment.",),
        "deadlines": (
            MailDeadline(
                text="Registration closes",
                due_at=NOW + timedelta(days=3),
                timezone="America/Chicago",
                authority="official_message",
                source_ref="message_utd_101",
            ),
        ),
        "opportunities": (),
        "excerpt": "Please complete your registration before the deadline.",
        "source_refs": ("message_utd_101",),
        "retrieved_at": NOW,
        "freshness": "fresh",
    }
    values.update(changes)
    return MailThreadSummary(**values)  # type: ignore[arg-type]


def _registry() -> CapabilityRegistry:
    grant = CapabilityGrant(
        grant_id="grant_mail_read_101",
        owner_ref=OWNER_REF,
        connection_ref=CONNECTION,
        capability=MAIL_READ_CAPABILITY,
        resource_refs=(MAILBOX,),
        operations=("read",),
        data_classes=("private_connector_content",),
        purpose=MAIL_READ_PURPOSE,
        provider_policy=ProviderPolicy((MAIL_READ_PROVIDER,), maximum_request_count=4),
        issued_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=1),
        revision=1,
    )
    return CapabilityRegistry((grant,))


def _fetch_request(authorization: object, *, selection: MailScopeSelection | None = None) -> MailFetchRequest:
    return MailFetchRequest(
        authorization=authorization,  # type: ignore[arg-type]
        owner_ref=OWNER_REF,
        connection_ref=CONNECTION,
        selection=selection or _scope(),
        page_size=10,
    )


def test_owner_ref_only_from_canonical_private_tuple():
    assert mail_owner_ref_from_authenticated_private_tuple("42", "42", "42") == OWNER_REF
    assert mail_owner_ref_from_authenticated_private_tuple("42", "43", "42") is None
    assert mail_owner_ref_from_authenticated_private_tuple(None, "42", "42") is None


def test_provider_is_explicit_and_never_guessed():
    profile = resolve_mail_provider(MAIL_READ_PROVIDER)
    assert profile.token_scope_is_mailbox_wide is True
    with pytest.raises(ValueError):
        resolve_mail_provider("utdallas.edu")


def test_scope_selection_fails_closed_on_bodies_and_attachments():
    with pytest.raises(ValueError):
        _scope(fetch_body=True)
    with pytest.raises(ValueError):
        _scope(include_attachments=True)
    with pytest.raises(ValueError):
        _scope(max_items=0)
    with pytest.raises(ValueError):
        _scope(max_items=10_000)
    with pytest.raises(ValueError):
        _scope(since=NOW, until=NOW - timedelta(days=1))
    with pytest.raises(ValueError):
        _scope(folders=("a", "a"))


def test_scope_description_is_honest_about_mailbox_wide_token():
    text = describe_mail_scope(_scope())
    assert "весь ящик" in text
    assert "прикладной фильтр" in text
    assert "Вложения не читаются" in text


def test_consent_preview_binds_identity_scope_and_expiry():
    selection = _scope()
    preview = build_mail_consent_preview(
        selection, owner_ref=OWNER_REF, connection_ref=CONNECTION, now=NOW
    )
    confirmation = MailConsentConfirmation(
        owner_ref=OWNER_REF,
        connection_ref=CONNECTION,
        scope_digest=selection.scope_digest,
        confirmed_at=NOW,
    )
    confirm_mail_scope(preview, confirmation, selection=selection, now=NOW)

    with pytest.raises(ValueError):
        confirm_mail_scope(preview, confirmation, selection=selection, now=NOW + timedelta(hours=1))

    changed = _scope(max_items=26)
    with pytest.raises(ValueError):
        confirm_mail_scope(preview, confirmation, selection=changed, now=NOW)

    other_owner = MailConsentConfirmation(
        owner_ref="owner_mail_other_101",
        connection_ref=CONNECTION,
        scope_digest=selection.scope_digest,
        confirmed_at=NOW,
    )
    with pytest.raises(ValueError):
        confirm_mail_scope(preview, other_owner, selection=selection, now=NOW)


def test_transport_purpose_is_registered_for_mail_read_only():
    assert (
        transport_purpose(
            provider_ref=MAIL_READ_PROVIDER,
            capability=MAIL_READ_CAPABILITY,
            operation="read",
        )
        == MAIL_READ_PURPOSE
    )
    with pytest.raises(CapabilityDenied):
        transport_purpose(
            provider_ref="provider_public_web",
            capability=MAIL_READ_CAPABILITY,
            operation="read",
        )


def test_mail_read_requires_a_matching_reservation():
    registry = _registry()
    operation_ref = f"operation_mail_{next(_OPERATION_SEQUENCE)}"
    decision = registry.authorize_and_reserve(
        AuthorizationRequest(
            owner_ref=OWNER_REF,
            connection_ref=CONNECTION,
            capability=MAIL_READ_CAPABILITY,
            resource_ref=MAILBOX,
            operation="read",
            data_class="private_connector_content",
            provider_ref=MAIL_READ_PROVIDER,
            purpose=MAIL_READ_PURPOSE,
            operation_ref=operation_ref,
        ),
        now=NOW,
    )
    require_mail_read_access(_fetch_request(decision))

    with pytest.raises(CapabilityDenied):
        require_mail_read_access(_fetch_request(None))

    disabled_provider = _scope(provider_id="provider_gmail", resource_ref=MAILBOX)
    with pytest.raises(CapabilityDenied):
        require_mail_read_access(_fetch_request(decision, selection=disabled_provider))


def test_summary_detects_conflicting_deadlines_and_round_trips():
    summary = _summary()
    assert summary.has_conflicting_deadlines is False
    conflicting = _summary(
        deadlines=(
            MailDeadline(
                text="Canvas says Friday",
                due_at=NOW + timedelta(days=5),
                timezone="America/Chicago",
                authority="official_message",
                source_ref="message_utd_201",
            ),
            summary.deadlines[0],
        )
    )
    assert conflicting.has_conflicting_deadlines is True

    restored = MailThreadSummary.from_payload(summary.to_payload())
    assert restored.content_digest == summary.content_digest
    assert restored.deadlines[0].due_at == summary.deadlines[0].due_at

    with pytest.raises(ValueError):
        _summary(category="spam")


def test_derived_store_keeps_only_normalized_summaries(tmp_path):
    store = MailDerivedStore(tmp_path / "mail.db")
    summary = _summary()
    store.write_summary(summary, connection_ref=CONNECTION)
    store.write_summary(
        _summary(subject="Updated subject"), connection_ref=CONNECTION
    )
    rows = store.list_summaries(OWNER_REF)
    assert len(rows) == 1
    assert rows[0].subject == "Updated subject"
    assert store.count(OWNER_REF) == 1

    assert store.delete_connection(OWNER_REF, CONNECTION) == 1
    assert store.count(OWNER_REF) == 0

    store.write_summary(summary, connection_ref=CONNECTION)
    assert store.delete_owner(OWNER_REF) == 1
    assert store.count(OWNER_REF) == 0


def test_from_payload_rejects_malformed_and_foreign_schema_payloads():
    with pytest.raises((ValueError, TypeError)):
        MailThreadSummary.from_payload({"schema_version": "assistant.mail_thread_summary.v1"})

    payload = _summary().to_payload()
    payload["schema_version"] = "assistant.mail_thread_summary.v99"
    with pytest.raises(ValueError):
        MailThreadSummary.from_payload(payload)


def test_fetch_request_page_size_is_bounded_by_confirmed_scope():
    with pytest.raises(ValueError):
        MailFetchRequest(
            authorization=None,  # type: ignore[arg-type]
            owner_ref=OWNER_REF,
            connection_ref=CONNECTION,
            selection=_scope(max_items=5),
            page_size=50,
        )
    with pytest.raises(ValueError):
        MailFetchRequest(
            authorization="not-a-decision",  # type: ignore[arg-type]
            owner_ref=OWNER_REF,
            connection_ref=CONNECTION,
            selection=_scope(),
            page_size=10,
        )


def test_fetch_page_rejects_duplicate_messages_and_unbounded_more():
    message = MailMessage(
        message_ref="message_utd_101",
        thread_ref="thread_mail_101",
        received_at=NOW,
        sender_domain="utdallas.edu",
        subject="Hi",
        snippet="Body",
    )
    page = MailFetchPage(messages=(message,), next_cursor=None, has_more=False)
    assert page.messages[0].message_ref == "message_utd_101"

    with pytest.raises(ValueError):
        MailFetchPage(messages=(message, message), next_cursor=None, has_more=False)
    with pytest.raises(ValueError):
        MailFetchPage(messages=(message,), next_cursor=None, has_more=True)
