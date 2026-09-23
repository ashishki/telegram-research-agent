import importlib.util
from pathlib import Path


def _module(name="assistant_pdf_ocr_crosscheck_test"):
    path = Path(__file__).parents[1] / "tools" / "pdf_ocr_crosscheck.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _pdf(tmp_path: Path) -> Path:
    path = tmp_path / "brief.pdf"
    path.write_bytes(b"%PDF-1.4 minimal")
    return path


def test_extract_job_id_and_status_are_tolerant():
    module = _module("ocr_extract")
    assert module.extract_job_id({"job_id": "abc"}) == "abc"
    assert module.extract_job_id({"id": "xyz"}) == "xyz"
    assert module.extract_job_id({"job": {"id": "nested"}}) == "nested"
    assert module.extract_job_id({"nope": 1}) is None
    assert module.extract_status({"status": "COMPLETED"}) == "completed"
    assert module.extract_status({"job": {"state": "Failed"}}) == "failed"
    assert module.extract_status({}) == ""


def test_compare_expected_is_case_insensitive():
    module = _module("ocr_compare")
    text = "Привет мир HELLO"
    assert module.compare_expected(text, ["привет", "hello", "нет"]) == ("нет",)


def test_run_crosscheck_fails_closed_without_ack(tmp_path, monkeypatch):
    module = _module("ocr_run_closed")
    pdf = _pdf(tmp_path)
    common = dict(
        pdf_path=pdf,
        expected=["x"],
        api_key="key",
        base_url="https://sotaocr.com",
        model_profile=None,
        page_ranges=None,
        result_format="markdown",
        poll_interval=1.0,
        timeout=5,
        output_path=tmp_path / "r.json",
        dataset_output_path=tmp_path / "d.ndjson",
    )
    no_ack = module.run_crosscheck(third_party_upload=False, provider_egress=True, **common)
    assert no_ack["status"] == "skipped_fail_closed"
    assert no_ack["privacy"]["document_uploaded_to_third_party"] is False
    assert (tmp_path / "d.ndjson").is_file()


def test_run_crosscheck_fails_closed_without_key(tmp_path):
    module = _module("ocr_run_nokey")
    report = module.run_crosscheck(
        pdf_path=_pdf(tmp_path),
        expected=["x"],
        api_key="",
        base_url="https://sotaocr.com",
        model_profile=None,
        page_ranges=None,
        result_format="markdown",
        poll_interval=1.0,
        timeout=5,
        output_path=tmp_path / "r.json",
        dataset_output_path=tmp_path / "d.ndjson",
        third_party_upload=True,
        provider_egress=True,
    )
    assert report["status"] == "skipped_fail_closed"
    assert report["judge_status"] == "no_provider_credentials"
