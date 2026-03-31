import os
import sqlite3
import sys
import tempfile
import types
import unittest
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
        with patch.dict(os.environ, {"AGENT_DB_PATH": self.db_path}):
            run_migrations()

    def tearDown(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
