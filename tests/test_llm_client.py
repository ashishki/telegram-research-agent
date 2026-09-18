import os
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from datetime import datetime, timedelta, timezone
from dataclasses import FrozenInstanceError
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
from db.migrate import run_migrations  # noqa: E402
from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy  # noqa: E402


AUTH_SCOPE = {
    "owner_ref": "owner_synthetic_primary",
    "connection_ref": None,
    "resource_ref": "resource_conversation",
}


def _authorization(*, capability: str = "model.generate"):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    grant = CapabilityGrant(
        grant_id=f"grant_synthetic_{capability.replace('.', '_')}",
        owner_ref="owner_synthetic_primary",
        connection_ref=None,
        capability=capability,
        resource_refs=("resource_conversation",),
        operations=("model_egress",),
        data_classes=("user_provided",),
        purpose="answer.request",
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
        purpose="answer.request",
        expected_grant_revision=1,
    )
    return CapabilityRegistry((grant,)).authorize_and_reserve(request, now=now)


class TestLLMClient(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        client.set_usage_db_path("")
        with patch.dict(os.environ, {"AGENT_DB_PATH": self.db_path}):
            run_migrations()
        self.text_authorization = _authorization()
        self.vision_authorization = _authorization(capability="model.vision")

    def tearDown(self) -> None:
        client.set_usage_db_path("")
        os.unlink(self.db_path)

    def test_get_client_disables_sdk_retries_for_a_granted_transport(self):
        constructed = object()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "synthetic-key"}, clear=True):
            with patch.object(client, "Anthropic", return_value=constructed) as anthropic:
                assert client._get_client() is constructed

        anthropic.assert_called_once_with(api_key="synthetic-key", max_retries=0)

    def test_complete_records_llm_usage_row(self):
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

        self.assertEqual(row[0], "claude-haiku-4-5")
        self.assertEqual(row[1], "test")
        self.assertEqual(row[2], 123)
        self.assertEqual(row[3], 45)

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
        self.assertTrue(receipt.usage_recorded)
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

    def test_complete_records_llm_usage_row_with_set_usage_db_path(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hello world")],
            usage=SimpleNamespace(input_tokens=123, output_tokens=45),
        )
        mock_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: response))
        client.set_usage_db_path(self.db_path)

        with patch.dict(os.environ, {}, clear=True):
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

        self.assertEqual(row[0], "claude-haiku-4-5")
        self.assertEqual(row[1], "test")
        self.assertEqual(row[2], 123)
        self.assertEqual(row[3], 45)

    def test_complete_skips_usage_recording_when_database_is_locked(self):
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

    def test_complete_vision_returns_text(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="diagram with service boundaries")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=7),
        )
        mock_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: response))
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as image_file:
            image_file.write(b"fake image bytes")
            image_path = image_file.name

        try:
            with patch.object(client, "_get_client", return_value=mock_client):
                result = client.complete_vision(
                    prompt="analyze",
                    image_path=image_path,
                    model="claude-haiku-4-5",
                    authorization=self.vision_authorization,
                    **AUTH_SCOPE,
                )
        finally:
            os.unlink(image_path)

        self.assertEqual(result, "diagram with service boundaries")

    def test_complete_vision_logs_no_private_image_path_or_provider_exception(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="safe vision result")],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )
        mock_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_kwargs: response))
        with tempfile.NamedTemporaryFile(prefix="private-image-path-sentinel-", suffix=".jpg") as image_file:
            image_file.write(b"synthetic image bytes")
            image_file.flush()
            with patch.object(client, "_get_client", return_value=mock_client):
                with self.assertLogs(client.LOGGER, level="DEBUG") as logs:
                    assert client.complete_vision(
                        prompt="synthetic vision prompt",
                        image_path=image_file.name,
                        authorization=self.vision_authorization,
                        **AUTH_SCOPE,
                    ) == "safe vision result"

        assert "private-image-path-sentinel" not in "\n".join(logs.output)

    def test_complete_vision_redacts_provider_exception(self):
        mock_client = SimpleNamespace(
            messages=SimpleNamespace(
                create=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("provider-payload-sentinel"))
            )
        )
        with tempfile.NamedTemporaryFile(prefix="private-image-path-sentinel-", suffix=".jpg") as image_file:
            image_file.write(b"synthetic image bytes")
            image_file.flush()
            with patch.object(client, "_get_client", return_value=mock_client):
                with self.assertLogs(client.LOGGER, level="WARNING") as logs:
                    with self.assertRaises(client.LLMError) as error:
                        client.complete_vision(
                            prompt="synthetic vision prompt",
                            image_path=image_file.name,
                            authorization=self.vision_authorization,
                            **AUTH_SCOPE,
                        )

        assert "provider-payload-sentinel" not in str(error.exception)
        assert "provider-payload-sentinel" not in "\n".join(logs.output)
        assert "private-image-path-sentinel" not in "\n".join(logs.output)

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
