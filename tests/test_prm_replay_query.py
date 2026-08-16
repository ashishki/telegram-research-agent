import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _module():
    path = ROOT / "tools" / "prm_replay_query.py"
    spec = importlib.util.spec_from_file_location("prm_replay_query", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_private_replay_is_intent_first_and_source_direct():
    module = _module()
    fixture = json.loads((ROOT / "tests" / "fixtures" / "prm_agent_evals_replay.json").read_text())["items"]
    trace = module.replay_query(module.DEFAULT_QUERY, fixture=fixture)
    assert trace["route"]["primary_intent"] == "archive_to_action"
    assert trace["route"]["project_context_required"] is False
    assert trace["route"]["external_verification_required"] is False
    assert trace["candidates"][0]["relevance_label"] == "direct"
    assert trace["archive_contract"]["result_summary"]["direct_count"] == 1
    assert trace["render"]["decision_template_rendered"] is False


def test_public_replay_summary_contains_no_private_query_or_sources():
    module = _module()
    fixture = json.loads((ROOT / "tests" / "fixtures" / "prm_agent_evals_replay.json").read_text())["items"]
    summary = module.public_summary(module.replay_query(module.DEFAULT_QUERY, fixture=fixture))
    serialized = json.dumps(summary, ensure_ascii=False)
    assert module.DEFAULT_QUERY not in serialized
    assert "https://t.me" not in serialized
    assert "fixture:direct-agent-evals" not in serialized
    assert summary["privacy"]["contains_query"] is False
