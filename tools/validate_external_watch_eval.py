#!/usr/bin/env python3
"""Validate the public, sanitized external-watch evaluation inventory.

This is deliberately a manifest validator, not a collector or scoring engine.
It performs no network access, database access, provider call, or write.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


ALLOWED_SOURCES = {"calendar", "isso", "basic_needs", "synthetic_failure"}
ALLOWED_SPLITS = {"development", "blind_holdout"}
ALLOWED_OUTCOMES = {"notify", "ignore", "ambiguous"}
REQUIRED_SCENARIOS = {
    "new", "updated", "cancelled", "reinstated", "recurring", "duplicate",
    "cosmetic_change", "date_change", "location_change", "deadline_change",
    "disappearance", "return", "stale", "timeout", "rate_limited",
    "schema_drift", "prompt_injection", "eligibility", "past_event",
    "unsupported_savings",
}


def validate_manifest(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != "external_watch_eval_manifest.v1":
        errors.append("schema_version must be external_watch_eval_manifest.v1")
    if payload.get("contains_private_data") is not False:
        errors.append("contains_private_data must be false")
    if payload.get("launch_ready") is not False:
        errors.append("launch_ready must be false until operator evidence exists")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return [*errors, "cases must be a list"]
    if len(cases) != 50:
        errors.append("cases must contain exactly 50 entries")
    ids: set[str] = set()
    splits: dict[str, int] = {split: 0 for split in ALLOWED_SPLITS}
    scenarios: set[str] = set()
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            errors.append(f"case {index} must be an object")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"case {index} has invalid id")
        elif case_id in ids:
            errors.append(f"duplicate id: {case_id}")
        else:
            ids.add(case_id)
        source = case.get("source")
        if source not in ALLOWED_SOURCES:
            errors.append(f"{case_id}: unsupported source")
        split = case.get("split")
        if split not in ALLOWED_SPLITS:
            errors.append(f"{case_id}: unsupported split")
        else:
            splits[split] += 1
        scenario = case.get("scenario")
        if scenario not in REQUIRED_SCENARIOS:
            errors.append(f"{case_id}: unsupported scenario")
        else:
            scenarios.add(scenario)
        expected = case.get("expected_outcome")
        if expected is not None and expected not in ALLOWED_OUTCOMES:
            errors.append(f"{case_id}: unsupported expected_outcome")
        if case.get("review_status") not in {"pending_operator", "reviewed_operator"}:
            errors.append(f"{case_id}: review_status must be pending_operator or reviewed_operator")
        if case.get("fixture_ref") is not None and not str(case["fixture_ref"]).startswith("tests/fixtures/external_watch/"):
            errors.append(f"{case_id}: fixture_ref must stay under tests/fixtures/external_watch/")
    if splits["development"] != 35 or splits["blind_holdout"] != 15:
        errors.append("split must be exactly 35 development and 15 blind_holdout")
    missing = sorted(REQUIRED_SCENARIOS - scenarios)
    if missing:
        errors.append("missing required scenarios: " + ", ".join(missing))
    return errors


def readiness(payload: dict[str, Any]) -> dict[str, Any]:
    cases = payload.get("cases") if isinstance(payload.get("cases"), list) else []
    reviewed = sum(isinstance(case, dict) and case.get("review_status") == "reviewed_operator" for case in cases)
    labelled = sum(isinstance(case, dict) and case.get("expected_outcome") in ALLOWED_OUTCOMES for case in cases)
    return {
        "schema_valid": not validate_manifest(payload),
        "case_count": len(cases),
        "operator_reviewed_cases": reviewed,
        "labelled_cases": labelled,
        "shadow_ready": reviewed == 50 and labelled == 50 and payload.get("live_source_samples_verified") is True,
        "launch_ready": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"external_watch_eval: cannot read manifest: {exc}")
        return 2
    if not isinstance(payload, dict):
        print("external_watch_eval: manifest root must be an object")
        return 2
    errors = validate_manifest(payload)
    result = {"errors": errors, "readiness": readiness(payload)}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.json else result)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
