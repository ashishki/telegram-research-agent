from prm.synthesis import synthesize_answer
from datetime import datetime, timedelta, timezone

from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy


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
