#!/usr/bin/env python3
"""Independent, read-only deep review of a git range via the OpenCode Go model.

This replaces the Codex reviewer role for this programme. It reads only the git
range, sends the diff to the model, and writes a findings report. It never edits
files, never runs the application, and records the reviewed SHA and model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = os.environ.get("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1")
DEFAULT_MODEL = os.environ.get("MIMO_REVIEW_MODEL", "mimo-v2.6-pro")
MAX_DIFF_CHARS = 900_000

PROMPT = """You are a strict, independent code reviewer for a private personal-assistant
project. Review ONLY the supplied git diff. Report real defects, not style nits.

Priorities: safety/fail-closed correctness (a denial or unknown must never become an
allow, an unknown outcome must never be retried blindly, a grant for one provider/purpose
must never authorize another), input validation and bounds, resource leaks, race
conditions, idempotency, and privacy (no private text or secret in reports/logs).
The project rules: no live network/account/DB in these modules; deterministic synthetic
tests; one-use version-bound confirmation; conflicting deadlines are surfaced not merged;
unknown pricing is never zero; media allowlists reject unknown types.

Return compact JSON only:
{"verdict":"SHIP_OK|FIX_P1_FIRST|STOP_SHIP",
 "findings":[{"severity":"P0|P1|P2","title":"...","file":"path:line",
              "issue":"1-3 sentences","fix":"1-3 sentences","confidence":"high|medium|low"}],
 "not_verified":["..."],
 "summary":"one paragraph"}
Rank P0 first. If there are no P0/P1, say so explicitly."""


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), *args],
        capture_output=True, text=True, check=True,
    )
    return completed.stdout


def _api_key(explicit_file: str) -> str:
    if explicit_file and Path(explicit_file).is_file():
        return Path(explicit_file).read_text(encoding="utf-8").strip()
    value = os.environ.get("OPENCODE_API_KEY", "").strip()
    if value:
        return value
    key_file = os.environ.get("OPENCODE_API_KEY_FILE", "").strip()
    if key_file and Path(key_file).is_file():
        return Path(key_file).read_text(encoding="utf-8").strip()
    return ""


def _call_model(*, api_key: str, base_url: str, model: str, prompt: str, timeout: int) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 12000,
        "response_format": {"type": "json_object"},
    }
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "personal-assistant-review/1.0",
            "x-opencode-session": "personal-assistant-review",
        },
        method="POST",
    )
    with urlopen(request, timeout=max(30, timeout)) as response:  # nosec B310
        return json.loads(response.read())


def _response_text(payload: Mapping[str, Any]) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
    content = message.get("content") if isinstance(message, Mapping) else None
    return content if isinstance(content, str) else None


def _parse_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9]*\s*", "", cleaned)
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    for candidate in (cleaned, cleaned.replace("\r", " ").replace("\n", " ")):
        try:
            return json.loads(candidate)
        except Exception:
            match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    continue
    raise ValueError("unparsable_model_json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="git revision to diff from")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--key-file", default=os.environ.get("OPENCODE_API_KEY_FILE", ""))
    parser.add_argument("--allow-provider-egress", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    head_sha = _git("rev-parse", args.head).strip()
    base_sha = _git("rev-parse", args.base).strip()
    log = _git("log", "--oneline", f"{base_sha}..{head_sha}")
    diff = _git("diff", f"{base_sha}..{head_sha}")
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n[... diff truncated ...]\n"
    if not args.allow_provider_egress:
        report = {"status": "skipped_fail_closed", "reason": "provider egress not allowed"}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))
        return 1
    api_key = _api_key(args.key_file)
    if not api_key:
        report = {"status": "no_provider_credentials", "reason": "OPENCODE_API_KEY not present"}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))
        return 1
    from urllib.parse import urlparse

    parsed = urlparse(args.base_url)
    if parsed.scheme != "https" or (parsed.hostname or "") not in {"opencode.ai", "api.opencode.ai"}:
        print(json.dumps({"status": "invalid_base_url"}))
        return 1
    user = f"Reviewed range: {base_sha}..{head_sha}\nCommits:\n{log}\n\nDiff:\n{diff}"
    try:
        payload = _call_model(
            api_key=api_key, base_url=args.base_url, model=args.model,
            prompt=PROMPT + "\n\n" + user, timeout=args.timeout,
        )
    except HTTPError as error:
        print(json.dumps({"status": "provider_error", "error": f"http_{error.code}"}))
        return 1
    except URLError as error:
        print(json.dumps({"status": "provider_error", "error": f"url_{type(error.reason).__name__}"}))
        return 1
    text = _response_text(payload)
    if not text:
        print(json.dumps({"status": "invalid_response"}))
        return 1
    findings = _parse_json(text)
    report = {
        "status": "reviewed",
        "reviewer_model": args.model,
        "reviewer_role": "deep_review",
        "base_sha": base_sha,
        "head_sha": head_sha,
        "diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
        "diff_chars": len(diff),
        "findings": findings,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "reviewed", "verdict": findings.get("verdict"),
        "findings": len(findings.get("findings") or []), "out": str(args.out),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
