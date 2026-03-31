import json
import unittest
from unittest.mock import patch


from delivery.telegraph import html_to_telegraph_nodes, publish_article


class _FakeResponse:
    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestTelegraph(unittest.TestCase):
    def test_html_to_telegraph_nodes_h2(self):
        nodes = html_to_telegraph_nodes("<h2>Title</h2>")
        self.assertEqual(nodes, [{"tag": "h3", "children": ["Title"]}])

    def test_html_to_telegraph_nodes_paragraph(self):
        nodes = html_to_telegraph_nodes("<p>Hello world</p>")
        self.assertEqual(nodes, [{"tag": "p", "children": ["Hello world"]}])

    def test_html_to_telegraph_nodes_list(self):
        nodes = html_to_telegraph_nodes("<ul><li>item a</li><li>item b</li></ul>")
        self.assertEqual(
            nodes,
            [
                {
                    "tag": "ul",
                    "children": [
                        {"tag": "li", "children": ["item a"]},
                        {"tag": "li", "children": ["item b"]},
                    ],
                }
            ],
        )

    def test_publish_article_returns_url(self):
        responses = [
            _FakeResponse({"ok": True, "result": {"access_token": "token-123"}}),
            _FakeResponse({"ok": True, "result": {"url": "https://telegra.ph/test-page"}}),
        ]
        with patch("urllib.request.urlopen", side_effect=responses):
            with patch.dict("os.environ", {}, clear=False):
                # Ensure no TELEGRAPH_TOKEN set so createAccount is called
                import os
                os.environ.pop("TELEGRAPH_TOKEN", None)
                url = publish_article("Weekly Review", "<p>Hello world</p>")
        self.assertTrue(url.startswith("https://telegra.ph/"))

    def test_publish_article_uses_env_token_skips_create_account(self):
        responses = [
            _FakeResponse({"ok": True, "result": {"url": "https://telegra.ph/test-page-2"}}),
        ]
        with patch("urllib.request.urlopen", side_effect=responses):
            with patch.dict("os.environ", {"TELEGRAPH_TOKEN": "my-token"}):
                url = publish_article("Weekly Review", "<p>content</p>")
        self.assertTrue(url.startswith("https://telegra.ph/"))

    def test_publish_article_raises_on_api_error(self):
        with patch("urllib.request.urlopen", return_value=_FakeResponse({"ok": False, "error": "API_ERROR"})):
            with patch.dict("os.environ", {}, clear=False):
                import os
                os.environ.pop("TELEGRAPH_TOKEN", None)
                with self.assertRaises(RuntimeError):
                    publish_article("Weekly Review", "<p>Hello world</p>")


if __name__ == "__main__":
    unittest.main()
