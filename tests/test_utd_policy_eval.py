import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).parents[1]

def _module():
    spec=importlib.util.spec_from_file_location("utd_policy_eval", ROOT/"tools/utd_policy_eval.py")
    module=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(module); return module


def test_all_50_cases_receive_proposed_not_human_outcomes():
    module=_module()
    manifest=json.loads((ROOT/"evals/external_watch/manifest.v1.json").read_text())
    result=module.score_manifest(manifest)
    assert result["case_count"] == 50
    assert sum(result["counts"].values()) == 50
    assert result["human_labels_added"] is False
    assert result["holdouts_used_for_tuning"] is False
    assert all(row["human_label"] is None for row in result["rows"])
