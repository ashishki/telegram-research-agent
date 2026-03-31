"""
Unit tests for scoring engine (src/processing/score_posts.py).

Coverage:
  (a) Bucket boundary values via direct score → bucket mapping
  (b) Cultural keyword override
  (c) _score_personal_interest: boost / downrank / neutral
"""

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from config.settings import Settings
from db.migrate import run_migrations
from processing.score_posts import _is_cultural, _score_personal_interest
from processing.score_posts import score_posts


class TestBucketBoundaryValues(unittest.TestCase):
    """
    Bucket assignment logic mirrored from score_posts.score_posts():

        if signal_score >= strong_threshold:   bucket = "strong"
        elif signal_score >= watch_threshold:  bucket = "watch"
        elif _is_cultural(...):               bucket = "cultural"
        else:                                  bucket = "noise"

    Thresholds from scoring.yaml: strong=0.75, watch=0.45
    """

    STRONG_THRESHOLD = 0.75
    WATCH_THRESHOLD = 0.45

    def _assign_bucket(self, signal_score: float, content: str = "", cultural_keywords: list = None) -> str:
        """Reproduce the bucket-assignment logic from score_posts without DB."""
        cultural_keywords = cultural_keywords or []
        if signal_score >= self.STRONG_THRESHOLD:
            return "strong"
        elif signal_score >= self.WATCH_THRESHOLD:
            return "watch"
        elif _is_cultural(content, cultural_keywords):
            return "cultural"
        else:
            return "noise"

    def test_0_75_is_strong(self):
        self.assertEqual(self._assign_bucket(0.75), "strong")

    def test_0_74_is_watch(self):
        self.assertEqual(self._assign_bucket(0.74), "watch")

    def test_0_45_is_watch(self):
        self.assertEqual(self._assign_bucket(0.45), "watch")

    def test_0_44_is_noise(self):
        self.assertEqual(self._assign_bucket(0.44), "noise")


class TestCulturalKeywordOverride(unittest.TestCase):
    """
    A post with signal_score below the watch threshold (< 0.45) but whose
    content matches a cultural_keywords entry must receive bucket "cultural".
    """

    STRONG_THRESHOLD = 0.75
    WATCH_THRESHOLD = 0.45

    def _assign_bucket(self, signal_score: float, content: str = "", cultural_keywords: list = None) -> str:
        cultural_keywords = cultural_keywords or []
        if signal_score >= self.STRONG_THRESHOLD:
            return "strong"
        elif signal_score >= self.WATCH_THRESHOLD:
            return "watch"
        elif _is_cultural(content, cultural_keywords):
            return "cultural"
        else:
            return "noise"

    def test_cultural_keyword_overrides_noise(self):
        # signal_score below watch threshold → would normally be "noise"
        bucket = self._assign_bucket(
            signal_score=0.20,
            content="Great movie recommendation this week",
            cultural_keywords=["movie"],
        )
        self.assertEqual(bucket, "cultural")

    def test_no_cultural_keyword_remains_noise(self):
        bucket = self._assign_bucket(
            signal_score=0.20,
            content="Random low-quality post",
            cultural_keywords=["movie"],
        )
        self.assertEqual(bucket, "noise")

    def test_cultural_keyword_case_insensitive(self):
        # _is_cultural does .lower() on both sides
        bucket = self._assign_bucket(
            signal_score=0.10,
            content="A great BOOK review",
            cultural_keywords=["book"],
        )
        self.assertEqual(bucket, "cultural")

    def test_cultural_does_not_override_watch(self):
        # score is in watch range — cultural check is never reached
        bucket = self._assign_bucket(
            signal_score=0.50,
            content="Contains movie keyword",
            cultural_keywords=["movie"],
        )
        self.assertEqual(bucket, "watch")

    def test_cultural_does_not_override_strong(self):
        bucket = self._assign_bucket(
            signal_score=0.80,
            content="Contains movie keyword",
            cultural_keywords=["movie"],
        )
        self.assertEqual(bucket, "strong")


class TestScorePersonalInterest(unittest.TestCase):
    """
    Tests for _score_personal_interest(topic_labels, boost_topics, downrank_topics).

    From the implementation:
      - Any boost match  → min(1.0, 0.75 + boost_hits * 0.05)  (≥ 0.80 for 1 hit)
      - Any downrank match → 0.10
      - No match → 0.45
      - Empty labels → 0.40
    """

    BOOST_TOPICS = ["llm", "agentic workflows", "vector search"]
    DOWNRANK_TOPICS = ["crypto", "nft", "web3"]

    def test_boost_topic_returns_high_score(self):
        score = _score_personal_interest(
            topic_labels=["llm fine-tuning", "transformers"],
            boost_topics=self.BOOST_TOPICS,
            downrank_topics=self.DOWNRANK_TOPICS,
        )
        self.assertGreaterEqual(score, 0.75)

    def test_downrank_topic_returns_low_score(self):
        score = _score_personal_interest(
            topic_labels=["crypto market analysis"],
            boost_topics=self.BOOST_TOPICS,
            downrank_topics=self.DOWNRANK_TOPICS,
        )
        self.assertLessEqual(score, 0.15)

    def test_neutral_topic_returns_neutral_score(self):
        score = _score_personal_interest(
            topic_labels=["general technology news"],
            boost_topics=self.BOOST_TOPICS,
            downrank_topics=self.DOWNRANK_TOPICS,
        )
        self.assertGreaterEqual(score, 0.40)
        self.assertLessEqual(score, 0.60)

    def test_empty_labels_returns_below_neutral(self):
        score = _score_personal_interest(
            topic_labels=[],
            boost_topics=self.BOOST_TOPICS,
            downrank_topics=self.DOWNRANK_TOPICS,
        )
        self.assertEqual(score, 0.40)

    def test_boost_takes_precedence_over_downrank(self):
        # A label that matches both boost and downrank → boost wins
        score = _score_personal_interest(
            topic_labels=["llm crypto overlap"],
            boost_topics=["llm"],
            downrank_topics=["crypto"],
        )
        self.assertGreaterEqual(score, 0.75)

    def test_multiple_boost_hits_increase_score(self):
        score_single = _score_personal_interest(
            topic_labels=["llm"],
            boost_topics=["llm", "vector search"],
            downrank_topics=[],
        )
        score_double = _score_personal_interest(
            topic_labels=["llm vector search"],
            boost_topics=["llm", "vector search"],
            downrank_topics=[],
        )
        self.assertGreater(score_double, score_single)

    def test_boost_score_capped_at_1_0(self):
        # Many boost hits should not exceed 1.0
        score = _score_personal_interest(
            topic_labels=["a b c d e f g h i j"],
            boost_topics=["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
            downrank_topics=[],
        )
        self.assertLessEqual(score, 1.0)


class TestScorePostsPersistence(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        self.settings = Settings(
            db_path=self.db_path,
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        with patch.dict(os.environ, {"AGENT_DB_PATH": self.db_path}):
            run_migrations()

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO raw_posts (
                    id, channel_username, channel_id, message_id, posted_at, text, media_type,
                    media_caption, forward_from, view_count, message_url, raw_json, ingested_at, image_description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (1, "@signal", 1001, 5001, now_iso, "Post body", None, None, None, 120, None, "{}", now_iso, None),
            )
            connection.execute(
                """
                INSERT INTO posts (
                    id, raw_post_id, channel_username, posted_at, content, url_count, has_code,
                    language_detected, word_count, normalized_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (1, 1, "@signal", now_iso, "LLM agent systems post", 1, 1, "en", 120, now_iso),
            )
            connection.execute(
                "INSERT INTO topics (id, label, description, first_seen, last_seen, post_count) VALUES (?, ?, ?, ?, ?, ?)",
                (1, "llm", "topic", now_iso, now_iso, 1),
            )
            connection.execute(
                "INSERT INTO post_topics (post_id, topic_id, confidence) VALUES (?, ?, ?)",
                (1, 1, 0.9),
            )
            connection.commit()

    def tearDown(self) -> None:
        os.unlink(self.db_path)

    def test_score_posts_sets_scored_at_and_score_run_id(self):
        score_posts(self.settings, since_days=7)

        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT score_run_id, scored_at FROM posts WHERE id = 1"
            ).fetchone()

        self.assertIsNotNone(row[0])
        self.assertIsNotNone(row[1])
        self.assertTrue(row[0])
        self.assertTrue(row[1])

    def test_score_posts_stores_score_breakdown_json(self):
        score_posts(self.settings, since_days=7)

        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT score_breakdown FROM posts WHERE id = 1"
            ).fetchone()

        breakdown = json.loads(row[0])
        self.assertEqual(
            set(breakdown.keys()),
            {"recency", "engagement", "topic_relevance", "source_quality", "novelty"},
        )
        for value in breakdown.values():
            self.assertIsInstance(value, float)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_score_posts_sets_routed_model(self):
        score_posts(self.settings, since_days=7)

        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT routed_model FROM posts WHERE id = 1"
            ).fetchone()

        self.assertIsNotNone(row[0])
        self.assertTrue(row[0])


class TestBucketDistributionEvals(unittest.TestCase):
    STRONG_THRESHOLD = 0.75
    WATCH_THRESHOLD = 0.45

    def _assign_bucket(self, signal_score: float) -> str:
        if signal_score >= self.STRONG_THRESHOLD:
            return "strong"
        if signal_score >= self.WATCH_THRESHOLD:
            return "watch"
        return "noise"

    def test_scores_above_point_seven_can_all_land_in_strong_bucket(self):
        buckets = [self._assign_bucket(score) for score in [0.8] * 10]
        self.assertEqual(buckets, ["strong"] * 10)

    def test_scores_in_watch_band_land_in_watch_bucket(self):
        scores = [0.45, 0.47, 0.49, 0.5, 0.52, 0.54, 0.55, 0.57, 0.59, 0.6]
        buckets = [self._assign_bucket(score) for score in scores]
        self.assertEqual(buckets, ["watch"] * 10)

    def test_mixed_scores_assign_noise_strong_and_watch(self):
        buckets = [self._assign_bucket(score) for score in [0.1, 0.9, 0.5]]
        self.assertEqual(buckets, ["noise", "strong", "watch"])


if __name__ == "__main__":
    unittest.main()
