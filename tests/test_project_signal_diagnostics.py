import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from config.settings import Settings
from db.migrate import run_migrations
from output.project_signal_diagnostics import (
    diagnose_project_signal_matching,
    format_project_signal_diagnostics,
)


class TestProjectSignalDiagnostics(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        os.environ["AGENT_DB_PATH"] = self.db_path
        run_migrations()
        self.settings = Settings(
            db_path=self.db_path,
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, name, description, keywords, active, github_repo
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "ashishki/AI_workflow_playbook",
                    "Reusable AI-assisted development workflow",
                    json.dumps(["workflow automation", "agent orchestration"]),
                    1,
                    "ashishki/AI_workflow_playbook",
                ),
            )
            connection.execute(
                """
                INSERT INTO digests (
                    week_label, generated_at, content_md, content_json, post_count
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "2026-W20",
                    "2026-05-11T09:00:00Z",
                    "digest",
                    json.dumps(
                        {
                            "key_findings": [
                                {
                                    "title": "AI Agents and Autonomous Task Management",
                                    "body": "3 posts captured this week.",
                                }
                            ]
                        }
                    ),
                    3,
                ),
            )
            connection.execute(
                """
                INSERT INTO raw_posts (
                    id, channel_username, channel_id, message_id, posted_at, text, raw_json, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "@agents",
                    100,
                    10,
                    "2026-05-12T10:00:00Z",
                    "Agent workflow automation pattern",
                    "{}",
                    "2026-05-12T10:01:00Z",
                ),
            )
            connection.execute(
                """
                INSERT INTO posts (
                    id, raw_post_id, channel_username, posted_at, content, normalized_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    1,
                    "@agents",
                    "2026-05-12T10:00:00Z",
                    "Agent workflow automation pattern for developer tooling",
                    "2026-05-12T10:01:00Z",
                ),
            )
            connection.execute(
                """
                INSERT INTO topics (id, label, description, first_seen, last_seen, post_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "AI Agents and Autonomous Task Management",
                    "Posts about AI agents and workflow automation.",
                    "2026-05-12T10:00:00Z",
                    "2026-05-12T10:00:00Z",
                    1,
                ),
            )
            connection.execute(
                "INSERT INTO post_topics (post_id, topic_id, confidence) VALUES (?, ?, ?)",
                (1, 1, 0.95),
            )
            connection.commit()

    def tearDown(self):
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def test_diagnose_project_signal_matching_reports_candidate_unlinked_topic(self):
        report = diagnose_project_signal_matching(self.settings, week_label="2026-W20", topic_limit=5)

        project = next(
            item for item in report["projects"]
            if item["project_name"] == "ashishki/AI_workflow_playbook"
        )
        topic = project["topics"][0]

        self.assertEqual(report["topic_source"], "digest")
        self.assertEqual(topic["status"], "candidate_unlinked")
        self.assertGreaterEqual(topic["post_keyword_match_count"], 1)
        self.assertEqual(topic["sample_post_ids"], [1])

    def test_format_project_signal_diagnostics_includes_drop_reason(self):
        report = diagnose_project_signal_matching(self.settings, week_label="2026-W20", topic_limit=5)

        rendered = format_project_signal_diagnostics(report)

        self.assertIn("Project signal diagnostics", rendered)
        self.assertIn("candidate_unlinked", rendered)
        self.assertIn("recent topic posts match project keywords", rendered)


if __name__ == "__main__":
    unittest.main()
