import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from config.settings import Settings
from db.knowledge_atoms import record_knowledge_atom
from db.migrate import run_migrations
from output.ai_report_contract import INTELLIGENCE_CONTRACT_VERSION, RADAR_INTELLIGENCE_CONTRACT_VERSION
from output.idea_threads import refresh_idea_threads
from output.opportunity_seed_export import export_opportunity_seeds
from output.reporting_period import resolve_reporting_period


class TestOpportunitySeedExport(unittest.TestCase):
    def test_period_inputs_reject_ambiguous_rolling_combinations(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        now = datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "week_label cannot be combined"):
            export_opportunity_seeds(
                settings,
                days=7,
                week_label="2026-W28",
                now=now,
            )
        with self.assertRaisesRegex(ValueError, "reporting_period cannot be combined"):
            export_opportunity_seeds(
                settings,
                days=7,
                reporting_period=resolve_reporting_period(now),
            )

    def test_completed_week_seed_selection_is_half_open_and_carries_period_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "agent.db")
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}):
                run_migrations()

            import sqlite3

            with sqlite3.connect(db_path) as connection:
                for post_id, posted_at in (
                    (1, "2026-07-06T00:00:00Z"),
                    (2, "2026-07-13T00:00:00Z"),
                ):
                    content = f"How to automate this workflow manually, boundary post {post_id}."
                    connection.execute(
                        """
                        INSERT INTO raw_posts (
                            id, channel_username, channel_id, message_id, posted_at, text,
                            media_type, media_caption, forward_from, view_count, message_url,
                            raw_json, ingested_at, image_description
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            post_id,
                            "@boundary",
                            10,
                            post_id,
                            posted_at,
                            content,
                            None,
                            None,
                            None,
                            10,
                            f"https://t.me/boundary/{post_id}",
                            "{}",
                            posted_at,
                            None,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO posts (
                            id, raw_post_id, channel_username, posted_at, content,
                            url_count, has_code, language_detected, word_count, normalized_at,
                            bucket, signal_score
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            post_id,
                            post_id,
                            "@boundary",
                            posted_at,
                            content,
                            0,
                            0,
                            "en",
                            9,
                            posted_at,
                            "noise",
                            0.1,
                        ),
                    )
                connection.commit()

            out_path = Path(tmpdir) / "seeds.json"
            result = export_opportunity_seeds(
                Settings(
                    db_path=db_path,
                    llm_api_key="",
                    model_provider="anthropic",
                    telegram_session_path="",
                ),
                limit=10,
                output_path=out_path,
                now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
            )
            seeds = json.loads(out_path.read_text(encoding="utf-8"))

            self.assertEqual(result.week_label, "2026-W28")
            self.assertEqual(result.period_mode, "completed_iso_week")
            self.assertEqual(result.analysis_period_start, "2026-07-06T00:00:00Z")
            self.assertEqual(result.analysis_period_end, "2026-07-13T00:00:00Z")
            self.assertEqual([seed["post_id"] for seed in seeds], ["1"])
            self.assertEqual(seeds[0]["reporting_week"], "2026-W28")
            self.assertEqual(seeds[0]["period_mode"], "completed_iso_week")

    def test_exports_demand_surface_seed_for_radar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "agent.db")
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}):
                run_migrations()

            import sqlite3

            posted_at = "2026-05-23T10:00:00Z"
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO raw_posts (
                        id, channel_username, channel_id, message_id, posted_at, text,
                        media_type, media_caption, forward_from, view_count, message_url,
                        raw_json, ingested_at, image_description
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        "@its_capitan",
                        10,
                        100,
                        posted_at,
                        "Owners ask how to make Telegram channel content searchable for SEO.",
                        None,
                        None,
                        None,
                        500,
                        "https://t.me/its_capitan/100",
                        "{}",
                        posted_at,
                        None,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO posts (
                        id, raw_post_id, channel_username, posted_at, content,
                        url_count, has_code, language_detected, word_count, normalized_at,
                        bucket, signal_score
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        1,
                        "@its_capitan",
                        posted_at,
                        "Owners ask how to make Telegram channel content searchable for SEO.",
                        0,
                        0,
                        "en",
                        10,
                        posted_at,
                        "noise",
                        0.2,
                    ),
                )
                connection.commit()

            out_path = Path(tmpdir) / "seeds.json"
            result = export_opportunity_seeds(
                Settings(
                    db_path=db_path,
                    llm_api_key="",
                    model_provider="anthropic",
                    telegram_session_path="",
                ),
                days=7,
                limit=10,
                output_path=out_path,
                now=datetime(2026, 5, 25, tzinfo=timezone.utc),
            )
            seeds = json.loads(out_path.read_text(encoding="utf-8"))

            self.assertEqual(result.seed_count, 1)
            self.assertEqual(seeds[0]["contract_version"], RADAR_INTELLIGENCE_CONTRACT_VERSION)
            self.assertEqual(seeds[0]["intelligence_contract_version"], INTELLIGENCE_CONTRACT_VERSION)
            self.assertEqual(seeds[0]["mvp_shape"], "Telegram Channel SEO Site Generator")
            self.assertIn("creator_content_gap", seeds[0]["demand_surfaces"])
            self.assertEqual(seeds[0]["source_url"], "https://t.me/its_capitan/100")

    def test_exports_knowledge_thread_seed_for_radar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "agent.db")
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}):
                run_migrations()

            import sqlite3

            with sqlite3.connect(db_path) as connection:
                record_knowledge_atom(
                    connection,
                    week_label="2026-W28",
                    atom_type="market_signal",
                    claim="AI support teams are asking for lead response SLA monitors.",
                    summary="Repeated operator demand around measuring lead response time.",
                    evidence_quote="lead response SLA monitor",
                    source_post_ids=[501],
                    source_urls=["https://t.me/market_ai/501"],
                    entities=["lead response", "SLA"],
                    confidence=0.82,
                    novelty_score=0.7,
                    practical_utility_score=0.9,
                    first_seen_at="2026-07-06T08:00:00Z",
                    last_seen_at="2026-07-06T08:00:00Z",
                )
            settings = Settings(
                db_path=db_path,
                llm_api_key="",
                model_provider="anthropic",
                telegram_session_path="",
            )
            refresh_idea_threads(settings, weeks=12, now=datetime(2026, 7, 8, tzinfo=timezone.utc))

            out_path = Path(tmpdir) / "seeds.json"
            result = export_opportunity_seeds(
                settings,
                days=7,
                limit=10,
                output_path=out_path,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )
            seeds = json.loads(out_path.read_text(encoding="utf-8"))

            self.assertEqual(result.knowledge_thread_count, 1)
            self.assertEqual(result.seed_count, 1)
            self.assertEqual(seeds[0]["contract_version"], RADAR_INTELLIGENCE_CONTRACT_VERSION)
            self.assertEqual(seeds[0]["intelligence_contract_version"], INTELLIGENCE_CONTRACT_VERSION)
            self.assertEqual(seeds[0]["source_kind"], "knowledge_thread")
            self.assertIn("knowledge_thread_slug", seeds[0])
            self.assertEqual(seeds[0]["source_atom_ids"], [1])
            self.assertEqual(seeds[0]["source_url"], "https://t.me/market_ai/501")

    def test_bounded_hype_only_thread_remains_ineligible_for_radar_seed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "agent.db")
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}):
                run_migrations()

            import sqlite3

            with sqlite3.connect(db_path) as connection:
                record_knowledge_atom(
                    connection,
                    week_label="2026-W28",
                    atom_type="market_signal",
                    claim="A hype-only workflow claim must not become a Radar seed.",
                    summary="The bounded projection still preserves the legacy status gate.",
                    evidence_quote="hype-only workflow claim",
                    source_post_ids=[601],
                    source_urls=["https://t.me/non_market_channel/601"],
                    entities=["hype-only workflow"],
                    staleness_status="hype_only",
                    first_seen_at="2026-07-07T08:00:00Z",
                    last_seen_at="2026-07-07T08:00:00Z",
                )
            settings = Settings(
                db_path=db_path,
                llm_api_key="",
                model_provider="anthropic",
                telegram_session_path="",
            )
            refresh_idea_threads(
                settings,
                weeks=12,
                now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
            )
            output = Path(tmpdir) / "seeds.json"
            result = export_opportunity_seeds(
                settings,
                output_path=output,
                now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
            )
            seeds = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result.knowledge_thread_count, 0)
        self.assertFalse(any(seed.get("source_kind") == "knowledge_thread" for seed in seeds))

    def test_exports_curated_market_analyst_context_without_displacing_seed_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "agent.db")
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}):
                run_migrations()

            import sqlite3

            with sqlite3.connect(db_path) as connection:
                record_knowledge_atom(
                    connection,
                    week_label="2026-W28",
                    atom_type="case_study",
                    claim="Founder-led signal stacking generated 90 qualified demos for a niche B2B market.",
                    summary="Precise ICP, purchase-signal targeting, and founder-authored outreach created qualified demos.",
                    evidence_quote="90+ qualified demos with 41.8% open rate and 17.1% reply rate",
                    source_post_ids=[140],
                    source_urls=["https://t.me/leadgenvalley/140"],
                    entities=["B2B founders", "sales teams"],
                    confidence=0.92,
                    novelty_score=0.7,
                    practical_utility_score=0.95,
                    first_seen_at="2026-07-06T08:00:00Z",
                    last_seen_at="2026-07-06T08:00:00Z",
                )
            settings = Settings(
                db_path=db_path,
                llm_api_key="",
                model_provider="anthropic",
                telegram_session_path="",
            )
            refresh_idea_threads(settings, weeks=12, now=datetime(2026, 7, 8, tzinfo=timezone.utc))

            out_path = Path(tmpdir) / "seeds.json"
            result = export_opportunity_seeds(
                settings,
                days=7,
                limit=1,
                output_path=out_path,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )
            seeds = json.loads(out_path.read_text(encoding="utf-8"))
            market_pack = json.loads(Path(result.market_pack_path).read_text(encoding="utf-8"))
            context_seed = next(seed for seed in seeds if seed.get("source_kind") == "market_analyst_context")

            self.assertEqual(result.seed_count, 2)
            self.assertTrue(any(seed.get("source_kind") == "knowledge_thread" for seed in seeds))
            self.assertEqual(market_pack["status"], "available")
            self.assertEqual(market_pack["curated_atom_count"], 1)
            self.assertGreaterEqual(market_pack["market_thread_count"], 1)
            self.assertEqual(market_pack["raw_fallback_posts_scanned"], 0)
            self.assertTrue(market_pack["analyst_context"]["what_works"])
            self.assertTrue(market_pack["analyst_context"]["proof_points"])
            self.assertFalse(context_seed["build_ready_evidence"])
            self.assertTrue(context_seed["context_only"])
            self.assertEqual(context_seed["radar_role"], "context_only")
            self.assertEqual(context_seed["contract_version"], RADAR_INTELLIGENCE_CONTRACT_VERSION)
            self.assertEqual(context_seed["intelligence_contract_version"], INTELLIGENCE_CONTRACT_VERSION)
            self.assertEqual(context_seed["evidence_strength"], "context_only_market_analyst_pack")
            self.assertNotIn("mvp_shape", context_seed)
            self.assertIn("do not select this context row", context_seed["verification_needed"][0])

    def test_exports_market_pain_pack_raw_fallback_as_context_only_seed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "agent.db")
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}):
                run_migrations()

            import sqlite3

            posted_at = "2026-07-07T10:00:00Z"
            content = (
                "Small business founders pay for workflow automation because leads are handled "
                "вручную in Telegram and response is too slow."
            )
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO raw_posts (
                        id, channel_username, channel_id, message_id, posted_at, text,
                        media_type, media_caption, forward_from, view_count, message_url,
                        raw_json, ingested_at, image_description
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        "@huntermikevolkov",
                        10,
                        777,
                        posted_at,
                        content,
                        None,
                        None,
                        None,
                        250,
                        "https://t.me/huntermikevolkov/777",
                        "{}",
                        posted_at,
                        None,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO posts (
                        id, raw_post_id, channel_username, posted_at, content,
                        url_count, has_code, language_detected, word_count, normalized_at,
                        bucket, signal_score
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (1, 1, "@huntermikevolkov", posted_at, content, 0, 0, "en", 18, posted_at, "noise", 0.3),
                )
                connection.commit()

            out_path = Path(tmpdir) / "seeds.json"
            result = export_opportunity_seeds(
                Settings(
                    db_path=db_path,
                    llm_api_key="",
                    model_provider="anthropic",
                    telegram_session_path="",
                ),
                days=7,
                limit=10,
                output_path=out_path,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )
            seeds = json.loads(out_path.read_text(encoding="utf-8"))
            market_pack = json.loads(Path(result.market_pack_path).read_text(encoding="utf-8"))
            context_seed = next(seed for seed in seeds if seed.get("source_kind") == "market_analyst_context")

            self.assertEqual(market_pack["status"], "available")
            self.assertEqual(market_pack["posts_scanned"], 1)
            self.assertEqual(market_pack["curated_atom_count"], 0)
            self.assertEqual(market_pack["raw_fallback_posts_scanned"], 1)
            self.assertTrue(market_pack["analyst_context"]["market_pains"])
            self.assertFalse(context_seed["build_ready_evidence"])
            self.assertEqual(context_seed["radar_role"], "context_only")
            self.assertEqual(context_seed["evidence_strength"], "context_only_market_analyst_pack")
            self.assertIn("external demand validation", context_seed["verification_needed"][1])

    def test_market_pain_pack_empty_audit_does_not_create_seed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "agent.db")
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}):
                run_migrations()
            out_path = Path(tmpdir) / "seeds.json"
            result = export_opportunity_seeds(
                Settings(
                    db_path=db_path,
                    llm_api_key="",
                    model_provider="anthropic",
                    telegram_session_path="",
                ),
                days=7,
                limit=10,
                output_path=out_path,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )

            seeds = json.loads(out_path.read_text(encoding="utf-8"))
            market_pack = json.loads(Path(result.market_pack_path).read_text(encoding="utf-8"))

            self.assertEqual(seeds, [])
            self.assertEqual(market_pack["status"], "empty")
            self.assertEqual(market_pack["radar_gate_audit"]["status"], "no_market_context")
            self.assertFalse(market_pack["radar_gate_audit"]["build_ready_evidence"])

    def test_market_context_baseline_uses_twelve_week_window_for_radar_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "agent.db")
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}):
                run_migrations()

            import sqlite3

            with sqlite3.connect(db_path) as connection:
                record_knowledge_atom(
                    connection,
                    week_label="2026-W21",
                    atom_type="case_study",
                    claim="Browser data export app generates recurring purchases at a $40-60 price point.",
                    summary="A narrow export utility can monetize despite a single-use workflow.",
                    evidence_quote="$2500/month from daily recurring purchases",
                    source_post_ids=[544],
                    source_urls=["https://t.me/its_capitan/544"],
                    entities=["browser export", "solo founder"],
                    confidence=0.9,
                    novelty_score=0.7,
                    practical_utility_score=0.93,
                    first_seen_at="2026-06-01T08:00:00Z",
                    last_seen_at="2026-06-01T08:00:00Z",
                )

            settings = Settings(
                db_path=db_path,
                llm_api_key="",
                model_provider="anthropic",
                telegram_session_path="",
            )
            out_path = Path(tmpdir) / "seeds.json"
            result = export_opportunity_seeds(
                settings,
                days=7,
                limit=10,
                output_path=out_path,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )
            seeds = json.loads(out_path.read_text(encoding="utf-8"))
            context_seed = next(seed for seed in seeds if seed.get("source_kind") == "market_analyst_context")
            market_pack = json.loads(Path(result.market_pack_path).read_text(encoding="utf-8"))

            self.assertEqual(result.seed_count, 1)
            self.assertEqual(market_pack["status"], "available")
            self.assertEqual(market_pack["curated_atom_count"], 1)
            self.assertIn("Browser data export", context_seed["text"])
            self.assertIn("Baseline:", context_seed["text"])
            self.assertIn("Weekly delta:", context_seed["text"])
            self.assertEqual(context_seed["radar_role"], "context_only")
            self.assertTrue(Path(result.market_lens_path).exists())
            self.assertTrue(Path(result.market_baseline_path).exists())
            self.assertTrue(Path(result.market_delta_path).exists())


if __name__ == "__main__":
    unittest.main()
