import argparse
import io
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
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
_install_stub("telethon", TelegramClient=object)
_install_stub("telethon.errors", FloodWaitError=Exception)
_install_stub("weasyprint")
_install_stub("jinja2")

from config.settings import Settings  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
import main as main_module  # noqa: E402


class TestCostStats(unittest.TestCase):
    def test_cost_stats_outputs_totals_and_breakdown(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        settings = Settings(
            db_path=db_path,
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}):
                run_migrations()

            with sqlite3.connect(db_path) as connection:
                connection.executemany(
                    """
                    INSERT INTO llm_usage (
                        model, task_type, input_tokens, output_tokens, est_cost_usd,
                        called_at, category, cost_usd, duration_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        ("claude-haiku-4-5", "test", 10, 5, 0.1, "2026-03-30T10:00:00Z", "test", 0.1, 50),
                        ("claude-sonnet-4-6", "digest", 20, 10, 0.2, "2026-03-31T10:00:00Z", "digest", 0.2, 75),
                    ],
                )
                connection.commit()

            parser = main_module.build_parser()
            args = parser.parse_args(["cost-stats"])
            self.assertIs(args.handler, main_module.handle_cost_stats)

            output = io.StringIO()
            with patch.object(main_module, "load_settings", return_value=settings):
                with redirect_stdout(output):
                    exit_code = main_module.handle_cost_stats(argparse.Namespace())

            rendered = output.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("total_cost_usd=0.30000000", rendered)
            self.assertIn("distinct_days=2", rendered)
            self.assertIn("claude-haiku-4-5 call_count=1 total_cost_usd=0.10000000", rendered)
            self.assertIn("claude-sonnet-4-6 call_count=1 total_cost_usd=0.20000000", rendered)
        finally:
            os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
