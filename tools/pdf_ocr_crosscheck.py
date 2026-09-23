#!/usr/bin/env python3
"""Optional external SotaOCR cross-check for a generated PDF (PA OCR layer).

Uploads one PDF to the operator-owned SotaOCR account, polls the job, fetches
the OCR text and checks that expected substrings survive rendering. This is the
only judge layer that sends a document to a third party, so it is fail-closed
and requires both ``--allow-provider-egress`` and an explicit
``--i-understand-third-party-upload`` acknowledgement plus a SotaOCR key.

The OCR text is never written to the public report: only its length, SHA-256
and the missing-expected list. Use it to catch dropped/overlapping glyphs and
copyability problems the vision judge can miss.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _requests():
    """Import requests lazily so the module/tests load without it installed."""

    import requests

    return requests
SCHEMA_VERSION = "assistant_pdf_ocr_crosscheck.v1"
DEFAULT_BASE_URL = os.environ.get("SOTAOCR_BASE_URL", "https://sotaocr.com")
DEFAULT_OUTPUT = PROJECT_ROOT / ".playbook-artifacts/ocr/assistant_pdf_ocr_crosscheck_latest.json"
DEFAULT_DATASET_OUTPUT = PROJECT_ROOT / ".playbook-artifacts/ocr/assistant_pdf_ocr_crosscheck_dataset_latest.ndjson"


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_api_key(explicit_file: str) -> str:
    if explicit_file and Path(explicit_file).is_file():
        key = Path(explicit_file).read_text(encoding="utf-8").strip()
        if key:
            return key
    return os.environ.get("SOTAOCR_API_KEY", "").strip()


def extract_job_id(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    for key in ("job_id", "jobId", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    job = payload.get("job")
    if isinstance(job, Mapping):
        return extract_job_id(job)
    return None


def extract_status(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        return ""
    for key in ("status", "state"):
        value = payload.get(key)
        if isinstance(value, str):
            return value.strip().casefold()
    job = payload.get("job")
    if isinstance(job, Mapping):
        return extract_status(job)
    return ""


def compare_expected(ocr_text: str, expected: Sequence[str]) -> tuple[str, ...]:
    folded = ocr_text.casefold()
    return tuple(item for item in expected if str(item).strip() and str(item).casefold() not in folded)


def _submit(*, base_url: str, headers: dict[str, str], pdf_path: Path, data: dict[str, str], timeout: int) -> dict[str, Any]:
    with pdf_path.open("rb") as stream:
        requests = _requests()
        response = requests.post(
            f"{base_url}/v1/extract",
            headers=headers,
            data=data,
            files={"file": (pdf_path.name, stream, "application/pdf")},
            timeout=timeout,
        )
    response.raise_for_status()
    return response.json()


def _poll(*, base_url: str, headers: dict[str, str], job_id: str, poll_interval: float, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        requests = _requests()
        response = requests.get(f"{base_url}/v1/jobs/{job_id}", headers=headers, timeout=min(30, timeout))
        response.raise_for_status()
        payload = response.json()
        state = extract_status(payload)
        if state == "completed":
            return payload
        if state in {"failed", "cancelled", "error"}:
            raise RuntimeError(f"SotaOCR job ended with status {state}")
        if time.monotonic() > deadline:
            raise TimeoutError("SotaOCR job did not complete before the timeout")
        time.sleep(max(1.0, poll_interval))


def run_crosscheck(
    *,
    pdf_path: Path,
    expected: Sequence[str],
    api_key: str,
    base_url: str,
    model_profile: str | None,
    page_ranges: str | None,
    result_format: str,
    poll_interval: float,
    timeout: int,
    output_path: Path,
    dataset_output_path: Path,
    third_party_upload: bool,
    provider_egress: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    pdf_bytes = pdf_path.read_bytes()
    pdf_sha = sha256_bytes(pdf_bytes)
    dataset_output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_output_path.write_text(
        json.dumps(
            {
                "pdf": pdf_path.name,
                "pdf_sha256": pdf_sha,
                "pdf_bytes": len(pdf_bytes),
                "expected": list(expected),
                "result_format": result_format,
                "model_profile": model_profile,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    base = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "advisory_only": True,
        "provider": "sotaocr",
        "base_url": base_url,
        "pdf": pdf_path.name,
        "pdf_sha256": pdf_sha,
        "pdf_bytes": len(pdf_bytes),
        "result_format": result_format,
        "model_profile": model_profile,
        "expected_count": len([item for item in expected if str(item).strip()]),
        "privacy": {
            "document_uploaded_to_third_party": False,
            "ocr_text_committed": False,
        },
    }
    if not provider_egress or not third_party_upload:
        report = {
            **base,
            "status": "skipped_fail_closed",
            "judge_status": "no_model_configured",
            "reason": "provider egress and explicit third-party upload acknowledgement are required",
        }
        write_json(output_path, report)
        return report
    if not api_key:
        report = {
            **base,
            "status": "skipped_fail_closed",
            "judge_status": "no_provider_credentials",
            "reason": "SOTAOCR_API_KEY was not present",
        }
        write_json(output_path, report)
        return report

    requests = _requests()
    headers = {"Authorization": f"Bearer {api_key}"}
    data: dict[str, str] = {}
    if model_profile:
        data["model_profile"] = model_profile
    if page_ranges:
        import json as _json

        ranges = []
        for chunk in page_ranges.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "-" in chunk:
                start, end = chunk.split("-", 1)
                ranges.append({"start": int(start), "end": int(end)})
            else:
                ranges.append({"start": int(chunk), "end": int(chunk)})
        data["page_ranges"] = _json.dumps(ranges, separators=(",", ":"))
    status = "failed_closed"
    judge_status = "provider_failed"
    reason = "unknown"
    ocr_text = ""
    missing: tuple[str, ...] = ()
    try:
        submitted = _submit(base_url=base_url, headers=headers, pdf_path=pdf_path, data=data, timeout=timeout)
        job_id = extract_job_id(submitted)
        if not job_id:
            raise RuntimeError("SotaOCR did not return a job id")
        _poll(base_url=base_url, headers=headers, job_id=job_id, poll_interval=poll_interval, timeout=timeout)
        requests = _requests()
        response = requests.get(
            f"{base_url}/v1/jobs/{job_id}/result",
            headers=headers,
            params={"format": result_format},
            timeout=timeout,
        )
        response.raise_for_status()
        ocr_text = response.content.decode("utf-8", errors="replace")
        missing = compare_expected(ocr_text, expected)
        if not ocr_text.strip():
            status, judge_status, reason = "failed_closed", "executed", "OCR returned no text layer"
        elif missing:
            status, judge_status, reason = "failed_closed", "executed", "expected text missing from OCR"
        else:
            status, judge_status, reason = "pass", "executed", "OCR reproduced all expected text"
    except requests.HTTPError as error:
        reason = f"http_error_{error.response.status_code if error.response is not None else 'unknown'}"
    except requests.RequestException as error:
        reason = f"request_error_{type(error).__name__}"
    except (RuntimeError, TimeoutError) as error:
        reason = str(error)[:160]

    report = {
        **base,
        "status": status,
        "judge_status": judge_status,
        "reason": reason,
        "privacy": {
            "document_uploaded_to_third_party": True,
            "ocr_text_committed": False,
        },
        "metrics": {
            "ocr_text_chars": len(ocr_text),
            "ocr_text_sha256": sha256_bytes(ocr_text.encode("utf-8")) if ocr_text else None,
            "missing_expected": list(missing),
            "missing_count": len(missing),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        },
    }
    write_json(output_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--expect", action="append", default=[])
    parser.add_argument("--api-key-file", default=os.environ.get("SOTAOCR_API_KEY_FILE", ""))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model-profile", default="")
    parser.add_argument("--page-ranges", default="")
    parser.add_argument("--format", choices=("json", "markdown", "html", "docx"), default="markdown")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--allow-provider-egress", action="store_true")
    parser.add_argument("--i-understand-third-party-upload", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dataset-output", type=Path, default=DEFAULT_DATASET_OUTPUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.pdf.is_file():
        print(json.dumps({"status": "no_input", "reason": f"missing {args.pdf}"}, ensure_ascii=False))
        return 2
    report = run_crosscheck(
        pdf_path=args.pdf,
        expected=args.expect,
        api_key=load_api_key(args.api_key_file),
        base_url=args.base_url.rstrip("/"),
        model_profile=args.model_profile or None,
        page_ranges=args.page_ranges or None,
        result_format=args.format,
        poll_interval=args.poll_interval,
        timeout=args.timeout,
        output_path=args.output,
        dataset_output_path=args.dataset_output,
        third_party_upload=bool(args.i_understand_third_party_upload),
        provider_egress=bool(args.allow_provider_egress),
    )
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "reason": report.get("reason"),
                "metrics": report.get("metrics"),
                "output": str(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
