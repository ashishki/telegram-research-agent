from datetime import datetime, timedelta, timezone

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
    CONTACTS_READ_CAPABILITY,
    Contact,
    ContactsFetchRequest,
    require_contacts_read_access,
    resolve_recipient,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
OWNER = "owner_contacts_primary"
CONNECTION = "connection_contacts_primary"
ACCOUNT = "account_contacts_primary"


def _contact(ref, name, emails, account=ACCOUNT):
    return Contact(contact_ref=ref, account_ref=account, display_name=name, emails=tuple(emails))


def _registry():
    grant = CapabilityGrant(
        grant_id="grant_contacts_primary",
        owner_ref=OWNER,
        connection_ref=CONNECTION,
        capability=CONTACTS_READ_CAPABILITY,
        resource_refs=(ACCOUNT,),
        operations=("read",),
        data_classes=("private_connector_content",),
        purpose="contacts.read",
        provider_policy=ProviderPolicy(("provider_microsoft_graph",), maximum_request_count=4),
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
        revision=1,
    )
    return CapabilityRegistry((grant,))


def test_contact_validation_rejects_bad_email_and_duplicates():
    with pytest.raises(ValueError):
        _contact("contact_1", "Ann", ["not-an-email"])
    with pytest.raises(ValueError):
        _contact("contact_1", "Ann", ["a@b.co", "a@b.co"])
    with pytest.raises(ValueError):
        _contact("contact_1", "Ann", [])


def test_resolve_recipient_never_guesses():
    contacts = (
        _contact("contact_ann", "Ann Smith", ["ann@example.com"]),
        _contact("contact_an", "Andrey Volkov", ["andrey@example.com"]),
    )
    resolved = resolve_recipient("ann@example.com", contacts)
    assert resolved.status == "resolved"
    assert resolved.contact_ref == "contact_ann"

    # A substring that matches two people must stay ambiguous, never pick one.
    ambiguous = resolve_recipient("an", contacts)
    assert ambiguous.status == "ambiguous"
    assert ambiguous.contact_ref is None
    assert len(ambiguous.candidates) == 2

    assert resolve_recipient("nobody", contacts).status == "not_found"


def test_resolve_recipient_scopes_to_selected_accounts():
    contacts = (
        _contact("contact_a", "Ann", ["ann@work.com"], account="account_calendar_primary"),
        _contact("contact_b", "Ann", ["ann@home.com"], account="account_home"),
    )
    scoped = resolve_recipient("Ann", contacts, accounts=("account_home",))
    assert scoped.status == "resolved"
    assert scoped.contact_ref == "contact_b"


def test_contacts_read_fails_closed_without_reservation():
    with pytest.raises(CapabilityDenied):
        require_contacts_read_access(
            ContactsFetchRequest(
                authorization=None,
                owner_ref=OWNER,
                connection_ref=CONNECTION,
                provider_id="provider_microsoft_graph",
                account_ref=ACCOUNT,
            )
        )
    decision = _registry().authorize_and_reserve(
        AuthorizationRequest(
            owner_ref=OWNER,
            connection_ref=CONNECTION,
            capability=CONTACTS_READ_CAPABILITY,
            resource_ref=ACCOUNT,
            operation="read",
            data_class="private_connector_content",
            provider_ref="provider_microsoft_graph",
            purpose="contacts.read",
            operation_ref="operation_contacts",
        ),
        now=NOW,
    )
    require_contacts_read_access(
        ContactsFetchRequest(
            authorization=decision,
            owner_ref=OWNER,
            connection_ref=CONNECTION,
            provider_id="provider_microsoft_graph",
            account_ref=ACCOUNT,
        )
    )
    assert (
        transport_purpose(
            provider_ref="provider_microsoft_graph",
            capability=CONTACTS_READ_CAPABILITY,
            operation="read",
        )
        == "contacts.read"
    )
