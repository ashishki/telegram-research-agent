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
    module = sys.modules.get(module_name)
    if module is None:
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module
    for name, value in attributes.items():
        setattr(module, name, value)


_install_stub(
    "anthropic",
    APIConnectionError=Exception,
    APIStatusError=Exception,
    APITimeoutError=Exception,
    Anthropic=object,
    RateLimitError=Exception,
)
_install_stub("telethon", TelegramClient=object)
_install_stub("telethon.errors", FloodWaitError=Exception)
_install_stub("weasyprint")
_install_stub("jinja2")
_install_stub("numpy", asarray=lambda value: value)
_install_stub("sklearn")
_install_stub("sklearn.cluster", KMeans=object)
_install_stub("sklearn.feature_extraction")
_install_stub("sklearn.feature_extraction.text", ENGLISH_STOP_WORDS=set(), TfidfVectorizer=object)
_install_stub("sklearn.metrics", silhouette_score=lambda *_args, **_kwargs: 0.0)

from db.migrate import run_migrations  # noqa: E402
from db.research_brief_receipts import record_research_brief_receipt  # noqa: E402
import main  # noqa: E402


class TestResearchBriefReceiptCli(unittest.TestCase):
    def _make_receipt_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name
        with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
            run_migrations()
            with sqlite3.connect(db_path) as connection:
                digest_id = connection.execute(
                    """
                    INSERT INTO digests (
                        week_label,
                        generated_at,
                        content_md,
                        post_count
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    ("2026-W22", "2026-05-29T09:00:00Z", "# Brief", 2),
                ).lastrowid
                connection.commit()
                record_research_brief_receipt(
                    connection,
                    receipt_id="rbr_cli_2026_w22",
                    week_label="2026-W22",
                    generated_at="2026-05-29T10:00:00Z",
                    window_start="2026-05-22T00:00:00Z",
                    window_end="2026-05-29T00:00:00Z",
                    included_channels=["source_a"],
                    post_counts={"total_posts": 2, "strong_count": 1, "watch_count": 1},
                    source_set={
                        "telegram_source_links": ["https://t.me/source_a/123"],
                        "source_post_ids": [1],
                    },
                    project_scopes=["telegram-research-agent"],
                    topic_scopes=["agent-memory"],
                    digest_id=digest_id,
                    markdown_path="/tmp/brief.md",
                    json_path="/tmp/brief.json",
                    html_path="/tmp/brief.html",
                    telegraph_url="https://telegra.ph/brief",
                    telegram_delivery_timestamp="2026-05-29T10:05:00Z",
                    telegram_message_id=123,
                )
        return db_path

    def test_memory_inspect_receipts_prints_debug_surface(self):
        db_path = self._make_receipt_db()
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):

                with patch.object(
                    sys,
                    "argv",
                    [
                        "main.py",
                        "memory",
                        "inspect-receipts",
                        "--week",
                        "2026-W22",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Receipt rbr_cli_2026_w22", output)
        self.assertIn("source_of_truth: research_brief_receipts", output)
        self.assertIn("refresh_rule: created once after generation", output)
        self.assertIn("retrieval_path: receipt_id, week_label, digest_id, artifact path, or Telegraph URL", output)
        self.assertIn("debug_surface: identity, evidence window, source set", output)
        self.assertIn("delivery: telegraph=https://telegra.ph/brief", output)
        self.assertIn("verification: status=pending", output)

    def test_memory_review_receipt_updates_operator_status(self):
        db_path = self._make_receipt_db()
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "main.py",
                        "memory",
                        "review-receipt",
                        "--receipt-id",
                        "rbr_cli_2026_w22",
                        "--status",
                        "waived",
                        "--notes",
                        "Accepted after manual read",
                        "--checked-by",
                        "ashish",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Reviewed Research Brief receipt rbr_cli_2026_w22", output)
        self.assertIn("status=waived", output)
        self.assertIn("method=operator_review", output)
        self.assertIn("checked_by=ashish", output)
        self.assertIn("notes=Accepted after manual read", output)


if __name__ == "__main__":
    unittest.main()
