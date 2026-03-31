import unittest

from output.personalize import apply_personalization


class TestPersonalize(unittest.TestCase):
    def test_boost_topic_increases_score(self):
        posts = [
            {"id": 1, "content": "FastAPI routing improvements", "signal_score": 0.5, "bucket": "watch"}
        ]

        personalized_posts = apply_personalization(posts, {"boost_topics": ["FastAPI"], "downrank_topics": []})

        self.assertGreater(personalized_posts[0]["personalized_score"], posts[0]["signal_score"])

    def test_downrank_topic_decreases_score(self):
        posts = [
            {"id": 1, "content": "crypto market discussion", "signal_score": 0.5, "bucket": "watch"}
        ]

        personalized_posts = apply_personalization(posts, {"boost_topics": [], "downrank_topics": ["crypto"]})

        self.assertLess(personalized_posts[0]["personalized_score"], posts[0]["signal_score"])

    def test_strong_post_stays_above_watch_threshold(self):
        posts = [
            {"id": 1, "content": "crypto update with strong signal", "signal_score": 0.8, "bucket": "strong"}
        ]

        personalized_posts = apply_personalization(posts, {"boost_topics": [], "downrank_topics": ["crypto"]})

        self.assertGreaterEqual(personalized_posts[0]["personalized_score"], 0.45)


if __name__ == "__main__":
    unittest.main()
