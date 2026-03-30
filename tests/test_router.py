import unittest

from config.settings import CHEAP_MODEL, STRONG_MODEL
from llm.router import route


class TestRouter(unittest.TestCase):
    def test_route_synthesis_returns_strong_model(self):
        self.assertEqual(route("synthesis", signal_score=0.8), STRONG_MODEL)

    def test_route_per_post_low_signal_returns_cheap_model(self):
        self.assertEqual(route("per_post", signal_score=0.3), CHEAP_MODEL)


if __name__ == "__main__":
    unittest.main()
