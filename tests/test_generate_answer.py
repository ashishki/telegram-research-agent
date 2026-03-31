import sys
import types
import unittest
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

from config.settings import Settings  # noqa: E402
from output.generate_answer import generate_answer  # noqa: E402


class TestGenerateAnswer(unittest.TestCase):
    def test_generate_answer_returns_non_empty_string(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch("output.generate_answer.LLMClient.complete", return_value="Ответ по данным") as mock_complete:
            result = generate_answer(
                question="Что нового по агентам?",
                context={"topics_summary": "- agents", "excerpts": ["- excerpt"]},
                settings=settings,
            )

        self.assertTrue(result)
        self.assertEqual(result, "Ответ по данным")
        mock_complete.assert_called_once()


if __name__ == "__main__":
    unittest.main()
