import json
import logging
import os
import urllib.request
from html.parser import HTMLParser


LOGGER = logging.getLogger(__name__)
_CREATE_ACCOUNT_URL = "https://api.telegra.ph/createAccount"
_CREATE_PAGE_URL = "https://api.telegra.ph/createPage"


class _HTMLToNodesParser(HTMLParser):
    """Convert HTML into Telegraph Node objects."""

    def __init__(self) -> None:
        super().__init__()
        self.nodes: list[dict | str] = []
        self._stack: list[dict] = []
        self._skip_tags = {"html", "body", "head"}

    def _current(self) -> list | None:
        if self._stack:
            return self._stack[-1]["children"]
        return self.nodes  # type: ignore[return-value]

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._skip_tags:
            return
        tag_map = {"h2": "h3", "h3": "h3", "h4": "h4", "p": "p", "ul": "ul", "li": "li", "b": "b"}
        mapped = tag_map.get(tag)
        if mapped:
            node: dict = {"tag": mapped, "children": []}
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._skip_tags:
            return
        tag_map = {"h2": "h3", "h3": "h3", "h4": "h4", "p": "p", "ul": "ul", "li": "li", "b": "b"}
        if tag not in tag_map:
            return
        if not self._stack:
            return
        node = self._stack.pop()
        # Merge single-string children into plain string for cleanliness
        if len(node["children"]) == 1 and isinstance(node["children"][0], str):
            node["children"] = [node["children"][0]]
        target = self._current()
        target.append(node)  # type: ignore[union-attr]

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        target = self._current()
        if target is not None:
            target.append(text)  # type: ignore[union-attr]


def html_to_telegraph_nodes(html_content: str) -> list[dict]:
    """Convert HTML content to Telegraph Node objects."""
    parser = _HTMLToNodesParser()
    parser.feed(html_content)
    # Filter out bare strings at top level (whitespace artifacts)
    return [node for node in parser.nodes if isinstance(node, dict)]


def _api_post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result


def _get_or_create_access_token() -> str:
    token = os.environ.get("TELEGRAPH_TOKEN", "").strip()
    if token:
        return token
    payload = {
        "short_name": "ResearchAgent",
        "author_name": "Research Agent",
    }
    result = _api_post(_CREATE_ACCOUNT_URL, payload)
    if not result.get("ok"):
        raise RuntimeError(f"Telegraph createAccount failed: {result.get('error')}")
    return str(result["result"]["access_token"])


def publish_article(title: str, html_content: str) -> str:
    """
    Publish HTML content as a Telegraph article. Returns the article URL.

    Raises RuntimeError if the API call fails.
    """
    access_token = _get_or_create_access_token()
    nodes = html_to_telegraph_nodes(html_content)
    if not nodes:
        nodes = [{"tag": "p", "children": ["No content."]}]

    payload = {
        "access_token": access_token,
        "title": title,
        "author_name": "Research Agent",
        "content": nodes,
    }
    result = _api_post(_CREATE_PAGE_URL, payload)
    if not result.get("ok"):
        raise RuntimeError(f"Telegraph createPage failed: {result.get('error')}")
    return str(result["result"]["url"])
