#!/usr/bin/env python3
"""Generate brief artifacts from the local archive for the design/eval loop.

Reads the operator's archive read-only (no writes, no migrations), builds a
deterministic BriefDocument, optionally drafts editorial stories with the
OpenCode Go model (validated by BriefEditorial.from_dict, retried on failure),
then writes standard + designed HTML/PDF/Markdown and a Telegram dialogue JSON.

Provider egress is off unless ``--allow-provider-egress`` is passed; when it is
on, the selected evidence (not the raw corpus) is sent to the model for the
editorial draft. All artifacts go to a git-ignored directory.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import glob
import re
import shutil
import subprocess
import sys
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from config.settings import load_settings  # noqa: E402
from prm.application import PersonalResearchAssistant, _brief_request_from_archive_payload  # noqa: E402
from prm.brief_editorial import BriefEditorial  # noqa: E402
from prm.briefs import build_brief_document, render_brief_document  # noqa: E402
from prm import report_exports  # noqa: E402
from prm.contracts import OperatorRequest  # noqa: E402


def _load_eval_module():
    path = Path(__file__).resolve().parent / "prm_product_ux_eval.py"
    spec = importlib.util.spec_from_file_location("prm_product_ux_eval_for_studio", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_EVAL = _load_eval_module()

EDITORIAL_PROMPT = """You are the editor of one private weekly brief in Russian.
You receive a JSON payload with a topic, period and a list of selected evidence
items ({evidence_ref, title, summary}). Write at most 5 editorial stories.
Return compact JSON only with exactly this shape:
{"stories":[{"title","summary","explanation","plain_explanation","why_selected","next_step","caveat","anchors":[{"evidence_ref","quote"}]}],"omitted_refs":[]}
Hard rules:
- every evidence_ref must appear exactly once, either as a story anchor or in
  omitted_refs; anchors use the real evidence_ref values;
- each quote MUST be a verbatim substring (at least 16 characters) of that
  evidence item's summary; never paraphrase a quote;
- never write a digit in title/summary/explanation/plain_explanation unless
  that exact number appears in one of your chosen quotes; the safest rule is to
  avoid digits in your own prose entirely and keep numbers only inside quotes;
- a title must describe an event, never start with '@';
- keep every story bound to its sources; no new facts, deadlines or claims.
Fields: title (<=140), summary (<=300), explanation (<=900),
why_selected (<=300), plain_explanation (<=500, may be empty),
next_step/caveat (<=300, may be empty)."""


def _call_model(
    *,
    prompt: str,
    payload: Mapping[str, Any],
    model: str,
    timeout: int,
    max_output_tokens: int,
) -> dict[str, Any]:
    api_key = _EVAL._opencode_api_key()
    if not api_key:
        return {"status": "provider_error", "error": "missing_api_key"}
    base_url = (
        os.environ.get("OPENCODE_GO_BASE_URL", _EVAL.DEFAULT_OPENCODE_BASE_URL)
        or _EVAL.DEFAULT_OPENCODE_BASE_URL
    ).rstrip("/")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
        ],
        "temperature": 0,
        "max_tokens": max(512, max_output_tokens),
        "response_format": {"type": "json_object"},
    }
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "personal-assistant-brief-studio/1.0",
            "x-opencode-session": "personal-assistant-brief-studio",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=max(10, timeout)) as response:  # nosec B310
            result = json.loads(response.read())
    except HTTPError as error:
        return {"status": "provider_error", "error": f"http_error_{error.code}"}
    except URLError as error:
        return {"status": "provider_error", "error": f"url_error_{type(error.reason).__name__}"}
    except Exception as error:  # pragma: no cover - network dependent
        return {"status": "provider_error", "error": type(error).__name__}
    text = _EVAL._chat_completion_text(result)
    if not text:
        return {"status": "invalid_response", "error": "missing_message_content"}
    try:
        return {"status": "ok", "json": _parse_model_json(text)}
    except Exception as error:
        return {
            "status": "invalid_response",
            "error": f"invalid_json:{type(error).__name__}",
            "raw_head": text.strip()[:180],
        }


def _parse_model_json(text: str) -> Any:
    """Tolerate code fences and literal newlines inside string values."""

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9]*\s*", "", cleaned)
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    candidates = [cleaned, cleaned.replace("\r", " ").replace("\n", " ")]
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            pass
        match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                continue
    raise ValueError("unparsable_model_json")


def _evidence_payload(document: Any) -> dict[str, Any]:
    return {
        "topic": document.topic,
        "period": document.window.to_dict(),
        "evidence": [
            {
                "evidence_ref": item.evidence_ref,
                "title": item.title,
                "summary": item.summary,
            }
            for item in document.evidence
        ],
    }


def draft_editorial(
    document: Any,
    *,
    model: str,
    retries: int,
    timeout: int,
    max_output_tokens: int,
) -> tuple[BriefEditorial | None, dict[str, Any]]:
    payload = _evidence_payload(document)
    last_error = "not_attempted"
    feedback = ""
    for attempt in range(1, max(1, retries) + 1):
        result = _call_model(
            prompt=EDITORIAL_PROMPT + feedback,
            payload=payload,
            model=model,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
        )
        if result.get("status") != "ok":
            last_error = str(result.get("error"))
            feedback = (
                "\n\nYour previous reply could not be parsed as JSON. Return one "
                "compact JSON object only, with no literal newlines inside strings."
            )
            continue
        try:
            editorial = BriefEditorial.from_dict(result["json"], document.evidence)
        except ValueError as error:
            last_error = f"validation:{error}"
            feedback = (
                f"\n\nYour previous reply failed validation: {error}. Fix exactly "
                "this: any number in a title/summary/explanation must also appear "
                "inside one of your anchor quotes (copy the quote verbatim), every "
                "evidence_ref must be used or omitted exactly once, and quotes must "
                "be verbatim substrings of that item's summary of length >= 16."
            )
            continue
        return editorial, {"status": "drafted", "attempts": attempt}
    return None, {"status": "failed", "error": last_error[:200]}


def _find_chrome() -> str | None:
    explicit = os.environ.get("ASSISTANT_CHROME", "").strip()
    if explicit and Path(explicit).is_file():
        return explicit
    candidates = sorted(glob.glob(str(Path.home() / ".cache/ms-playwright/chromium-*/chrome-linux64/chrome")))
    return candidates[-1] if candidates else shutil.which("chromium") or shutil.which("google-chrome")


def _render_pdf_chrome(html_path: Path, output_path: Path, *, timeout: int = 90) -> Path:
    """Print the designed HTML to PDF with headless Chrome (better CSS support)."""

    binary = _find_chrome()
    if not binary:
        raise RuntimeError("no chrome/chromium binary found")
    command = [
        binary,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        "--virtual-time-budget=4000",
        f"--print-to-pdf={output_path}",
        html_path.resolve().as_uri(),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if not output_path.is_file():
        raise RuntimeError(f"chrome print-to-pdf failed: {completed.stderr.strip()[:200]}")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", default="AI и research за неделю")
    parser.add_argument("--chat-id", default="local-brief-studio")
    parser.add_argument("--out-dir", type=Path, default=PROJECT_ROOT / ".playbook-artifacts/brief_studio")
    parser.add_argument("--model", default=os.environ.get("PRM_BRIEF_EDITORIAL_MODEL", "mimo-v2.6-pro"))
    parser.add_argument("--judge-base-url", default=os.environ.get("OPENCODE_GO_BASE_URL", _EVAL.DEFAULT_OPENCODE_BASE_URL))
    parser.add_argument("--judge-api-key-file", default=os.environ.get("OPENCODE_API_KEY_FILE", ""))
    parser.add_argument("--allow-provider-egress", action="store_true")
    parser.add_argument("--no-editorial", action="store_true")
    parser.add_argument("--editorial-retries", type=int, default=3)
    parser.add_argument("--provider-timeout", type=int, default=150)
    parser.add_argument("--max-output-tokens", type=int, default=6000)
    parser.add_argument("--chrome-pdf", action="store_true", help="Also render the designed HTML to PDF with headless Chrome")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    os.environ["OPENCODE_GO_BASE_URL"] = str(args.judge_base_url)
    if args.judge_api_key_file:
        os.environ["OPENCODE_API_KEY_FILE"] = str(args.judge_api_key_file)

    assistant = PersonalResearchAssistant(settings=load_settings())
    request = OperatorRequest(query=args.question, mode="brief", chat_id=args.chat_id)
    result = assistant.answer(request)
    source_payload = result.payload or {}
    if not source_payload.get("brief_document"):
        print(json.dumps({"status": "no_brief", "reason": result.status}, ensure_ascii=False))
        return 1
    brief_request = _brief_request_from_archive_payload(request=request, payload=source_payload, topic=args.question)
    document = build_brief_document(brief_request)

    editorial_meta: dict[str, Any] = {"status": "skipped"}
    if not args.no_editorial and args.allow_provider_egress and _EVAL._opencode_api_key():
        editorial, editorial_meta = draft_editorial(
            document,
            model=args.model,
            retries=args.editorial_retries,
            timeout=args.provider_timeout,
            max_output_tokens=args.max_output_tokens,
        )
        if editorial is not None:
            document = build_brief_document(replace(brief_request, editorial=editorial))
    elif not args.no_editorial and not args.allow_provider_egress:
        editorial_meta = {"status": "skipped_no_egress"}

    out = args.out_dir
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for name, artifact in (
        ("brief.html", report_exports.render_html(document)),
        ("brief.md", report_exports.render_markdown(document)),
        ("brief.pdf", report_exports.render_pdf(document)),
        ("brief_designed.html", report_exports.render_designed_html(document)),
        ("brief_designed.pdf", report_exports.render_designed_pdf(document)),
    ):
        body = artifact.body if isinstance(artifact.body, bytes) else artifact.body.encode("utf-8")
        (out / name).write_bytes(body)
        written[name] = str(out / name)
    if args.chrome_pdf:
        try:
            chrome_pdf = out / "brief_designed_chrome.pdf"
            _render_pdf_chrome(out / "brief_designed.html", chrome_pdf)
            written["brief_designed_chrome.pdf"] = str(chrome_pdf)
        except Exception as error:  # pragma: no cover - environment dependent
            written["brief_designed_chrome.pdf"] = f"failed:{type(error).__name__}"
    telegram_text = render_brief_document(document, view="telegram")
    (out / "telegram.txt").write_text(telegram_text, encoding="utf-8")
    dialogue = {
        "title": "Личный ассистент",
        "turns": [
            {"role": "user", "text": args.question},
            {"role": "assistant", "text": telegram_text, "format": "html",
             "buttons": ["Показать полный бриф", "Объясни пункт 2", "Сделай короче"]},
        ],
    }
    (out / "dialogue.json").write_text(json.dumps(dialogue, ensure_ascii=False), encoding="utf-8")
    manifest = {
        "status": "ok",
        "question": args.question,
        "brief_id": document.brief_id,
        "version": document.version,
        "items": len(document.items),
        "evidence": len(document.evidence),
        "editorial": editorial_meta,
        "editorial_stories": len(document.editorial.stories) if document.editorial else 0,
        "artifacts": written,
        "dialogue": str(out / "dialogue.json"),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
