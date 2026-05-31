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
import main  # noqa: E402


class TestChannelIntelligenceCli(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name
        with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
            run_migrations()
            with sqlite3.connect(db_path) as connection:
                claim_id = connection.execute(
                    """
                    INSERT INTO channel_repeated_claims (
                        claim_key,
                        normalized_claim,
                        claim_type,
                        status,
                        evidence_strength,
                        first_seen_week,
                        last_seen_week,
                        occurrence_count,
                        channel_count,
                        project_name,
                        topic_label,
                        entity_labels_json,
                        evidence_item_ids_json,
                        refresh_scope_json,
                        extraction_version,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "claim:cli",
                        "cli repeated claim",
                        "cross_channel_repeated",
                        "repeated",
                        "strong",
                        "2026-W22",
                        "2026-W22",
                        2,
                        2,
                        "telegram-research-agent",
                        "Agents",
                        "[]",
                        "[1, 2]",
                        '{"week_label":"2026-W22"}',
                        "fixture",
                        "2026-05-29T10:00:00Z",
                        "2026-05-29T10:00:00Z",
                    ),
                ).lastrowid
                narrative_id = connection.execute(
                    """
                    INSERT INTO channel_narratives (
                        narrative_key,
                        title,
                        summary,
                        status,
                        project_name,
                        topic_label,
                        first_seen_week,
                        last_seen_week,
                        supporting_post_count,
                        supporting_channel_count,
                        linked_claim_count,
                        evidence_item_ids_json,
                        source_channels_json,
                        refresh_scope_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "narrative:cli",
                        "Agents signals for telegram-research-agent in 2026-W22",
                        "fixture",
                        "active",
                        "telegram-research-agent",
                        "Agents",
                        "2026-W22",
                        "2026-W22",
                        2,
                        2,
                        1,
                        "[1, 2]",
                        '["source_a", "source_b"]',
                        '{"extractor_version":"fixture"}',
                        "2026-05-29T10:00:00Z",
                        "2026-05-29T10:00:00Z",
                    ),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO narrative_claim_links (
                        narrative_id,
                        claim_id,
                        link_reason,
                        shared_evidence_count,
                        shared_entities_json,
                        confidence,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        narrative_id,
                        claim_id,
                        "fixture",
                        2,
                        '["telegram-research-agent", "Agents"]',
                        0.9,
                        "2026-05-29T10:00:00Z",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO source_observations (
                        channel_username,
                        week_label,
                        scope_key,
                        project_name,
                        topic_label,
                        post_count,
                        scored_count,
                        evidence_count,
                        cited_count,
                        acted_on_count,
                        skipped_count,
                        rejected_count,
                        low_signal_count,
                        repeated_claim_count,
                        useful_count,
                        counters_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "source_a",
                        "2026-W22",
                        "project:telegram-research-agent|topic:Agents",
                        "telegram-research-agent",
                        "Agents",
                        2,
                        2,
                        1,
                        1,
                        1,
                        0,
                        0,
                        0,
                        1,
                        1,
                        '{"post_ids":[1,2]}',
                        "2026-05-29T10:00:00Z",
                        "2026-05-29T10:00:00Z",
                    ),
                )
                entity_id = connection.execute(
                    """
                    INSERT INTO intelligence_entity_links (
                        entity_label,
                        entity_type,
                        linked_object_type,
                        linked_object_id,
                        project_name,
                        topic_label,
                        source_table,
                        source_row_id,
                        confidence,
                        reason,
                        extractor_version,
                        week_label,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "Agents",
                        "topic",
                        "claim",
                        str(claim_id),
                        "telegram-research-agent",
                        "Agents",
                        "channel_repeated_claims",
                        claim_id,
                        0.9,
                        "fixture",
                        "fixture",
                        "2026-W22",
                        "2026-05-29T10:00:00Z",
                    ),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO project_intelligence_links (
                        project_name,
                        linked_object_type,
                        linked_object_id,
                        week_label,
                        relevance_score,
                        match_reason,
                        evidence_item_ids_json,
                        active_project,
                        refresh_scope_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "telegram-research-agent",
                        "entity",
                        str(entity_id),
                        "2026-W22",
                        0.9,
                        "fixture",
                        "[1, 2]",
                        1,
                        '{"extractor_version":"fixture"}',
                        "2026-05-29T10:00:00Z",
                        "2026-05-29T10:00:00Z",
                    ),
                )
                connection.commit()
        return db_path

    def test_memory_inspect_channel_intelligence_prints_debug_surface(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "main.py",
                        "memory",
                        "inspect-channel-intelligence",
                        "--week",
                        "2026-W22",
                        "--project",
                        "telegram-research-agent",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Channel Intelligence inspection", output)
        self.assertIn("source_of_truth: channel_repeated_claims", output)
        self.assertIn("refresh_rule: derived rows rebuilt", output)
        self.assertIn("retrieval_path: week, project, topic, channel, status", output)
        self.assertIn("claims (1):", output)
        self.assertIn("narratives (1):", output)
        self.assertIn("source_observations (1):", output)
        self.assertIn("entity_links (1):", output)
        self.assertIn("project_links (1):", output)
        self.assertIn("claim_links: claim=", output)
        self.assertIn("raw_inputs:", output)

    def test_memory_inspect_channel_intelligence_can_filter_sources_by_channel(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "main.py",
                        "memory",
                        "inspect-channel-intelligence",
                        "--kind",
                        "sources",
                        "--channel",
                        "source_a",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("source_observations (1):", output)
        self.assertIn("channel=source_a", output)
        self.assertNotIn("claims (", output)


if __name__ == "__main__":
    unittest.main()
