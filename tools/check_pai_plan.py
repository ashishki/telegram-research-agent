#!/usr/bin/env python3
"""Offline PAI registration/mapping check; never product or approval evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from playbook import ROOT, verified_upstream


def check(root: Path = ROOT) -> int:
    upstream = verified_upstream(root)
    sys.path.insert(0, str(upstream / "tools"))
    import feature_design_lib
    import playbook_validate

    registry_path = root / "docs/design/PAI.design.json"
    findings, registry = feature_design_lib.validate_design_file(root, registry_path)
    errors = [f for f in findings if f.severity == "error"]
    if errors:
        raise ValueError("; ".join(f.check_id + ": " + f.message for f in errors))
    pack = (root / "docs/PA_IMPLEMENTATION_TASKS.md").read_text()
    card_entries = re.findall(
            r"^### (PAI-\d{2}) — [^\n]+\n(.*?)(?=\n<a id=|\n## Что записывать)",
            pack, re.M | re.S,
        )
    cards = dict(card_entries)
    if len(cards) != len(card_entries):
        raise ValueError("duplicate PAI card IDs")
    expected = {f"PAI-{n:02}" for n in range(32)}
    tasks = {
        b.task_id: b.to_record() for b in
        playbook_validate.parse_task_blocks(root / "docs/tasks.md")
        if b.task_id.startswith("PAI-")
    }
    slices = {s["slice_id"]: s for s in registry["slices"]}
    if set(cards) != expected or set(tasks) != expected or set(slices) != expected:
        raise ValueError("task pack, formal tasks and unique registry slices must cover PAI-00..31")
    if len(registry["slices"]) != len(expected):
        raise ValueError("duplicate PAI slice IDs")
    original = json.loads((root / "docs/design/PA.design.json").read_text())
    pa_ids = {s["slice_id"] for s in original["slices"]}
    coverage = set()
    future_tests = set()
    for task, body in cards.items():
        dep_value = re.search(r"^Depends-On: (.+)$", body, re.M).group(1)
        dependencies = [] if dep_value == "none" else dep_value.split(", ")
        refs = re.search(r"^PA-Refs: (.+)$", body, re.M).group(1).split(", ")
        if not set(refs) <= pa_ids:
            raise ValueError("unknown original PA requirement: " + task)
        coverage.update(refs)
        if set(dependencies) != set(tasks[task]["dependencies"]) or set(dependencies) != set(slices[task]["dependencies"]):
            raise ValueError("dependency mismatch: " + task)
        if "docs/design/PAI.design.json" not in tasks[task]["design_refs"]:
            raise ValueError("missing exact PAI design binding: " + task)
        if not tasks[task]["acceptance_criteria"] or not slices[task]["verification"]:
            raise ValueError("missing acceptance: " + task)
        verification_section = re.search(r"\*\*Проверить:\*\*(.*?)(?=\n\*\*|\Z)", body, re.S).group(1)
        declared_tests = set(re.findall(r"tests/[\w/.*-]+\.py", verification_section))
        registered_tests = {
            arg for entry in slices[task]["verification"] for arg in entry["argv"]
            if arg.startswith("tests/") and arg.endswith(".py")
        }
        if not declared_tests <= registered_tests:
            raise ValueError("card acceptance tests absent from registry: " + task)
        future_tests.update(p for p in registered_tests if not (root / p).is_file())
    if coverage != pa_ids:
        raise ValueError("original PA programme coverage incomplete")
    if len((root / "docs/design/PAI.md").read_text()) > 20000:
        raise ValueError("design exceeds pinned renderer context limit")
    print("PAI plan: 32 registered packets; dependency/acceptance/PA coverage and pinned schema checks passed.")
    print(f"Design state: {registry['status']}; {len(future_tests)} planned test files absent; no product/review/human/live claim.")
    return len(future_tests)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-implemented-tests", action="store_true",
                        help="fail if any registered acceptance test file is absent")
    args = parser.parse_args()
    try:
        missing = check()
        return 1 if args.require_implemented_tests and missing else 0
    except (OSError, ValueError, KeyError, AttributeError) as exc:
        print("PAI plan check failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
