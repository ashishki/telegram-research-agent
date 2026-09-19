import os
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from datetime import datetime, timedelta, timezone
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
from unittest.mock import patch


def _install_stub(module_name: str, **attributes: object) -> None:
    if module_name in sys.modules:
        return
    module = types.ModuleType(module_name)
    for name, value in attributes.items():
        setattr(module, name, value)
    sys.modules[module_name] = module


class _APIStatusError(Exception):
    def __init__(self, status_code: int = 500):
        super().__init__("status error")
        self.status_code = status_code


_install_stub(
    "anthropic",
    APIConnectionError=Exception,
    APIStatusError=_APIStatusError,
    APITimeoutError=Exception,
    Anthropic=object,
    RateLimitError=Exception,
)

import llm.client as client  # noqa: E402
import llm.vision as vision  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy  # noqa: E402


SYNTHETIC_ANTHROPIC_KEY = "synthetic-anthropic-key"
SYNTHETIC_ANTHROPIC_CONNECTION = client._anthropic_connection_ref(SYNTHETIC_ANTHROPIC_KEY)
assert SYNTHETIC_ANTHROPIC_CONNECTION is not None

AUTH_SCOPE = {
    "owner_ref": "owner_synthetic_primary",
    "connection_ref": SYNTHETIC_ANTHROPIC_CONNECTION,
    "resource_ref": "resource_conversation",
}


def _authorization(
    *,
    capability: str = "model.generate",
    purpose: str = "answer.request",
    operation_ref: str | None = "operation_synthetic_anthropic_001",
):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    grant = CapabilityGrant(
        grant_id=f"grant_synthetic_{capability.replace('.', '_')}",
        owner_ref="owner_synthetic_primary",
        connection_ref=SYNTHETIC_ANTHROPIC_CONNECTION,
        capability=capability,
        resource_refs=("resource_conversation",),
        operations=("model_egress",),
        data_classes=("user_provided",),
        purpose=purpose,
        provider_policy=ProviderPolicy(("provider_anthropic",)),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        revision=1,
    )
    request = AuthorizationRequest(
        owner_ref="owner_synthetic_primary",
        capability=capability,
        resource_ref="resource_conversation",
        operation="model_egress",
        data_class="user_provided",
        provider_ref="provider_anthropic",
        purpose=purpose,
        connection_ref=SYNTHETIC_ANTHROPIC_CONNECTION,
        expected_grant_revision=1,
        operation_ref=operation_ref,
    )
    return CapabilityRegistry((grant,)).authorize_and_reserve(request, now=now)


class TestLLMClient(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        self.credential_env = patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": SYNTHETIC_ANTHROPIC_KEY},
            clear=False,
        )
        self.credential_env.start()
        client.set_usage_db_path("")
        with patch.dict(os.environ, {"AGENT_DB_PATH": self.db_path}):
            run_migrations()
        self.text_authorization = _authorization()
        self.vision_authorization = _authorization(capability="model.vision")

    def tearDown(self) -> None:
        self.credential_env.stop()
        client.set_usage_db_path("")
        os.unlink(self.db_path)

    def test_get_client_disables_sdk_retries_for_a_granted_transport(self):
        constructed = object()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "synthetic-key"}, clear=True):
            with patch.object(client, "Anthropic", return_value=constructed) as anthropic:
                assert client._get_client() is constructed

        anthropic.assert_called_once_with(api_key="synthetic-key", max_retries=0)

    def test_text_transport_rejects_a_reservation_for_another_purpose_before_provider_call(self):
        fake_transport = unittest.mock.Mock()
        fake_client = SimpleNamespace(messages=SimpleNamespace(create=fake_transport))

        with patch.object(client, "_get_client", return_value=fake_client):
            with self.assertRaises(client.LLMError):
                client.complete(
                    prompt="Synthetic question",
                    authorization=_authorization(purpose="answer.context"),
                    **AUTH_SCOPE,
                )

        fake_transport.assert_not_called()

    def test_text_transport_rejects_a_grant_for_another_active_credential_before_provider_call(self):
        granted_key = "synthetic-anthropic-grant-a"
        active_key = "synthetic-anthropic-credential-b"
        granted_connection_ref = client._anthropic_connection_ref(granted_key)
        assert granted_connection_ref is not None
        now = datetime.now(timezone.utc).replace(microsecond=0)
        grant = CapabilityGrant(
            grant_id="grant_synthetic_anthropic_connection_a",
            owner_ref="owner_synthetic_primary",
            connection_ref=granted_connection_ref,
            capability="model.generate",
            resource_refs=("resource_conversation",),
            operations=("model_egress",),
            data_classes=("user_provided",),
            purpose="answer.request",
            provider_policy=ProviderPolicy(("provider_anthropic",)),
            issued_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=1),
            revision=1,
        )
        decision = CapabilityRegistry((grant,)).authorize_and_reserve(
            AuthorizationRequest(
                owner_ref="owner_synthetic_primary",
                connection_ref=granted_connection_ref,
                capability="model.generate",
                resource_ref="resource_conversation",
                operation="model_egress",
                data_class="user_provided",
                provider_ref="provider_anthropic",
                purpose="answer.request",
                expected_grant_revision=1,
            ),
            now=now,
        )
        fake_transport = unittest.mock.Mock()
        fake_client = SimpleNamespace(messages=SimpleNamespace(create=fake_transport))

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": active_key}, clear=False), patch.object(
            client, "_get_client", return_value=fake_client
        ):
            with self.assertRaises(client.LLMError):
                client.complete(
                    prompt="Synthetic question",
                    authorization=decision,
                    owner_ref="owner_synthetic_primary",
                    connection_ref=granted_connection_ref,
                    resource_ref="resource_conversation",
                )

        fake_transport.assert_not_called()

    def test_text_transport_rejects_a_null_connection_ref_before_provider_call(self):
        fake_transport = unittest.mock.Mock()
        fake_client = SimpleNamespace(messages=SimpleNamespace(create=fake_transport))

        with patch.object(client, "_get_client", return_value=fake_client):
            with self.assertRaises(client.LLMError):
                client.complete(
                    prompt="Synthetic question",
                    authorization=self.text_authorization,
                    owner_ref="owner_synthetic_primary",
                    connection_ref=None,
                    resource_ref="resource_conversation",
                )

        fake_transport.assert_not_called()

    def test_revoked_or_revision_stale_text_reservation_cannot_write_usage(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        for change in ("revoke", "revision"):
            with self.subTest(change=change):
                grant = CapabilityGrant(
                    grant_id=f"grant_synthetic_usage_{change}",
                    owner_ref="owner_synthetic_primary",
                    connection_ref=SYNTHETIC_ANTHROPIC_CONNECTION,
                    capability="model.generate",
                    resource_refs=("resource_conversation",),
                    operations=("model_egress",),
                    data_classes=("user_provided",),
                    purpose="answer.request",
                    provider_policy=ProviderPolicy(("provider_anthropic",)),
                    issued_at=now - timedelta(minutes=1),
                    expires_at=now + timedelta(hours=1),
                    revision=1,
                )
                registry = CapabilityRegistry((grant,))
                decision = registry.authorize_and_reserve(
                    AuthorizationRequest(
                        owner_ref="owner_synthetic_primary",
                        connection_ref=SYNTHETIC_ANTHROPIC_CONNECTION,
                        capability="model.generate",
                        resource_ref="resource_conversation",
                        operation="model_egress",
                        data_class="user_provided",
                        provider_ref="provider_anthropic",
                        purpose="answer.request",
                        expected_grant_revision=1,
                    ),
                    now=now,
                )
                if change == "revoke":
                    registry.revoke_grant(grant.grant_id)
                else:
                    registry.replace_grant(replace(grant, revision=2))
                fake_transport = unittest.mock.Mock()
                fake_client = SimpleNamespace(messages=SimpleNamespace(create=fake_transport))
                with patch.object(client, "_get_client", return_value=fake_client):
                    with self.assertRaises(client.LLMError):
                        client.complete(
                            prompt="Synthetic question",
                            authorization=decision,
                            **AUTH_SCOPE,
                        )
                fake_transport.assert_not_called()
                with sqlite3.connect(self.db_path) as connection:
                    count = connection.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0]
                self.assertEqual(count, 0)

    def test_complete_does_not_persist_llm_usage_without_a_local_write_grant(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hello world")],
            usage=SimpleNamespace(input_tokens=123, output_tokens=45),
        )
        mock_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: response))

        with patch.dict(os.environ, {"AGENT_DB_PATH": self.db_path}, clear=False):
            with patch.object(client, "_get_client", return_value=mock_client):
                result = client.complete(
                    prompt="hi", category="test", model="claude-haiku-4-5",
                    authorization=self.text_authorization, **AUTH_SCOPE,
                )

        self.assertEqual(result, "hello world")
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT model, task_type, input_tokens, output_tokens
                FROM llm_usage
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        self.assertIsNone(row)

    def test_complete_with_receipt_returns_immutable_usage_metadata(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="receipt text")],
            usage=SimpleNamespace(input_tokens=125, output_tokens=25),
        )
        mock_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: response))

        with patch.dict(os.environ, {"AGENT_DB_PATH": self.db_path}, clear=False):
            with patch.object(client, "_get_client", return_value=mock_client):
                receipt = client.LLMClient.complete_with_receipt(
                    prompt="hi",
                    category="test",
                    model="claude-haiku-4-5",
                    authorization=self.text_authorization,
                    **AUTH_SCOPE,
                )

        self.assertEqual(receipt.text, "receipt text")
        self.assertEqual(receipt.model, "claude-haiku-4-5")
        self.assertEqual(receipt.input_tokens, 125)
        self.assertEqual(receipt.output_tokens, 25)
        self.assertAlmostEqual(receipt.estimated_cost_usd, 0.0002)
        self.assertGreaterEqual(receipt.duration_ms, 0)
        self.assertEqual(receipt.attempts, 1)
        self.assertFalse(receipt.usage_recorded)
        with self.assertRaises(FrozenInstanceError):
            receipt.text = "changed"

    def test_complete_with_receipt_does_not_retry_an_unknown_provider_outcome(self):
        calls = 0

        def create(**_kwargs):
            nonlocal calls
            calls += 1
            raise RuntimeError("temporary failure")

        mock_client = SimpleNamespace(messages=SimpleNamespace(create=create))
        with patch.dict(os.environ, {"AGENT_DB_PATH": self.db_path}, clear=False):
            with patch.object(client, "_get_client", return_value=mock_client):
                with self.assertRaises(client.LLMError):
                    client.complete_with_receipt(
                        prompt="retry",
                        category="test",
                        model="claude-haiku-4-5",
                        max_attempts=3,
                        authorization=self.text_authorization,
                        **AUTH_SCOPE,
                    )

        self.assertEqual(calls, 1)

    def test_unknown_anthropic_outcome_blocks_same_operation_until_reconciliation(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        operation_ref = "operation_synthetic_anthropic_unknown_001"
        grant = CapabilityGrant(
            grant_id="grant_synthetic_anthropic_unknown",
            owner_ref="owner_synthetic_primary",
            connection_ref=SYNTHETIC_ANTHROPIC_CONNECTION,
            capability="model.generate",
            resource_refs=("resource_conversation",),
            operations=("model_egress",),
            data_classes=("user_provided",),
            purpose="answer.request",
            provider_policy=ProviderPolicy(("provider_anthropic",), maximum_request_count=2),
            issued_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=1),
            revision=1,
        )
        request = AuthorizationRequest(
            owner_ref="owner_synthetic_primary",
            connection_ref=SYNTHETIC_ANTHROPIC_CONNECTION,
            capability="model.generate",
            resource_ref="resource_conversation",
            operation="model_egress",
            data_class="user_provided",
            provider_ref="provider_anthropic",
            purpose="answer.request",
            expected_grant_revision=1,
            operation_ref=operation_ref,
        )
        registry = CapabilityRegistry((grant,))
        calls = 0

        def create(**_kwargs):
            nonlocal calls
            calls += 1
            raise TimeoutError("synthetic unknown provider outcome")

        fake_client = SimpleNamespace(messages=SimpleNamespace(create=create))
        with patch.object(client, "_get_client", return_value=fake_client):
            with self.assertRaises(client.LLMOutcomeUnknown) as error:
                client.complete_with_receipt(
                    prompt="retry sentinel",
                    authorization=registry.authorize_and_reserve(request),
                    **AUTH_SCOPE,
                )

        self.assertTrue(error.exception.receipt.external_call_attempted)
        self.assertEqual(error.exception.receipt.delivery_outcome, "unknown")
        self.assertEqual(calls, 1)
        self.assertEqual(
            registry.authorize_and_reserve(request).reason,
            "operation_outcome_unknown",
        )
        self.assertTrue(registry.reconcile_unknown_operation(operation_ref, delivery_outcome="not_delivered"))
        self.assertTrue(registry.authorize_and_reserve(request).allowed)

    def test_anthropic_transport_requires_a_sealed_operation_ref_before_fake_call(self):
        fake_transport = unittest.mock.Mock()
        fake_client = SimpleNamespace(messages=SimpleNamespace(create=fake_transport))

        with patch.object(client, "_get_client", return_value=fake_client):
            with self.assertRaises(client.LLMError):
                client.complete(
                    prompt="missing operation ref",
                    authorization=_authorization(operation_ref=None),
                    **AUTH_SCOPE,
                )

        fake_transport.assert_not_called()

    def test_text_completion_redacts_provider_exception_from_logs_and_error_chain(self):
        mock_client = SimpleNamespace(
            messages=SimpleNamespace(
                create=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("provider-payload-sentinel"))
            )
        )
        with patch.object(client, "_get_client", return_value=mock_client):
            with self.assertLogs(client.LOGGER, level="WARNING") as logs:
                with self.assertRaises(client.LLMError) as error:
                    client.complete(
                        prompt="private-prompt-sentinel",
                        category="test",
                        authorization=self.text_authorization,
                        **AUTH_SCOPE,
                    )

        assert "provider-payload-sentinel" not in str(error.exception)
        assert error.exception.__cause__ is None
        rendered = "\n".join(logs.output)
        assert "provider-payload-sentinel" not in rendered
        assert "private-prompt-sentinel" not in rendered

    def test_complete_with_receipt_honors_single_attempt_budget(self):
        calls = 0

        def create(**_kwargs):
            nonlocal calls
            calls += 1
            raise RuntimeError("temporary failure")

        mock_client = SimpleNamespace(messages=SimpleNamespace(create=create))
        with (
            patch.object(client, "_get_client", return_value=mock_client),
            patch.object(client.time, "sleep") as sleep_mock,
        ):
            with self.assertRaises(client.LLMError):
                client.complete_with_receipt(
                    prompt="bounded",
                    category="test",
                    model="claude-haiku-4-5",
                    max_attempts=1,
                    authorization=self.text_authorization,
                    **AUTH_SCOPE,
                )

        self.assertEqual(calls, 1)
        sleep_mock.assert_not_called()

    def test_complete_with_receipt_records_provider_reported_model(self):
        response = SimpleNamespace(
            model="provider-resolved-model",
            content=[SimpleNamespace(type="text", text="resolved")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )
        mock_client = SimpleNamespace(
            messages=SimpleNamespace(create=lambda **_: response)
        )

        with patch.object(client, "_get_client", return_value=mock_client):
            receipt = client.complete_with_receipt(
                prompt="audit actual model",
                category="test",
                model="requested-model",
                authorization=self.text_authorization,
                **AUTH_SCOPE,
            )

        self.assertEqual(receipt.model, "provider-resolved-model")

    def test_complete_preserves_string_result_via_receipt_api(self):
        receipt = client.LLMCompletionReceipt(
            text="exact string",
            model="claude-haiku-4-5",
            input_tokens=1,
            output_tokens=2,
            estimated_cost_usd=0.0,
            duration_ms=3,
            attempts=1,
            usage_recorded=False,
        )
        with patch.object(
            client, "complete_with_receipt", return_value=receipt
        ) as complete_receipt:
            result = client.complete(
                prompt="hello",
                system="system",
                max_tokens=99,
                category="test",
                model="claude-haiku-4-5",
                authorization=self.text_authorization,
                **AUTH_SCOPE,
            )

        self.assertEqual(result, "exact string")
        complete_receipt.assert_called_once_with(
            prompt="hello",
            system="system",
            max_tokens=99,
            category="test",
            model="claude-haiku-4-5",
            authorization=self.text_authorization,
            data_class="user_provided",
            **AUTH_SCOPE,
        )

    def test_complete_does_not_persist_llm_usage_with_an_explicit_usage_db_path(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hello world")],
            usage=SimpleNamespace(input_tokens=123, output_tokens=45),
        )
        mock_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: response))
        client.set_usage_db_path(self.db_path)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": SYNTHETIC_ANTHROPIC_KEY}, clear=True):
            with patch.object(client, "_get_client", return_value=mock_client):
                result = client.complete(
                    prompt="hi",
                    category="test",
                    model="claude-haiku-4-5",
                    authorization=self.text_authorization,
                    **AUTH_SCOPE,
                )

        self.assertEqual(result, "hello world")
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT model, task_type, input_tokens, output_tokens
                FROM llm_usage
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        self.assertIsNone(row)

    def test_complete_never_touches_a_locked_usage_database_without_a_local_write_grant(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hello world")],
            usage=SimpleNamespace(input_tokens=123, output_tokens=45),
        )
        mock_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: response))
        locker = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        locker.execute("BEGIN IMMEDIATE")

        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": self.db_path}, clear=False):
                with patch.object(client, "_get_client", return_value=mock_client):
                    started_at = time.monotonic()
                    result = client.complete(
                        prompt="hi",
                        category="test",
                        model="claude-haiku-4-5",
                        authorization=self.text_authorization,
                        **AUTH_SCOPE,
                    )
                    elapsed = time.monotonic() - started_at
        finally:
            locker.rollback()
            locker.close()

        self.assertEqual(result, "hello world")
        self.assertLess(elapsed, 0.5)
        with sqlite3.connect(self.db_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0]
        self.assertEqual(count, 0)

    def test_complete_vision_rejects_direct_local_path_before_read_or_provider_egress(self):
        mock_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: self.fail("provider must not run")))
        with tempfile.NamedTemporaryFile(prefix="private-image-path-sentinel-", suffix=".jpg") as image_file:
            image_file.write(b"synthetic image bytes")
            image_file.flush()
            with patch.object(client, "_get_client", return_value=mock_client):
                with patch("builtins.open") as open_file:
                    with self.assertRaisesRegex(client.LLMError, "ingress-verified attachment"):
                        client.complete_vision(
                            prompt="synthetic vision prompt",
                            image_path=image_file.name,
                            authorization=self.vision_authorization,
                            **AUTH_SCOPE,
                        )

        open_file.assert_not_called()

    def test_analyze_photo_denies_unbound_bytes_before_tempfile_or_provider_egress(self):
        with patch("tempfile.NamedTemporaryFile") as temp_file:
            with patch("llm.client.LLMClient.complete_vision") as complete_vision:
                assert vision.analyze_photo(b"private-image-bytes", "image/png") is None

        temp_file.assert_not_called()
        complete_vision.assert_not_called()

    def test_feedback_intake_strategist_model_route_and_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(client._get_model("feedback_intake_strategist"), "claude-opus-4-8")

        with patch.dict(
            os.environ,
            {"LLM_MODEL_FEEDBACK_INTAKE_STRATEGIST": "claude-opus-test"},
            clear=True,
        ):
            self.assertEqual(client._get_model("feedback_intake_strategist"), "claude-opus-test")


if __name__ == "__main__":
    unittest.main()
