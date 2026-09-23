import importlib.util
from pathlib import Path

import pytest


def _module(name="assistant_visual_judge_test"):
    path = Path(__file__).parents[1] / "tools" / "assistant_visual_judge.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63fcffff3f0300050001a5f645400000000049454e44ae426082"
)


def _png(tmp_path: Path) -> Path:
    path = tmp_path / "shot.png"
    path.write_bytes(_PNG_BYTES)
    return path


def test_build_case_hashes_and_redacts(tmp_path):
    module = _module()
    case = module.build_case(
        case_id="visual:test:1",
        view="telegram_mobile",
        image_path=_png(tmp_path),
        title="Weekly brief user@example.com",
        context="see https://example.com/private",
    )
    assert case["image_sha256"] == module.sha256_bytes(_PNG_BYTES)
    assert "user@example.com" not in case["title"]
    assert "https://example.com/private" not in case["context"]
    assert "[REDACTED_URL:" in case["context"]
    assert case["view"] == "telegram_mobile"
    with pytest.raises(ValueError):
        module.build_case(case_id="x", view="nope", image_path=_png(tmp_path))


def test_image_data_url_mime_and_rejection(tmp_path):
    module = _module("assistant_visual_judge_url")
    assert module.build_image_data_url(_png(tmp_path)).startswith("data:image/png;base64,")
    bad = tmp_path / "shot.gif"
    bad.write_bytes(b"GIF89a")
    with pytest.raises(ValueError):
        module.build_image_data_url(bad)


def test_normalize_visual_judgment_flags_and_floor():
    module = _module("assistant_visual_judge_norm")
    good = module.normalize_visual_judgment(
        "c1",
        {"verdict": "pass", "scores": {field: 5 for field in module.VISUAL_SCORE_FIELDS}, "summary": "ok"},
    )
    assert good["verdict"] == "pass"
    assert good["status"] == "judged"

    bad = module.normalize_visual_judgment(
        "c2",
        {
            "verdict": "fail",
            "scores": {field: 5 for field in module.VISUAL_SCORE_FIELDS},
            "text_cropped": True,
            "risk_tags": ["crop", "crop"],
        },
    )
    assert bad["verdict"] == "fail"
    assert bad["text_cropped"] is True
    assert bad["risk_tags"] == ["crop"]
    assert bad["human_review_required"] is True


def test_normalize_rescales_ten_point_reply_to_five():
    module = _module("assistant_visual_judge_rescale")
    result = module.normalize_visual_judgment(
        "c1",
        {"verdict": "pass", "scores": {field: 8 for field in module.VISUAL_SCORE_FIELDS}, "summary": "ok"},
    )
    assert all(value == 4 for value in result["scores"].values())
    assert result["verdict"] == "pass"


def test_visual_status_escalates_layout_failure():
    module = _module("assistant_visual_judge_status")
    verdicts = [
        module.normalize_visual_judgment(
            "c1",
            {"verdict": "pass", "scores": {field: 5 for field in module.VISUAL_SCORE_FIELDS}, "horizontal_overflow": True},
        )
    ]
    status, judge_status, reason = module._visual_status(verdicts, [], 4.0)
    assert status == "failed_closed"
    assert "layout failures" in reason


def test_run_visual_judge_fails_closed_without_egress(tmp_path, monkeypatch):
    module = _module("assistant_visual_judge_run")
    case = module.build_case(case_id="c1", view="telegram_mobile", image_path=_png(tmp_path))
    common = dict(
        model="",
        timeout=5,
        max_output_tokens=200,
        quality_floor=4.0,
        output_path=tmp_path / "r.json",
        dataset_output_path=tmp_path / "d.ndjson",
        md_report_path=tmp_path / "r.md",
        judge_caller=lambda *a: {"case_id": "c1", "status": "judged", "verdict": "pass"},
    )
    skipped = module.run_visual_judge([case], provider_egress=False, **common)
    assert skipped["status"] == "skipped_fail_closed"
    assert skipped["judge_status"] == "no_model_configured"

    for name in ("OPENCODE_API_KEY", "OPENCODE_API_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)
    no_creds = module.run_visual_judge([case], provider_egress=True, **common)
    assert no_creds["status"] == "skipped_fail_closed"
    assert no_creds["judge_status"] == "no_provider_credentials"

    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    judged = module.run_visual_judge([case], provider_egress=True, **common)
    assert judged["metrics"]["judged_count"] == 1


def test_chrome_binary_is_discoverable():
    module = _module("assistant_visual_judge_chrome")
    binary = module.find_chrome()
    if binary is None:
        pytest.skip("no chrome/chromium available in this environment")
    assert Path(binary).is_file()


def test_default_model_is_vision_capable_name():
    module = _module("assistant_visual_judge_model")
    assert "vision" in module.DEFAULT_MODEL or module.DEFAULT_MODEL
