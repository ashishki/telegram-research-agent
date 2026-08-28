from email.message import Message
from io import BytesIO
from urllib import error

import pytest

from external_watch import fetch as fetch_module
from external_watch.fetch import FetchError, safe_fetch, validate_url


@pytest.mark.parametrize("url", [
    "http://calendar.utdallas.edu/api/2/events",
    "https://evil.example/api/2/events",
    "https://127.0.0.1/",
    "https://user:pass@calendar.utdallas.edu/",
    "https://calendar.utdallas.edu:444/api/2/events",
])
def test_url_boundary_rejects_unsafe_urls(url):
    with pytest.raises(FetchError):
        validate_url(url)


def test_url_boundary_accepts_only_three_public_hosts():
    for url in (
        "https://calendar.utdallas.edu/api/2/events",
        "https://isso.utdallas.edu/",
        "https://basicneeds.utdallas.edu/resource-hub/",
    ):
        assert validate_url(url).hostname


class FakeResponse:
    def __init__(self, *, url, body=b"{}", ctype="application/json", status=200):
        self._url = url
        self._body = body
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = ctype
        self._stream = BytesIO(body)
    def geturl(self): return self._url
    def read(self, n=-1): return self._stream.read(n)
    def __enter__(self): return self
    def __exit__(self, *args): return False


class FakeOpener:
    def __init__(self, result): self.result = result
    def open(self, req, timeout=0):
        if isinstance(self.result, Exception): raise self.result
        return self.result


def _patch_transport(monkeypatch, result):
    monkeypatch.setattr(fetch_module, "_reject_private_resolution", lambda host: None)
    monkeypatch.setattr(fetch_module.request, "build_opener", lambda *handlers: FakeOpener(result))


def test_cross_host_redirect_is_rejected(monkeypatch):
    _patch_transport(monkeypatch, FakeResponse(url="https://evil.example/"))
    with pytest.raises(FetchError, match="cross-host") as exc:
        safe_fetch("https://calendar.utdallas.edu/api/2/events")
    assert exc.value.code == "redirect"


def test_unsupported_content_type_is_rejected(monkeypatch):
    _patch_transport(monkeypatch, FakeResponse(url="https://calendar.utdallas.edu/api/2/events", ctype="application/octet-stream"))
    with pytest.raises(FetchError) as exc:
        safe_fetch("https://calendar.utdallas.edu/api/2/events")
    assert exc.value.code == "content_type"


def test_oversized_response_is_rejected(monkeypatch):
    _patch_transport(monkeypatch, FakeResponse(url="https://calendar.utdallas.edu/api/2/events", body=b"x" * 12))
    with pytest.raises(FetchError) as exc:
        safe_fetch("https://calendar.utdallas.edu/api/2/events", max_bytes=10)
    assert exc.value.code == "size"


def test_429_is_source_health_error_not_data(monkeypatch):
    http_error = error.HTTPError("https://calendar.utdallas.edu/api/2/events", 429, "Too Many Requests", hdrs=None, fp=None)
    _patch_transport(monkeypatch, http_error)
    with pytest.raises(FetchError) as exc:
        safe_fetch("https://calendar.utdallas.edu/api/2/events")
    assert exc.value.code == "rate_limited"
    assert exc.value.status == 429
