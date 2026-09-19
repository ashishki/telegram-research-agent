"""Narrow, injected GitHub public-repository identity reader for PA-06.

It deliberately does not read environment tokens, write a database, sync
projects, follow redirects, or become a default application dependency.
``GitHubReadAccess`` remains the authority gate immediately before its call.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping
from urllib import error, parse, request


_REPOSITORY_REF = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{7,64}$")
_GITHUB_API_HOST = "api.github.com"


class GitHubReadError(RuntimeError):
    """A non-sensitive public repository read failure."""


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GitHubReadError("redirect_rejected")


class ReadOnlyGitHubContextProvider:
    """Read a repository's current GitHub commit identity through one endpoint."""

    def __init__(self, *, timeout_seconds: float = 15.0, max_response_bytes: int = 256_000) -> None:
        if not 1.0 <= float(timeout_seconds) <= 30.0:
            raise ValueError("github read timeout is out of range")
        if not 4_096 <= int(max_response_bytes) <= 1_000_000:
            raise ValueError("github read response limit is out of range")
        self._timeout_seconds = float(timeout_seconds)
        self._max_response_bytes = int(max_response_bytes)

    def read_repository_context(self, repository_ref: str) -> Mapping[str, Any]:
        if not _REPOSITORY_REF.fullmatch(repository_ref):
            raise GitHubReadError("invalid_repository_ref")
        endpoint = f"https://{_GITHUB_API_HOST}/repos/{repository_ref}/commits/HEAD"
        opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())
        req = request.Request(
            endpoint,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "telegram-research-agent-pa06-readonly/1",
            },
        )
        try:
            response = opener.open(req, timeout=self._timeout_seconds)
        except GitHubReadError:
            raise
        except error.HTTPError as exc:
            raise GitHubReadError("http_status") from exc
        except (error.URLError, OSError, TimeoutError) as exc:
            raise GitHubReadError("transport") from exc
        with response:
            final = parse.urlparse(str(response.geturl() or endpoint))
            expected_path = f"/repos/{repository_ref}/commits/"
            if final.scheme != "https" or final.hostname != _GITHUB_API_HOST or not final.path.startswith(expected_path):
                raise GitHubReadError("redirect_rejected")
            content_type = str(response.headers.get_content_type() or "").casefold()
            if content_type != "application/json":
                raise GitHubReadError("content_type")
            body = response.read(self._max_response_bytes + 1)
            if len(body) > self._max_response_bytes:
                raise GitHubReadError("response_too_large")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubReadError("payload") from exc
        if not isinstance(payload, Mapping):
            raise GitHubReadError("payload")
        commit_sha = str(payload.get("sha") or "").casefold()
        api_url = str(payload.get("url") or "")
        expected_api_prefix = f"https://{_GITHUB_API_HOST}/repos/{repository_ref}/commits/"
        if not _COMMIT_SHA.fullmatch(commit_sha) or api_url != expected_api_prefix + commit_sha:
            raise GitHubReadError("repository_identity_mismatch")
        # Commit messages and arbitrary repository metadata are external,
        # untrusted content. PA-06 needs identity/ref freshness, not a second
        # text channel that could carry instructions into the planner.
        return {
            "repository_ref": repository_ref,
            "commit_sha": commit_sha,
            "ref": "HEAD",
            "summary": "",
        }
