from __future__ import annotations

import json
from pathlib import Path

from assistant.utd_profile import classify_utd_question, render_utd_question_preview


def test_synthetic_utd_ux_cases_fail_closed_without_live_sources() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "utd_ux_cases.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert payload["privacy"] == "synthetic_public"
    assert len(payload["cases"]) == 5
    for case in payload["cases"]:
        answer = render_utd_question_preview(case["question"])
        assert classify_utd_question(case["question"]) == case["expected_category"]
        assert case["expected_phrase"] in answer
        assert case["forbidden_claim"] not in answer
        assert "Live UTD-источники" in answer
