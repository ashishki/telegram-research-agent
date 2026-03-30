import os
import sqlite3
import sys
import tempfile
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


_install_stub(
    "anthropic",
    APIConnectionError=Exception,
    APIStatusError=Exception,
    APITimeoutError=Exception,
    Anthropic=object,
    RateLimitError=Exception,
)
_install_stub("telethon")
_install_stub("weasyprint")
_install_stub("jinja2")

from config.settings import Settings  # noqa: E402
from output.report_schema import DigestResult  # noqa: E402
import bot.handlers as handlers  # noqa: E402


class TestHandlers(unittest.TestCase):
    def test_handle_digest_sends_markdown_content_without_parse_mode(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            with sqlite3.connect(db_path) as connection:
                connection.execute("CREATE TABLE digests (week_label TEXT, content_md TEXT)")
                connection.execute(
                    "INSERT INTO digests (week_label, content_md) VALUES (?, ?)",
                    ("2026-W14", "* legacy markdown *"),
                )
                connection.commit()

            settings = Settings(
                db_path=db_path,
                llm_api_key="",
                model_provider="anthropic",
                telegram_session_path="",
            )

            with patch.object(handlers, "_compute_week_label", return_value="2026-W14"):
                with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                    with patch.object(handlers, "send_text") as mock_send_text:
                        handlers.handle_digest(chat_id="42", args="", settings=settings)

            mock_send_text.assert_called_once_with(
                chat_id="42",
                text="* legacy markdown *",
                token="bot-token",
                parse_mode=None,
            )
        finally:
            os.unlink(db_path)

    def test_handle_run_digest_relies_on_run_digest_delivery_only(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        summary = DigestResult(week_label="2026-W14", output_path="/tmp/digest.md", post_count=3, json_path="/tmp/digest.json")

        with patch.object(handlers, "run_digest", return_value=summary) as mock_run_digest:
            with patch.object(handlers, "generate_recommendations") as mock_generate_recommendations:
                with patch.object(handlers, "send_report_preview") as mock_send_report_preview:
                    with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                        handlers.handle_run_digest(chat_id="42", args="", settings=settings)

        mock_run_digest.assert_called_once_with(settings)
        mock_generate_recommendations.assert_not_called()
        mock_send_report_preview.assert_called_once_with(
            chat_id="42",
            title="Дайджест сгенерирован",
            summary_lines=["/tmp/digest.md", "/tmp/digest.json"],
            week_label="2026-W14",
            token="bot-token",
        )


if __name__ == "__main__":
    unittest.main()
