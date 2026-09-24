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
from prm.media_connectors import (
    ExtractedText,
    MediaAnswer,
    MediaAsset,
    MediaQuestion,
    Transcription,
    build_media_asset,
    needs_ocr,
    plan_cleanup,
    require_media_egress_access,
    revise_transcription,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
OWNER = "owner_media_primary"
CONNECTION = "connection_media_primary"
RESOURCE = "resource_media_primary"


def _asset(kind="document", mime="application/pdf", content=b"%PDF-1.4 data", **changes):
    values = {"owner_ref": OWNER, "kind": kind, "mime_type": mime, "content": content, "now": NOW}
    values.update(changes)
    return build_media_asset(**values)  # type: ignore[arg-type]


def _grant(capability, purpose):
    return CapabilityGrant(
        grant_id=f"grant_{capability}",
        owner_ref=OWNER,
        connection_ref=CONNECTION,
        capability=capability,
        resource_refs=(RESOURCE,),
        operations=("model_egress",),
        data_classes=("private_connector_content",),
        purpose=purpose,
        provider_policy=ProviderPolicy(("provider_openai",), maximum_request_count=2),
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
        revision=1,
    )


def _decision(capability, purpose):
    registry = CapabilityRegistry((_grant(capability, purpose),))
    return registry.authorize_and_reserve(
        AuthorizationRequest(
            owner_ref=OWNER,
            connection_ref=CONNECTION,
            capability=capability,
            resource_ref=RESOURCE,
            operation="model_egress",
            data_class="private_connector_content",
            provider_ref="provider_openai",
            purpose=purpose,
            operation_ref=f"operation_{capability}",
        ),
        now=NOW,
    )


def test_asset_rejects_oversized_blocked_and_unsupported():
    with pytest.raises(ValueError):
        _asset(content=b"")
    with pytest.raises(ValueError):
        _asset(content=b"x" * (21 * 1024 * 1024))
    with pytest.raises(ValueError):
        _asset(kind="document", mime="application/zip", content=b"PK\x03\x04")
    with pytest.raises(ValueError):
        _asset(kind="image", mime="application/pdf", content=b"%PDF")
    asset = _asset()
    assert asset.is_expired(NOW + timedelta(hours=2)) is True


def test_transcription_is_editable_and_keeps_original():
    original = Transcription(
        transcript_ref="transcript_1", media_ref="media_voice_1", owner_ref=OWNER,
        text="привет", language="ru", provider_ref="provider_openai", version=1, created_at=NOW,
    )
    revised = revise_transcription(original, text="привет, мир", now=NOW + timedelta(minutes=1))
    assert revised.version == 2 and revised.text == "привет, мир"
    assert original.version == 1 and original.text == "привет"  # original retained


def test_ocr_only_when_text_layer_is_inadequate():
    image = _asset(kind="image", mime="image/png", content=b"\x89PNG data")
    assert needs_ocr(image, None) is True
    document = _asset()
    assert needs_ocr(document, None) is True
    adequate = ExtractedText(media_ref=document.media_ref, method="text_layer", pages=((1, "x" * 400),))
    assert needs_ocr(document, adequate) is False
    thin = ExtractedText(media_ref=document.media_ref, method="text_layer", pages=((1, "short"),))
    assert needs_ocr(document, thin) is True


def test_media_answer_carries_page_and_source_refs():
    answer = MediaAnswer(
        media_ref="media_doc_1", answer="Ключевой срок — 30 сентября.",
        page_refs=(2,), source_refs=("source_pdf_1",), extraction_method="ocr",
    )
    assert answer.page_refs == (2,)
    with pytest.raises(ValueError):
        MediaAnswer(media_ref="media_doc_1", answer="x", page_refs=(1, 1), source_refs=(), extraction_method="ocr")


def test_cleanup_plan_targets_and_question_validation():
    asset = _asset()
    plan = plan_cleanup(asset, had_transcript=True)
    assert {target for target, _ in plan.targets} == {"temp_file", "derived_text", "derived_thumbnail", "transcript"}
    question = MediaQuestion(owner_ref=OWNER, media_ref=asset.media_ref, question="Какой срок?")
    assert question.max_answer_chars == 2000


def test_media_egress_fails_closed_and_purposes_are_separate():
    with pytest.raises(CapabilityDenied):
        require_media_egress_access(
            None, purpose="media.vision", owner_ref=OWNER, connection_ref=CONNECTION, resource_ref=RESOURCE
        )
    require_media_egress_access(
        _decision("media.vision", "media.vision"),
        purpose="media.vision", owner_ref=OWNER, connection_ref=CONNECTION, resource_ref=RESOURCE,
    )
    require_media_egress_access(
        _decision("media.document", "media.document"),
        purpose="media.document", owner_ref=OWNER, connection_ref=CONNECTION, resource_ref=RESOURCE,
    )
    require_media_egress_access(
        _decision("media.transcribe", "voice.transcription"),
        purpose="voice.transcription", owner_ref=OWNER, connection_ref=CONNECTION, resource_ref=RESOURCE,
    )
    assert transport_purpose(provider_ref="provider_openai", capability="media.vision", operation="model_egress") == "media.vision"
    assert transport_purpose(provider_ref="provider_openai", capability="media.document", operation="model_egress") == "media.document"
    assert transport_purpose(provider_ref="provider_openai", capability="media.speech", operation="model_egress") == "media.speech"
