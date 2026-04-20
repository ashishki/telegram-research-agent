import sys
import types
import unittest
from types import SimpleNamespace
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

from output.generate_recommendations import _render_insights_fragment, _rewrite_insight_source_urls, run_recommendations  # noqa: E402


class TestGenerateRecommendationsHtml(unittest.TestCase):
    def test_render_insights_fragment_wraps_paragraphs_and_links(self):
        content = (
            "<b>💡 Инсайты недели</b>\n\n"
            "<b>[Implement] Project</b>\n"
            "Полезный абзац с объяснением.\n"
            "https://example.com/source"
        )

        html = _render_insights_fragment(content)

        self.assertIn("<h2><b>💡 Инсайты недели</b></h2>", html)
        self.assertIn("<p><b>[Implement] Project</b></p>", html)
        self.assertIn("<p>Полезный абзац с объяснением. <a href=\"https://example.com/source\">https://example.com/source</a></p>", html)

    def test_rewrite_insight_source_urls_rebinds_to_best_matching_candidates(self):
        content = (
            "<b>💡 Инсайты недели</b>\n\n"
            "<b>[Implement] telegram-research-agent — Cross-channel clusters</b>\n"
            "Нужно отслеживать cluster spread по нескольким каналам и выделять это в дайджесте.\n"
            "<a href=\"https://t.me/NeuralShit/7342\">источник</a>\n\n"
            "<b>[Implement] gdev-agent — Cost-aware routing</b>\n"
            "В multi-tenant сервисе нужен дешёвый первый проход и дорогой только для неоднозначных кейсов.\n"
            "<a href=\"https://t.me/NeuralShit/7342\">источник</a>"
        )
        candidates = [
            {
                "url": "https://t.me/channelA/100",
                "project_name": "telegram-research-agent",
                "channel": "@signal_a",
                "match_text": "telegram-research-agent cross channel clusters spread digest theme week",
            },
            {
                "url": "https://t.me/channelB/200",
                "project_name": "gdev-agent",
                "channel": "@signal_b",
                "match_text": "gdev-agent cost aware routing cheap first pass multi tenant service classification",
            },
        ]

        rewritten = _rewrite_insight_source_urls(content, candidates)

        self.assertIn("https://t.me/channelA/100", rewritten)
        self.assertIn("https://t.me/channelB/200", rewritten)
        self.assertNotIn("https://t.me/NeuralShit/7342", rewritten)


class TestRunRecommendations(unittest.TestCase):
    def test_run_recommendations_continues_when_project_context_snapshots_fail(self):
        settings = SimpleNamespace(db_path=":memory:")

        with patch("output.generate_recommendations._load_digest_summary", return_value=("digest", "summary", [])), \
             patch("output.generate_recommendations._load_projects_context", return_value="projects"), \
             patch("output.generate_recommendations._load_project_context_snapshots", side_effect=RuntimeError("boom")), \
             patch("output.generate_recommendations._load_completed_study_history", return_value="study"), \
             patch("output.generate_recommendations._load_recent_decisions", return_value="decisions"), \
             patch("output.generate_recommendations._load_recent_project_evidence", return_value=("evidence", [])), \
             patch("output.generate_recommendations._load_prompt_sections", return_value=("system", "{project_context_snapshots}")), \
             patch("output.generate_recommendations.complete", return_value="insights") as complete_mock, \
             patch("output.generate_recommendations._rewrite_insight_source_urls", return_value="insights"), \
             patch("output.generate_recommendations.triage_insights", return_value=[]), \
             patch("output.generate_recommendations.render_triaged_insights_html", return_value="rendered"), \
             patch("output.generate_recommendations._write_insights_file"), \
             patch("output.generate_recommendations._write_insights_html_file"), \
             patch("output.generate_recommendations._store_recommendations"), \
             patch("output.generate_recommendations._send_recommendations_to_telegram_owner"):
            result = run_recommendations(settings)

        complete_mock.assert_called_once()
        self.assertEqual("rendered", result["text"])


if __name__ == "__main__":
    unittest.main()
