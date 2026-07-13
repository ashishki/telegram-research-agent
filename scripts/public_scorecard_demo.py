#!/usr/bin/env python3
"""Build or verify the credential-free synthetic public scorecard."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from output.dogfood_review import (  # noqa: E402
    build_weekly_intelligence_scorecard,
    validate_weekly_intelligence_scorecard,
)


FIXTURE_DIR = ROOT / "examples" / "public_scorecard_demo"
DEFAULT_OUTPUT = ROOT / "docs" / "evidence" / "public_demo_scorecard.json"
GENERATED_AT = "2026-07-13T00:00:00Z"


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"fixture must contain a JSON object: {path}")
    return payload


def build_demo_scorecard() -> dict[str, Any]:
    """Run the existing scorecard logic over explicitly synthetic inputs."""
    weekly_brief = _read_object(FIXTURE_DIR / "weekly-brief.json")
    knowledge_atlas = _read_object(FIXTURE_DIR / "knowledge-atlas.json")
    observations = _read_object(FIXTURE_DIR / "observations.json")
    scorecard = build_weekly_intelligence_scorecard(
        week_label="2026-W28",
        weekly_brief=weekly_brief,
        knowledge_atlas=knowledge_atlas,
        observations=observations,
        source_artifacts={
            "weekly_brief_json_path": "examples/public_scorecard_demo/weekly-brief.json",
            "knowledge_atlas_json_path": "examples/public_scorecard_demo/knowledge-atlas.json",
            "observations_json_path": "examples/public_scorecard_demo/observations.json",
        },
        generated_at=GENERATED_AT,
    )
    findings = validate_weekly_intelligence_scorecard(scorecard)
    if findings:
        raise ValueError(f"generated scorecard failed validation: {findings}")
    scorecard["evidence_boundary"] = {
        "data_class": "synthetic_fixture",
        "supports": ["credential_free_scorecard_contract"],
        "does_not_support": [
            "dogfood_week",
            "operator_outcome",
            "production_reliability",
            "user_or_design_partner_validation",
        ],
    }
    return scorecard


def render_demo_scorecard() -> bytes:
    payload = json.dumps(
        build_demo_scorecard(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return f"{payload}\n".encode("utf-8")


def _resolve_output(value: str) -> Path:
    output = Path(value)
    return output if output.is_absolute() else ROOT / output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT.relative_to(ROOT)),
        help="repository-relative or absolute JSON output path",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that the committed artifact equals a fresh deterministic build",
    )
    args = parser.parse_args()

    output = _resolve_output(args.output)
    rendered = render_demo_scorecard()
    digest = hashlib.sha256(rendered).hexdigest()
    if args.check:
        if not output.exists():
            print(f"missing expected artifact: {output}", file=sys.stderr)
            return 1
        if output.read_bytes() != rendered:
            print(f"artifact drift: {output}", file=sys.stderr)
            return 1
        print(f"verified sha256:{digest} {output.relative_to(ROOT)}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rendered)
    print(f"wrote sha256:{digest} {output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
