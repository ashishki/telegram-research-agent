"""PAI registration guards using real pinned parsing, without touching files."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("pai_plan_check", ROOT / "tools/check_pai_plan.py")
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)


def test_current_registration_covers_full_programme_without_claiming_implementation(capsys):
    missing = plan.check(ROOT)
    output = capsys.readouterr().out
    assert "32 registered packets" in output
    assert "no product/review/human/live claim" in output
    # Planned suites are absent initially; this is explicit, never a fake PASS.
    assert isinstance(missing, int) and missing >= 0


@pytest.mark.parametrize("change", ["dependency", "design_binding", "missing_task"])
def test_registration_rejects_task_drift_from_design_and_card(monkeypatch, change):
    plan.check(ROOT)  # imports and validates the real pinned parser first
    import playbook_validate

    records = [
        (b.task_id, deepcopy(b.to_record()))
        for b in playbook_validate.parse_task_blocks(ROOT / "docs/tasks.md")
    ]
    record = next(value for task, value in records if task == "PAI-03")
    if change == "dependency":
        record["dependencies"] = ["PAI-00"]
    elif change == "design_binding":
        record["design_refs"] = ["docs/design/PA.design.json"]
    else:
        records = [(task, value) for task, value in records if task != "PAI-03"]
    blocks = [
        SimpleNamespace(task_id=task, to_record=lambda value=value: value)
        for task, value in records
    ]
    monkeypatch.setattr(playbook_validate, "parse_task_blocks", lambda path: blocks)
    with pytest.raises(ValueError, match={
        "dependency": "dependency mismatch",
        "design_binding": "missing exact PAI design binding",
        "missing_task": "must cover PAI-00..31",
    }[change]):
        plan.check(ROOT)
