import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from config.settings import Settings
from db.knowledge_atoms import record_knowledge_atom
from db.migrate import run_migrations
from output.market_context_lens import build_market_context_lens, market_context_lens_seed


class FakeMarketLensClient:
    calls: list[str] = []

    @staticmethod
    def complete_json(
        prompt: str,
        system: str = "",
        category: str = "unknown",
        model: str | None = None,
        max_tokens: int = 2048,
    ):
        FakeMarketLensClient.calls.append(prompt)
        if "Update the persistent market lens" in prompt:
            return {
                "delta_summary": "New weekly evidence reinforces paid narrow utilities.",
                "reinforced_rules": ["Keep ranking narrow paid utilities up."],
                "new_signals": ["Fresh WTP signal from the current week."],
                "weakened_or_contradicted_rules": [],
                "radar_adjustments": ["Ask for external proof before build."],
                "watch_next_week": ["Look for non-Telegram corroboration."],
            }
        return {
            "executive_lens": "Prefer narrow paid utilities with visible WTP and cheap validation.",
            "decision_rules": ["Rank up explicit WTP and low-build validation paths."],
            "rank_up_signals": ["Recurring purchases for a small export utility."],
            "rank_down_signals": ["Broad infrastructure-first bets."],
            "buying_triggers": ["Budget or repeated paid conversion evidence."],
            "distribution_patterns": ["Founder-led or organic distribution."],
            "anti_patterns": ["Paid ads without LTV proof."],
            "validation_playbook": ["Test a landing page and workflow demo first."],
            "open_questions": ["Which public source confirms the same pain?"],
        }


class TestMarketContextLens(unittest.TestCase):
    def test_baseline_is_persisted_and_weekly_delta_refreshes(self):
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
                    claim="Browser export utility generates recurring purchases at $40-60.",
                    summary="Narrow paid utility with visible willingness to pay.",
                    evidence_quote="$2500/month and daily purchases",
                    source_post_ids=[544],
                    source_urls=["https://t.me/its_capitan/544"],
                    entities=["browser export"],
                    confidence=0.9,
                    novelty_score=0.7,
                    practical_utility_score=0.95,
                    first_seen_at="2026-06-01T08:00:00Z",
                    last_seen_at="2026-06-01T08:00:00Z",
                )
                record_knowledge_atom(
                    connection,
                    week_label="2026-W28",
                    atom_type="market_signal",
                    claim="Current-week signal shows founders still pay for export automation.",
                    summary="Fresh weekly delta for the same baseline pattern.",
                    evidence_quote="founders still pay for export automation",
                    source_post_ids=[545],
                    source_urls=["https://t.me/its_capitan/545"],
                    entities=["founders"],
                    confidence=0.85,
                    novelty_score=0.7,
                    practical_utility_score=0.9,
                    first_seen_at="2026-07-07T08:00:00Z",
                    last_seen_at="2026-07-07T08:00:00Z",
                )

            FakeMarketLensClient.calls = []
            settings = Settings(
                db_path=db_path,
                llm_api_key="",
                model_provider="anthropic",
                telegram_session_path="",
            )
            first = build_market_context_lens(
                settings,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
                output_root=Path(tmpdir) / "lens",
                llm_client=FakeMarketLensClient,
                use_llm=True,
            )
            second = build_market_context_lens(
                settings,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
                output_root=Path(tmpdir) / "lens",
                llm_client=FakeMarketLensClient,
                use_llm=True,
            )

            self.assertTrue(first.baseline_created)
            self.assertFalse(second.baseline_created)
            self.assertEqual(len(FakeMarketLensClient.calls), 3)
            self.assertEqual(second.baseline_lens["synthesis_mode"], "llm")
            self.assertEqual(second.weekly_delta["synthesis_mode"], "llm")
            self.assertIn("Prefer narrow paid utilities", second.current_context["context_text"])
            self.assertIn("New weekly evidence reinforces", second.current_context["context_text"])
            seed = market_context_lens_seed(second.current_context)
            self.assertIsNotNone(seed)
            self.assertEqual(seed["source_kind"], "market_analyst_context")
            self.assertEqual(seed["radar_role"], "context_only")
            self.assertFalse(seed["build_ready_evidence"])


if __name__ == "__main__":
    unittest.main()
