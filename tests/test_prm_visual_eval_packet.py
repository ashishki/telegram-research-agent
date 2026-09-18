import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).parents[1] / "tools" / "prm_visual_eval_packet.py"
    spec = importlib.util.spec_from_file_location("prm_visual_eval_packet", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_visual_packet_selects_unique_balanced_synthetic_cases():
    module = _module()
    cases = module.select_cases(cases_per_surface=1)
    assert len(cases) == len(module.SURFACE_ORDER)
    assert len({case["case_id"] for case in cases}) == len(cases)


def test_visual_packet_prioritizes_positive_brief_and_lifecycle_screens():
    module = _module()
    cases = module.select_cases(cases_per_surface=6)
    case_ids = {case["case_id"] for case in cases}
    assert "judge:one:prm:brief:positive_topic_edition" in case_ids
    assert "judge:dialogue:utd:lifecycle:01:turns_001_004" in case_ids


def test_visual_renderer_escapes_visible_messages():
    module = _module()
    html = module.render_case_html(
        {"case_id": "x", "turns": [{"user_message": "<unsafe>", "assistant_visible_message": "a\nb", "deterministic_checks": {"safe": True}}]}
    )
    assert "&lt;unsafe&gt;" in html and "a<br>b" in html
