import os
import sqlite3
import sys
import tempfile
import time
import types
import unittest
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


class TestLLMClient(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        client.set_usage_db_path("")
        with patch.dict(os.environ, {"AGENT_DB_PATH": self.db_path}):
            run_migrations()

    def tearDown(self) -> None:
        client.set_usage_db_path("")
        os.unlink(self.db_path)

    def test_complete_records_llm_usage_row(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hello world")],
            usage=SimpleNamespace(input_tokens=123, output_tokens=45),
        )
        mock_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_: response))

        with patch.dict(os.environ, {"AGENT_DB_PATH": self.db_path}, clear=False):
            with patch.object(client, "_get_client", return_value=mock_client):
                result = client.complete(prompt="hi", category="test", model="claude-haiku-4-5")

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

    def test_complete_with_receipt_reports_successful_retry_attempt_count(self):
        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="retried")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )
        calls = 0

        def create(**_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("temporary failure")
            return response

        mock_client = SimpleNamespace(messages=SimpleNamespace(create=create))
        with patch.dict(os.environ, {"AGENT_DB_PATH": self.db_path}, clear=False):
            with (
                patch.object(client, "_get_client", return_value=mock_client),
                patch.object(client, "_should_retry", return_value=True),
                patch.object(client.time, "sleep"),
            ):
                receipt = client.complete_with_receipt(
                    prompt="retry",
                    category="test",
                    model="claude-haiku-4-5",
                )

        self.assertEqual(receipt.text, "retried")
        self.assertEqual(receipt.attempts, 2)
        self.assertTrue(receipt.usage_recorded)

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
            )

        self.assertEqual(result, "exact string")
        complete_receipt.assert_called_once_with(
            prompt="hello",
            system="system",
            max_tokens=99,
            category="test",
            model="claude-haiku-4-5",
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
                result = client.complete(prompt="hi", category="test", model="claude-haiku-4-5")

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
                    result = client.complete(prompt="hi", category="test", model="claude-haiku-4-5")
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
                result = client.complete_vision(prompt="analyze", image_path=image_path, model="claude-haiku-4-5")
        finally:
            os.unlink(image_path)

        self.assertEqual(result, "diagram with service boundaries")

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
