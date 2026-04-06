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

from output.generate_recommendations import _render_insights_fragment  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
