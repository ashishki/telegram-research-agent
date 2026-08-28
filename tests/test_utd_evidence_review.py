import json
from pathlib import Path
import importlib.util

ROOT = Path(__file__).parents[1]


def _module():
    path = ROOT / "tools" / "utd_evidence_review.py"
    spec = importlib.util.spec_from_file_location("utd_evidence_review", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_fixture_validator_rejects_secret_tokens():
    module = _module()
    payload = {
        "schema_version": "utd_source_fixture.v1",
        "source": "calendar",
        "kind": "localist_json",
        "contains_private_data": False,
        "sanitized": True,
        "canonical_url": "https://calendar.utdallas.edu/example",
        "content": {"headers": {"Authorization:": "redacted"}},
    }
    assert module.validate_fixture(payload)


def test_review_sheet_keeps_operator_labels_blank():
    module = _module()
    manifest = json.loads((ROOT / "evals" / "external_watch" / "manifest.v1.json").read_text())
    sheet = module.build_review_sheet(manifest)
    assert len(sheet["rows"]) == 50
    assert all(row["operator_label"] == "" for row in sheet["rows"])
    assert all(row["review_status"] == "pending_operator" for row in sheet["rows"])
