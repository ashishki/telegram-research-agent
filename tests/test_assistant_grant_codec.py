"""PA-01 capability-grant document decoding at the PA-02 enforcement boundary."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from prm.capabilities import (
    AuthorizationRequest,
    CapabilityDenied,
    CapabilityGrantDocumentError,
    CapabilityRegistry,
    decode_capability_grant_document,
    require_authorized_egress,
)


FIXTURE_NOW = datetime(2026, 9, 18, 0, 1, tzinfo=timezone.utc)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "assistant" / "pa01_acceptance_corpus.v1.json"


def _grant_document() -> dict[str, object]:
    corpus = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return deepcopy(corpus["contract_examples"]["capability_grant"])


def _model_egress_document(*, revision: int = 3) -> dict[str, object]:
    document = _grant_document()
    document["capability"] = {
        "name": "model.generate",
        "resource_refs": ["resource_conversation"],
        "operations": ["model_egress"],
        "data_classes": ["user_provided"],
        "purpose": "answer.request",
    }
    document["provider_policy"] = {
        "egress": "allow",
        "permitted_provider_refs": ["provider_openai"],
        "fallback_allowed": False,
        "maximum_request_count": 1,
    }
    document["validity"]["revision"] = revision
    return document


def _model_request(*, revision: int = 3) -> AuthorizationRequest:
    return AuthorizationRequest(
        owner_ref="owner_synthetic_primary",
        connection_ref=None,
        capability="model.generate",
        resource_ref="resource_conversation",
        operation="model_egress",
        data_class="user_provided",
        provider_ref="provider_openai",
        purpose="answer.request",
        expected_grant_revision=revision,
    )


def test_decoder_accepts_the_complete_pa01_grant_shape_and_preserves_egress_deny():
    grant = decode_capability_grant_document(_grant_document(), now=FIXTURE_NOW)

    assert grant.grant_id == "grant_synthetic_archive_read"
    assert grant.capability == "archive.search"
    assert grant.provider_policy.egress_allowed is False
    assert grant.provider_policy.permitted_provider_refs == ()

    denied_document = _model_egress_document()
    denied_document["provider_policy"]["egress"] = "deny"
    denied_document["provider_policy"]["permitted_provider_refs"] = []
    decision = CapabilityRegistry((decode_capability_grant_document(denied_document, now=FIXTURE_NOW),)).authorize(
        _model_request(),
        now=FIXTURE_NOW,
    )

    assert decision.allowed is False
    assert decision.reason == "egress_denied"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document.pop("schema_version"),
        lambda document: document.__setitem__("status", "revoked"),
        lambda document: document["provider_policy"].__setitem__("permitted_provider_refs", ["provider_openai"]),
    ],
)
def test_decoder_rejects_incomplete_or_inconsistent_documents_fail_closed(mutate):
    document = _grant_document()
    mutate(document)

    with pytest.raises(CapabilityGrantDocumentError):
        decode_capability_grant_document(document, now=FIXTURE_NOW)


def test_decoder_preserves_revocation_and_revision_for_reservation_revalidation():
    revoked_document = _grant_document()
    revoked_document["validity"]["revoked_at"] = "2026-09-17T23:59:00Z"
    revoked_document["status"] = "revoked"
    assert decode_capability_grant_document(revoked_document, now=FIXTURE_NOW).state_at(FIXTURE_NOW) == "revoked"

    registry = CapabilityRegistry((decode_capability_grant_document(_model_egress_document(), now=FIXTURE_NOW),))
    reservation = registry.authorize_and_reserve(_model_request(), now=FIXTURE_NOW)
    registry.replace_grant(decode_capability_grant_document(_model_egress_document(revision=4), now=FIXTURE_NOW))

    with pytest.raises(CapabilityDenied):
        require_authorized_egress(
            reservation,
            capability="model.generate",
            provider_ref="provider_openai",
            data_class="user_provided",
            owner_ref="owner_synthetic_primary",
            connection_ref=None,
            resource_ref="resource_conversation",
        )
