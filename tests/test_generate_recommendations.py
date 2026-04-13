import sys
import types
import unittest


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

from output.generate_recommendations import _render_insights_fragment, _rewrite_insight_source_urls  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
