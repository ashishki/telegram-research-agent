#!/usr/bin/env python3
"""Offline PAI registration/mapping check; never product or approval evidence."""
from __future__ import annotations

import argparse
import json
import hashlib
import fnmatch
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
        for entry in slices[task]["verification"]:
            if (any(arg.startswith("tests/test_pai_") for arg in entry["argv"])
                and entry["argv"][1] != "tools/run_pai_acceptance.py"):
                raise ValueError("PAI acceptance must fail on skipped/missing cases: " + task)
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
    matrix = json.loads((root / "docs/design/PAI.requirements.json").read_text())
    md = (root / "docs/design/PAI.md").read_text()
    matrix_digest = hashlib.sha256((root / "docs/design/PAI.requirements.json").read_bytes()).hexdigest()
    if "Requirements-matrix-SHA256: " + matrix_digest not in md:
        raise ValueError("design/matrix hash binding is stale")
    spec = (root / "docs/PERSONAL_ASSISTANT_SPEC.md").read_text()
    spec_ids = set(re.findall(r"\*\*([A-Z]+-\d{2})\b", spec))
    rows = matrix["requirements"]
    if len(rows) != len(spec_ids) or {row["spec_id"] for row in rows} != spec_ids:
        raise ValueError("fine-grained spec coverage incomplete or duplicated")
    if matrix["spec_sha256"] != hashlib.sha256(spec.encode()).hexdigest():
        raise ValueError("requirement matrix is stale against the full spec")
    refs = {task + "/" + v["id"] for task, sl in slices.items() for v in sl["verification"]}
    for row in rows:
        if not row["slices"] or not set(row["slices"]) <= set(slices):
            raise ValueError("unknown requirement slice: " + row["spec_id"])
        if not row["verification_refs"] or not set(row["verification_refs"]) <= refs:
            raise ValueError("unknown requirement verification: " + row["spec_id"])
        if not row["review_roles"] or not row["human_gate"]:
            raise ValueError("missing requirement review/human gate")
    scenario_text = [line[2:].strip() for line in spec.split("### 13.2.")[1].split("**EVAL-03:")[0].splitlines() if line.startswith("- ")]
    scenarios = matrix["scenarios"]
    if len(scenarios) != len(scenario_text) or [s["source_text"] for s in scenarios] != scenario_text:
        raise ValueError("mandatory scenario coverage differs from the full spec")
    if [s["scenario_id"] for s in scenarios] != [f"SC13.2-{i:02}" for i in range(1, 11)]:
        raise ValueError("mandatory scenario IDs incomplete or duplicated")
    for scenario in scenarios:
        if not set(scenario["slices"]) <= set(slices) or not scenario["review_roles"] or not scenario["human_evidence"]:
            raise ValueError("mandatory scenario slice/review binding invalid")
        if scenario["synthetic_test_node"].split("::")[0] not in {
            arg for v in slices["PAI-26"]["verification"] for arg in v["argv"]
        }:
            raise ValueError("mandatory scenario is not registered in PAI-26")
        if not any(interface.startswith(scenario["scenario_id"] + ":") for interface in slices["PAI-26"]["expected_interfaces"]):
            raise ValueError("PAI-26 does not enumerate mandatory scenario")
    if any(path.startswith(("src/", "tests/", "tools/")) for path in slices["PAI-01"]["allowed_files"]):
        raise ValueError("design-only PAI-01 grants runtime/checker edit scope")
    for task, sl in slices.items():
        for allowed in sl["allowed_files"]:
            if any(allowed == forbidden or fnmatch.fnmatchcase(allowed, forbidden) for forbidden in sl["forbidden_files"]):
                raise ValueError("allowed/forbidden scope overlap: " + task)
        for v in sl["verification"]:
            for arg in v["argv"]:
                if arg.startswith("tests/") and arg.endswith(".py") and not (root / arg).exists() and not arg.startswith("tests/test_pai_"):
                    raise ValueError("missing existing regression test: " + arg)
    if len((root / "docs/design/PAI.md").read_text()) > 20000:
        raise ValueError("design exceeds pinned renderer context limit")
    print("PAI plan: 32 registered packets; dependency/acceptance/PA coverage and pinned schema checks passed.")
    print(f"Spec coverage: {len(rows)} exact requirement IDs, {len(scenarios)} mandatory scenarios; planned evidence is not a PASS.")
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
