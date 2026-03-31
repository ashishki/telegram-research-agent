import unittest

from config.settings import CHEAP_MODEL, MID_MODEL, STRONG_MODEL
from llm.router import route


class TestRouter(unittest.TestCase):
    def test_route_synthesis_returns_strong_model(self):
        self.assertEqual(route("synthesis", signal_score=0.8), STRONG_MODEL)

    def test_route_per_post_low_signal_returns_cheap_model(self):
        self.assertEqual(route("per_post", signal_score=0.3), CHEAP_MODEL)

    def test_route_per_post_mid_signal_returns_mid_model(self):
        self.assertEqual(route("per_post", signal_score=0.6), MID_MODEL)

    def test_route_per_post_watch_boundary_returns_mid_model(self):
        self.assertEqual(route("per_post", signal_score=0.45), MID_MODEL)

    def test_route_per_post_none_signal_warns_and_returns_cheap_model(self):
        with self.assertLogs("llm.router", level="WARNING") as logs:
            selected_model = route("per_post", signal_score=None)

        self.assertEqual(selected_model, CHEAP_MODEL)
        self.assertTrue(any("signal_score=None" in message for message in logs.output))


if __name__ == "__main__":
    unittest.main()
