from __future__ import annotations

from types import SimpleNamespace

import pytest

from llm.openai_provider import CONTEXT_EGRESS_ENABLE_ENV, OPENAI_TERRA_MODEL, PROVIDER_ENABLE_ENV, ProviderEgressDenied, complete_with_provider


class _FakeResponses:
    def __init__(self): self.calls = []
    def create(self, **kwargs): self.calls.append(kwargs); return SimpleNamespace(output_text="provider answer")
class _FakeClient:
    def __init__(self): self.responses = _FakeResponses()


def test_local_search_is_default_and_performs_no_provider_call() -> None:
    client = _FakeClient(); result = complete_with_provider("Find archive notes", local_context=[{"title":"private","text":"context"}], client=client)
    assert result.status == "local_required" and not result.receipt.external_call_performed
    assert client.responses.calls == []


def test_provider_call_requires_environment_and_per_call_gate(monkeypatch) -> None:
    monkeypatch.delenv(PROVIDER_ENABLE_ENV, raising=False)
    with pytest.raises(ProviderEgressDenied): complete_with_provider("Use provider", provider="openai", allow_provider_egress=True, client=_FakeClient())
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    with pytest.raises(ProviderEgressDenied): complete_with_provider("Use provider", provider="openai", allow_provider_egress=False, client=_FakeClient())


def test_context_egress_requires_second_explicit_gate(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true"); monkeypatch.delenv(CONTEXT_EGRESS_ENABLE_ENV, raising=False); client = _FakeClient()
    result = complete_with_provider("Question", provider="openai", allow_provider_egress=True, allow_context_egress=True, local_context=[{"title":"private title","text":"private context"}], client=client)
    request = client.responses.calls[0]
    assert request["model"] == OPENAI_TERRA_MODEL and "private context" not in repr(request["input"])
    assert result.receipt.context_egress_performed is False
    monkeypatch.setenv(CONTEXT_EGRESS_ENABLE_ENV, "true"); client2 = _FakeClient()
    result2 = complete_with_provider("Question", provider="openai", allow_provider_egress=True, allow_context_egress=True, local_context=[{"title":"approved","summary":"approved context"}], client=client2)
    assert "approved context" in repr(client2.responses.calls[0]["input"])
    assert result2.receipt.context_egress_performed is True
