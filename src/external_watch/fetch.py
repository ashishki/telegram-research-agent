"""Safe HTTP boundary for allowlisted public UTD shadow sources."""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Mapping
from urllib import error, parse, request

ALLOWED_HOSTS = frozenset({"calendar.utdallas.edu", "isso.utdallas.edu", "basicneeds.utdallas.edu"})
MAX_RESPONSE_BYTES = 1_000_000
ALLOWED_CONTENT_TYPES = frozenset({"application/json", "text/html"})
USER_AGENT = "telegram-research-agent-utd-shadow/0.1"


class FetchError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    content_type: str
    headers: Mapping[str, str]
    body: bytes


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FetchError("redirect", f"redirect rejected: {newurl}", status=code)


def validate_url(url: str) -> parse.ParseResult:
    parsed = parse.urlparse(url)
    if parsed.scheme != "https":
        raise FetchError("scheme", "only https URLs are allowed")
    if parsed.username or parsed.password:
        raise FetchError("userinfo", "URL userinfo is forbidden")
    if parsed.port not in (None, 443):
        raise FetchError("port", "non-default ports are forbidden")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise FetchError("host", f"host not allowlisted: {host}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise FetchError("ip_literal", "IP-literal URLs are forbidden")
    return parsed


def _reject_private_resolution(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError("dns", f"DNS resolution failed for {host}") from exc
    if not infos:
        raise FetchError("dns", f"no addresses resolved for {host}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise FetchError("ssrf", f"unsafe address resolved for {host}")


def safe_fetch(url: str, *, timeout: float = 20.0, max_bytes: int = MAX_RESPONSE_BYTES) -> FetchResult:
    parsed = validate_url(url)
    _reject_private_resolution(parsed.hostname or "")
    opener = request.build_opener(_NoRedirect())
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/html;q=0.9"})
    try:
        response = opener.open(req, timeout=timeout)
    except FetchError:
        raise
    except error.HTTPError as exc:
        code = "rate_limited" if exc.code == 429 else "http"
        raise FetchError(code, f"HTTP {exc.code}", status=exc.code) from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise FetchError("transport", str(exc)) from exc
    with response:
        final = parse.urlparse(response.geturl())
        if (final.hostname or "").lower() != (parsed.hostname or "").lower():
            raise FetchError("redirect", "cross-host redirect rejected", status=getattr(response, "status", None))
        content_type = response.headers.get_content_type()
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise FetchError("content_type", f"unsupported content type: {content_type}")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise FetchError("size", f"response exceeds {max_bytes} bytes")
        headers = {key.lower(): value for key, value in response.headers.items() if key.lower() in {"etag", "last-modified", "cache-control", "content-type", "date", "expires"}}
        return FetchResult(url=url, status=int(getattr(response, "status", 200)), content_type=content_type, headers=headers, body=body)
