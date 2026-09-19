from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

from prm.archive_context import ArchiveEvidenceContext
from prm.archive_synthesis_transport import (
    ArchiveSynthesisReceipt,
    ArchiveSynthesisTransportResult,
    _openai_connection_ref,
    complete_archive_synthesis,
)
from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy
from prm.contracts import ArchiveSynthesisAccess
from prm.synthesis import synthesize_answer, synthesize_archive_response


def _archive_synthesis_authorization():
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    grant = CapabilityGrant(
        grant_id="grant_synthetic_archive_synthesis",
        owner_ref="owner_synthetic_primary",
        connection_ref=None,
        capability="model.generate",
        resource_refs=("resource_archive",),
        operations=("model_egress",),
        data_classes=("private_archive",),
        purpose="answer.request",
        provider_policy=ProviderPolicy(("provider_anthropic",)),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        revision=1,
    )
    request = AuthorizationRequest(
        owner_ref="owner_synthetic_primary",
        capability="model.generate",
        resource_ref="resource_archive",
        operation="model_egress",
        data_class="private_archive",
        provider_ref="provider_anthropic",
        purpose="answer.request",
        expected_grant_revision=1,
    )
    return CapabilityRegistry((grant,)).authorize_and_reserve(request, now=now)


def test_synthesis_rejects_diagnostic_fallback_markers(monkeypatch):
    calls = []

    def complete(**_kwargs):
        calls.append(_kwargs)
        return "The local research path found grounded evidence. Archive signal: raw fallback."

    monkeypatch.setenv("PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS", "1")
    monkeypatch.setenv("PRM_TELEGRAM_RAG_LLM_SYNTHESIS", "1")
    monkeypatch.setattr("prm.synthesis.LLMClient.complete", complete)

    result = synthesize_answer(
        {
            "answer_gate": {"external_verification_required": False},
            "claim_ledger": {
                "claims": [
                    {
                        "claim_text": "Есть подтверждённый локальный сигнал.",
                        "evidence_refs": ["https://t.me/example/1"],
                        "support_status": "supported",
                    }
                ]
            },
            "project_fit": {},
        },
        deterministic_fallback="Короткий вывод\nЕсть подтверждённый локальный сигнал.",
        mode="research",
        evidence_items=[
            {
                "evidence_id": "e1",
                "support_span": "Есть подтверждённый локальный сигнал.",
                "source_url": "https://t.me/example/1",
            }
        ],
        authorization=_archive_synthesis_authorization(),
    )

    assert result is None
    assert calls == []


def _archive_payload():
    return {
        "archive_contract": {
            "result_summary": {"direct_count": 1, "partial_count": 0, "adjacent_count": 0},
            "direct_findings": [{
                "evidence_id": "tg:synthetic-1",
                "title": "Agent evals",
                "summary": "Agent evals use task success and groundedness.",
                "source_url": "https://t.me/example/1",
                "relevance_label": "direct",
            }],
            "partial_findings": [],
            "adjacent_findings": [],
        },
    }


def _archive_evidence():
    return [{
        "evidence_id": "tg:synthetic-1",
        "source_url": "https://t.me/example/1",
        "support_span": "Agent evals use task success and groundedness.",
        "local_archive_provenance": True,
    }]


def _archive_access():
    now = datetime.now(timezone.utc)
    connection_ref = _openai_connection_ref("synthetic-pa04-key")
    assert connection_ref is not None
    text = CapabilityGrant(
        grant_id="grant_synthetic_pa04_text",
        owner_ref="owner_synthetic_primary",
        connection_ref=connection_ref,
        capability="model.generate",
        resource_refs=("resource_conversation",),
        operations=("model_egress",),
        data_classes=("user_provided",),
        purpose="answer.request",
        provider_policy=ProviderPolicy(("provider_openai",), maximum_request_count=2),
        issued_at=now - timedelta(minutes=1), expires_at=now + timedelta(minutes=5), revision=1,
    )
    context = CapabilityGrant(
        grant_id="grant_synthetic_pa04_context",
        owner_ref="owner_synthetic_primary",
        connection_ref=connection_ref,
        capability="model.context_egress",
        resource_refs=("resource_archive",),
        operations=("model_egress",),
        data_classes=("private_archive",),
        purpose="answer.context",
        provider_policy=ProviderPolicy(("provider_openai",), maximum_request_count=2),
        issued_at=now - timedelta(minutes=1), expires_at=now + timedelta(minutes=5), revision=1,
    )
    registry = CapabilityRegistry((text, context))
    operation_ref = "operation_synthetic_pa04_archive"
    query = registry.authorize_and_reserve(AuthorizationRequest(
        owner_ref=text.owner_ref, connection_ref=connection_ref, capability="model.generate",
        resource_ref="resource_conversation", operation="model_egress", data_class="user_provided",
        provider_ref="provider_openai", purpose="answer.request", expected_grant_revision=1,
        operation_ref=operation_ref,
    ))
    archive = registry.authorize_and_reserve(AuthorizationRequest(
        owner_ref=text.owner_ref, connection_ref=connection_ref, capability="model.context_egress",
        resource_ref="resource_archive", operation="model_egress", data_class="private_archive",
        provider_ref="provider_openai", purpose="answer.context", expected_grant_revision=1,
        operation_ref=operation_ref,
    ))
    return ArchiveSynthesisAccess(
        query_authorization=query, context_authorization=archive, owner_ref=text.owner_ref,
        connection_ref=connection_ref, query_resource_ref="resource_conversation", context_resource_ref="resource_archive",
    )


def test_pa04_transport_sends_only_immutable_source_bound_context(monkeypatch):
    context = ArchiveEvidenceContext.from_payload(
        question="What does my archive say about agent evals?",
        archive_contract=_archive_payload()["archive_contract"], evidence_items=_archive_evidence(),
    )
    assert context is not None
    access = _archive_access()
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_text="Agent evals use task success and groundedness (https://t.me/example/1).")

    monkeypatch.setenv("PRM_OPENAI_PROVIDER_ENABLED", "true")
    monkeypatch.setenv("PRM_OPENAI_CONTEXT_EGRESS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-pa04-key")
    monkeypatch.setattr("prm.archive_synthesis_transport._build_client", lambda _key: SimpleNamespace(responses=SimpleNamespace(create=create)))

    result = complete_archive_synthesis(context=context, access=access)

    assert result.receipt.context_egress_performed is True
    assert len(calls) == 1
    assert "Agent evals use task success and groundedness." in repr(calls[0]["input"])
    assert "https://t.me/example/1" in repr(calls[0]["input"])


def test_pa04_empty_provider_response_keeps_accepted_egress_measurement(monkeypatch):
    monkeypatch.setenv("PRM_OPENAI_PROVIDER_ENABLED", "true")
    monkeypatch.setenv("PRM_OPENAI_CONTEXT_EGRESS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-pa04-key")
    monkeypatch.setattr(
        "prm.archive_synthesis_transport._build_client",
        lambda _key: SimpleNamespace(responses=SimpleNamespace(create=lambda **_kwargs: SimpleNamespace(output_text=""))),
    )

    outcome = synthesize_archive_response(
        _archive_payload(), question="What does my archive say about agent evals?", evidence_items=_archive_evidence(), access=_archive_access(),
    )

    assert outcome.status == "provider_empty_response"
    assert outcome.measurement["external_call_attempted"] is True
    assert outcome.measurement["context_egress_performed"] is True


def test_pa04_synthesis_rejects_wrong_citation_and_false_refusal(monkeypatch):
    receipt = ArchiveSynthesisReceipt(
        provider="openai", model="gpt-5.6-terra", external_call_attempted=True, external_call_performed=True,
        context_egress_attempted=True, context_egress_performed=True, delivery_outcome="accepted", context_binding_digest="synthetic",
    )
    monkeypatch.setattr(
        "prm.synthesis.complete_archive_synthesis",
        lambda **_kwargs: ArchiveSynthesisTransportResult(
            text="Agent evals destroy task success and groundedness (https://t.me/example/1).", receipt=receipt,
        ),
    )

    outcome = synthesize_archive_response(
        _archive_payload(), question="Что в архиве есть про agent evals?", evidence_items=_archive_evidence(), access=_archive_access(),
    )

    assert outcome.text is None
    assert outcome.status == "generated_answer_rejected"
    assert outcome.measurement["context_egress_performed"] is True


def test_pa04_synthesis_accepts_bounded_useful_paraphrase(monkeypatch):
    receipt = ArchiveSynthesisReceipt(
        provider="openai", model="gpt-5.6-terra", external_call_attempted=True, external_call_performed=True,
        context_egress_attempted=True, context_egress_performed=True, delivery_outcome="accepted", context_binding_digest="synthetic",
    )
    monkeypatch.setattr(
        "prm.synthesis.complete_archive_synthesis",
        lambda **_kwargs: ArchiveSynthesisTransportResult(
            text="Archive materials describe using task success and groundedness for agent evals (https://t.me/example/1).", receipt=receipt,
        ),
    )

    outcome = synthesize_archive_response(
        _archive_payload(), question="What does my archive say about agent evals?", evidence_items=_archive_evidence(), access=_archive_access(),
    )

    assert outcome.status == "generated_verified"
    assert outcome.text is not None and outcome.text.startswith("Archive materials describe")


def test_pa04_synthesis_accepts_cited_answer_and_reports_measurement(monkeypatch):
    receipt = ArchiveSynthesisReceipt(
        provider="openai", model="gpt-5.6-terra", external_call_attempted=True, external_call_performed=True,
        context_egress_attempted=True, context_egress_performed=True, delivery_outcome="accepted", context_binding_digest="synthetic",
    )
    monkeypatch.setattr(
        "prm.synthesis.complete_archive_synthesis",
        lambda **_kwargs: ArchiveSynthesisTransportResult(
            text="Agent evals use task success and groundedness (https://t.me/example/1).", receipt=receipt,
        ),
    )

    outcome = synthesize_archive_response(
        _archive_payload(), question="What does my archive say about agent evals?", evidence_items=_archive_evidence(), access=_archive_access(),
    )

    assert outcome.status == "generated_verified"
    assert outcome.text == "Agent evals use task success and groundedness (https://t.me/example/1)."
    assert outcome.measurement["selected_source_count"] == 1


def test_pa04_synthesis_accepts_russian_cited_answer(monkeypatch):
    payload = _archive_payload()
    payload["archive_contract"]["direct_findings"][0].update({
        "summary": "В архиве есть практика: измерять task success и groundedness.",
        "source_url": "https://t.me/example/ru-1",
    })
    evidence = [{
        "evidence_id": "tg:synthetic-1",
        "source_url": "https://t.me/example/ru-1",
        "support_span": "В архиве есть практика: измерять task success и groundedness.",
        "local_archive_provenance": True,
    }]
    receipt = ArchiveSynthesisReceipt(
        provider="openai", model="gpt-5.6-terra", external_call_attempted=True, external_call_performed=True,
        context_egress_attempted=True, context_egress_performed=True, delivery_outcome="accepted", context_binding_digest="synthetic",
    )
    monkeypatch.setattr(
        "prm.synthesis.complete_archive_synthesis",
        lambda **_kwargs: ArchiveSynthesisTransportResult(
            text="В архиве есть практика: измерять task success и groundedness (https://t.me/example/ru-1).", receipt=receipt,
        ),
    )

    outcome = synthesize_archive_response(
        payload, question="Что в моём архиве есть про agent evals?", evidence_items=evidence, access=_archive_access(),
    )

    assert outcome.status == "generated_verified"
    assert outcome.text is not None and "https://t.me/example/ru-1" in outcome.text


def test_pa04_unbound_source_context_cannot_reach_transport(monkeypatch):
    calls = []
    monkeypatch.setattr("prm.synthesis.complete_archive_synthesis", lambda **kwargs: calls.append(kwargs))
    access = _archive_access()

    outcome = synthesize_archive_response(
        _archive_payload(),
        question="What does my archive say about agent evals?",
        evidence_items=[{
            "evidence_id": "tg:synthetic-1",
            "source_url": "https://t.me/example/other",
            "support_span": "Agent evals use task success and groundedness.",
        }],
        access=access,
    )

    assert outcome.status == "context_unavailable"
    assert calls == []
    assert access.query_authorization.reservation is not None and access.query_authorization.reservation.current is False
    assert access.context_authorization.reservation is not None and access.context_authorization.reservation.current is False


def test_pa04_context_uses_exact_selected_span_and_rejects_identity_or_provenance_mutations():
    payload = _archive_payload()
    payload["archive_contract"]["direct_findings"][0]["summary"] += " private-appended-sentinel"
    context = ArchiveEvidenceContext.from_payload(
        question="What does my archive say about agent evals?",
        archive_contract=payload["archive_contract"], evidence_items=_archive_evidence(),
    )

    assert context is not None
    assert context.items[0].text == "Agent evals use task success and groundedness."
    assert "private-appended-sentinel" not in repr(context.to_transport_context())

    wrong_identity = [{**_archive_evidence()[0], "evidence_id": "tg:other"}]
    no_provenance = [{**_archive_evidence()[0], "local_archive_provenance": False}]
    assert ArchiveEvidenceContext.from_payload(
        question="What does my archive say about agent evals?", archive_contract=payload["archive_contract"], evidence_items=wrong_identity,
    ) is None
    assert ArchiveEvidenceContext.from_payload(
        question="What does my archive say about agent evals?", archive_contract=payload["archive_contract"], evidence_items=no_provenance,
    ) is None


def test_pa04_context_accepts_normal_truncated_display_summary_from_canonical_span():
    support = "x" * 259 + "z"
    payload = _archive_payload()
    payload["archive_contract"]["direct_findings"][0]["summary"] = "x" * 259 + "…"
    evidence = [{
        "evidence_id": "tg:synthetic-1", "source_url": "https://t.me/example/1", "support_span": support,
        "local_archive_provenance": True,
    }]

    context = ArchiveEvidenceContext.from_payload(
        question="What does my archive say about agent evals?", archive_contract=payload["archive_contract"], evidence_items=evidence,
    )

    assert context is not None
    assert context.items[0].text == support
