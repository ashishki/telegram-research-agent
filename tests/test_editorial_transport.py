import json
from datetime import datetime, timedelta, timezone

import pytest

from prm.briefs import BriefBuildRequest, BriefWindow, CoverageSource, build_brief_document
from prm.capabilities import (
    AuthorizationRequest,
    CapabilityGrant,
    CapabilityRegistry,
    ProviderPolicy,
    transport_purpose,
)
from prm.editorial_transport import (
    OPENCODE_EDITORIAL_PROVIDER,
    OpenCodeEditorialAccess,
    build_operator_editorial_access,
    editorial_enabled,
    synthesize_opencode_editorial,
)


def _document():
    window = BriefWindow.from_iso(
        timezone_name="Europe/Berlin",
        start_at="2026-10-19T00:00:00+02:00",
        end_at="2026-10-26T00:00:00+01:00",
        generated_at="2026-10-26T01:15:00+01:00",
    )
    evidence = (
        {
            "local_archive_provenance": True,
            "evidence_id": "evidence_one",
            "source_url": "https://t.me/example/1",
            "title": "Новый релиз",
            "support_span": "Яндекс опубликовал открытую модель для быстрых ответов в поиске.",
            "posted_at": "2026-10-21T10:00:00+02:00",
            "topics": ("AI",),
        },
    )
    request = BriefBuildRequest(
        topic="AI",
        window=window,
        coverage=(CoverageSource("local_archive_selected_evidence", "partial"),),
        evidence=evidence,
    )
    return build_brief_document(request)


def _access():
    return build_operator_editorial_access(
        owner_ref="owner_editorial_cli",
        connection_ref="connection_editorial_cli",
        resource_ref="resource_editorial_cli",
        consent="enable-opencode-editorial",
        now=datetime.now(timezone.utc),
    )


def test_editorial_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PRM_EDITORIAL_OPENCODE_ENABLED", raising=False)
    assert editorial_enabled() is False
    editorial, measurement = synthesize_opencode_editorial(_document(), question="AI", access=None)
    assert editorial is None
    assert measurement["status"] == "disabled"
    assert measurement["provider_egress_attempted"] is False


def test_access_requires_exact_consent_and_matches_scope():
    with pytest.raises(ValueError):
        build_operator_editorial_access(
            owner_ref="owner_editorial_cli",
            connection_ref="connection_editorial_cli",
            resource_ref="resource_editorial_cli",
            consent="yes",
        )
    access = _access()
    assert access.authorization.provider_ref == OPENCODE_EDITORIAL_PROVIDER
    assert access.authorization.purpose == "answer.context"
    assert access.authorization.reservation is not None


def test_purpose_mapping_registered_for_opencode():
    assert (
        transport_purpose(
            provider_ref=OPENCODE_EDITORIAL_PROVIDER,
            capability="model.context_egress",
            operation="model_egress",
        )
        == "answer.context"
    )


def test_synthesize_requires_typed_access_when_enabled(monkeypatch):
    monkeypatch.setenv("PRM_EDITORIAL_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    editorial, measurement = synthesize_opencode_editorial(_document(), question="AI", access=None)
    assert editorial is None
    assert measurement["status"] == "authorization_required"


def test_access_rejects_decision_from_another_provider():
    now = datetime.now(timezone.utc)
    grant = CapabilityGrant(
        grant_id="grant_other_provider",
        owner_ref="owner_editorial_cli",
        connection_ref="connection_editorial_cli",
        capability="model.context_egress",
        resource_refs=("resource_editorial_cli",),
        operations=("model_egress",),
        data_classes=("private_archive",),
        purpose="answer.context",
        provider_policy=ProviderPolicy(("provider_openai",), maximum_request_count=1),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=5),
        revision=1,
    )
    registry = CapabilityRegistry((grant,))
    decision = registry.authorize_and_reserve(
        AuthorizationRequest(
            owner_ref="owner_editorial_cli",
            connection_ref="connection_editorial_cli",
            capability="model.context_egress",
            resource_ref="resource_editorial_cli",
            operation="model_egress",
            data_class="private_archive",
            provider_ref="provider_openai",
            purpose="answer.context",
            operation_ref="operation_other",
        ),
        now=now,
    )
    with pytest.raises(ValueError):
        OpenCodeEditorialAccess(decision, "owner_editorial_cli", "connection_editorial_cli", "resource_editorial_cli")


def test_synthesize_drafts_with_mocked_model(monkeypatch):
    import prm.editorial_transport as module

    monkeypatch.setenv("PRM_EDITORIAL_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    document = _document()
    ref = document.evidence[0].evidence_ref
    quote = document.evidence[0].summary[:24]
    editorial_json = {
        "stories": [
            {
                "title": "Вышел новый релиз",
                "summary": "Компания открыла модель для быстрых ответов.",
                "explanation": "Публикация затрагивает быстрые ответы в поиске.",
                "plain_explanation": "Появилась новая открытая модель.",
                "why_selected": "Это заметное событие недели.",
                "next_step": "",
                "caveat": "Выборка неполная.",
                "anchors": [{"evidence_ref": ref, "quote": quote}],
            }
        ],
        "omitted_refs": [],
    }
    monkeypatch.setattr(
        module,
        "_call_model",
        lambda **_: {"choices": [{"message": {"content": json.dumps(editorial_json, ensure_ascii=False)}}]},
    )
    editorial, measurement = synthesize_opencode_editorial(document, question="AI", access=_access())
    assert measurement["status"] == "drafted"
    assert editorial is not None and len(editorial.stories) == 1


def test_synthesize_rejects_bad_model_output(monkeypatch):
    import prm.editorial_transport as module

    monkeypatch.setenv("PRM_EDITORIAL_OPENCODE_ENABLED", "1")
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    monkeypatch.setattr(module, "_call_model", lambda **_: {"choices": [{"message": {"content": "not json"}}]})
    editorial, measurement = synthesize_opencode_editorial(_document(), question="AI", access=_access())
    assert editorial is None
    assert measurement["status"] == "editorial_rejected"
