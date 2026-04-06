import json
import logging
import os
import urllib.request
from urllib.error import URLError
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
        self._skip_tags = {"html", "body", "head", "style", "script"}
        self._skip_stack: list[str] = []

    def _current(self) -> list | None:
        if self._stack:
            return self._stack[-1]["children"]
        return self.nodes  # type: ignore[return-value]

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._skip_tags:
            self._skip_stack.append(tag)
            return
        if self._skip_stack:
            return
        tag_map = {
            "h1": "h3",
            "h2": "h3",
            "h3": "h3",
            "h4": "h4",
            "p": "p",
            "ul": "ul",
            "li": "li",
            "b": "b",
            "strong": "b",
            "a": "a",
        }
        mapped = tag_map.get(tag)
        if mapped:
            node: dict = {"tag": mapped, "children": []}
            if mapped == "a":
                href = dict(attrs).get("href")
                if href:
                    node["attrs"] = {"href": href}
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._skip_tags:
            if self._skip_stack and self._skip_stack[-1] == tag:
                self._skip_stack.pop()
            return
        if self._skip_stack:
            return
        tag_map = {
            "h1": "h3",
            "h2": "h3",
            "h3": "h3",
            "h4": "h4",
            "p": "p",
            "ul": "ul",
            "li": "li",
            "b": "b",
            "strong": "b",
            "a": "a",
        }
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
        if self._skip_stack:
            return
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
    nodes: list[dict] = []
    text_buffer: list[str] = []

    def flush_text() -> None:
        text = " ".join(part.strip() for part in text_buffer if part.strip()).strip()
        if text:
            nodes.append({"tag": "p", "children": [text]})
        text_buffer.clear()

    for node in parser.nodes:
        if isinstance(node, dict):
            flush_text()
            nodes.append(node)
            continue
        text_buffer.append(node)
    flush_text()
    return nodes


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
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            result = _api_post(_CREATE_PAGE_URL, payload)
            if not result.get("ok"):
                raise RuntimeError(f"Telegraph createPage failed: {result.get('error')}")
            return str(result["result"]["url"])
        except (RuntimeError, OSError, URLError) as exc:
            last_error = exc
            LOGGER.warning("Telegraph publish failed attempt=%d title=%s", attempt + 1, title, exc_info=True)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Telegraph publish failed for unknown reason")
