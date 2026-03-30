"""
Unit tests for scoring engine (src/processing/score_posts.py).

Coverage:
  (a) Bucket boundary values via direct score → bucket mapping
  (b) Cultural keyword override
  (c) _score_personal_interest: boost / downrank / neutral
"""

import unittest

from processing.score_posts import _is_cultural, _score_personal_interest


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


if __name__ == "__main__":
    unittest.main()
