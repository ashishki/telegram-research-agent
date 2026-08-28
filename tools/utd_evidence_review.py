#!/usr/bin/env python3
"""Offline UTD evidence and relevance review helper.

No network access, provider calls, Telegram delivery, timers or production DB writes.
It validates sanitized fixture envelopes and generates a human-review worksheet
for the external-watch evaluation manifest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

ALLOWED_FIXTURE_KINDS = {"localist_json", "html_excerpt"}
ALLOWED_SOURCES = {"calendar", "isso", "basic_needs"}
ALLOWED_OUTCOMES = {"notify", "ignore", "ambiguous"}


def validate_fixture(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != "utd_source_fixture.v1":
        errors.append("schema_version must be utd_source_fixture.v1")
    source = payload.get("source")
    if source not in ALLOWED_SOURCES:
        errors.append("source must be calendar, isso or basic_needs")
    kind = payload.get("kind")
    if kind not in ALLOWED_FIXTURE_KINDS:
        errors.append("kind must be localist_json or html_excerpt")
    if payload.get("contains_private_data") is not False:
        errors.append("contains_private_data must be false")
    if payload.get("sanitized") is not True:
        errors.append("sanitized must be true")
    if not isinstance(payload.get("canonical_url"), str) or not payload.get("canonical_url"):
        errors.append("canonical_url is required")
    content = payload.get("content")
    if not isinstance(content, (dict, list, str)):
        errors.append("content must be object, list or string")
    forbidden = json.dumps(payload, ensure_ascii=False).lower()
    for token in ("authorization:", "cookie:", "set-cookie:", "telegram_owner_chat_id", "openai_api_key"):
        if token in forbidden:
            errors.append(f"forbidden secret-bearing token present: {token}")
    return errors


def build_review_sheet(manifest: Mapping[str, Any]) -> dict[str, Any]:
    cases = manifest.get("cases") if isinstance(manifest.get("cases"), list) else []
    rows = []
    for case in cases:
        if not isinstance(case, Mapping):
            continue
        rows.append({
            "id": case.get("id"),
            "source": case.get("source"),
            "split": case.get("split"),
            "scenario": case.get("scenario"),
            "expected_outcome": case.get("expected_outcome"),
            "review_status": case.get("review_status"),
            "fixture_ref": case.get("fixture_ref"),
            "operator_label": "",
            "material_fields": [],
            "reason": "",
        })
    return {
        "schema_version": "utd_operator_review_sheet.v1",
        "instructions": {
            "allowed_labels": sorted(ALLOWED_OUTCOMES),
            "rule": "Do not mark reviewed_operator until a human has inspected the fixture and chosen the label.",
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    fixture = sub.add_parser("validate-fixture")
    fixture.add_argument("path", type=Path)

    sheet = sub.add_parser("review-sheet")
    sheet.add_argument("--manifest", type=Path, required=True)
    sheet.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "validate-fixture":
        payload = json.loads(args.path.read_text(encoding="utf-8"))
        errors = validate_fixture(payload)
        print(json.dumps({"errors": errors}, ensure_ascii=False, sort_keys=True))
        return 1 if errors else 0

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = build_review_sheet(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
