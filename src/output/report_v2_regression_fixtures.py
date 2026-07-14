from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


REGRESSION_MANIFEST_SCHEMA_VERSION = "report_v2_regression_manifest.v1"
REQUIRED_CONTRACT_REFS = frozenset(
    {
        "split_ai_report",
        "report_quality",
        "reader_value_quality",
        "report_visuals",
        "feedback_receipt",
        "mvp_radar_reader",
    }
)
DEFAULT_REGRESSION_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "intelligence_report_v2"
    / "irx13_fixture_manifest.v1.json"
)

REQUIRED_SCENARIO_COVERAGE = frozenset(
    {
        "new_week_monday",
        "sunday_year_boundary",
        "previous_week_reactions",
        "fable_claude_duplication",
        "missing_radar",
        "investigate_radar",
        "context_only_market_lens",
        "concrete_project_implication",
        "no_project_implication",
        "generic_fallback",
        "weak_evidence",
        "partial_period",
        "empty_period",
        "confirmed_feedback_receipt",
        "desktop_viewport",
        "mobile_viewport",
        "w29_failure_pattern",
    }
)

REQUIRED_VIEWPORTS = frozenset({"desktop_1440", "mobile_375"})


class ReportV2RegressionFixtureError(ValueError):
    pass


def load_report_v2_regression_manifest(path: str | Path = DEFAULT_REGRESSION_MANIFEST) -> dict[str, Any]:
    manifest_path = Path(path)
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportV2RegressionFixtureError(f"invalid JSON manifest: {manifest_path}") from exc
    if not isinstance(value, dict):
        raise ReportV2RegressionFixtureError("regression manifest must be a JSON object")
    validate_report_v2_regression_manifest(value, manifest_path=manifest_path)
    return value


def validate_report_v2_regression_manifest(
    manifest: Mapping[str, Any],
    *,
    manifest_path: str | Path | None = None,
) -> None:
    errors: list[str] = []
    root = _repo_root_for_manifest(manifest_path)

    if manifest.get("schema_version") != REGRESSION_MANIFEST_SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    _required_text(manifest, "fixture_set_id", errors)
    _required_text(manifest, "updated_at", errors)

    contracts = _mapping(manifest.get("expected_contracts"))
    missing_contracts = sorted(REQUIRED_CONTRACT_REFS - set(contracts))
    if missing_contracts:
        errors.append("missing expected contract refs: " + ", ".join(missing_contracts))
    for key, value in contracts.items():
        if not str(value or "").strip():
            errors.append(f"expected_contracts.{key} must be non-empty")

    privacy = _mapping(manifest.get("privacy"))
    if privacy.get("raw_telegram_content") != "excluded":
        errors.append("privacy.raw_telegram_content must be excluded")
    if privacy.get("generated_private_reports") != "excluded":
        errors.append("privacy.generated_private_reports must be excluded")
    if privacy.get("redaction_provenance") != "synthetic_or_sanitized":
        errors.append("privacy.redaction_provenance must be synthetic_or_sanitized")

    scenarios = _mapping_list(manifest.get("scenarios"))
    if not scenarios:
        errors.append("scenarios must not be empty")
    coverage: set[str] = set()
    scenario_ids: set[str] = set()
    for index, scenario in enumerate(scenarios):
        path = f"scenarios[{index}]"
        scenario_id = _required_text(scenario, "id", errors, path=path)
        if scenario_id in scenario_ids:
            errors.append(f"{path}.id is duplicated")
        scenario_ids.add(scenario_id)
        _required_text(scenario, "title", errors, path=path)
        scenario_coverage = _string_list(scenario.get("coverage"), f"{path}.coverage", errors)
        coverage.update(scenario_coverage)
        for ref_index, fixture_ref in enumerate(_mapping_list(scenario.get("fixture_refs"))):
            ref_path = _required_text(fixture_ref, "path", errors, path=f"{path}.fixture_refs[{ref_index}]")
            if ref_path and (Path(ref_path).is_absolute() or ".." in Path(ref_path).parts):
                errors.append(f"{path}.fixture_refs[{ref_index}].path must be repository-relative")
            if ref_path and not (root / ref_path).exists():
                errors.append(f"{path}.fixture_refs[{ref_index}].path does not exist: {ref_path}")
        assertions = _mapping(scenario.get("structured_assertions"))
        if not assertions:
            errors.append(f"{path}.structured_assertions must not be empty")
        if scenario.get("private_data") not in (False, None):
            errors.append(f"{path}.private_data must be false or omitted")

    missing = sorted(REQUIRED_SCENARIO_COVERAGE - coverage)
    if missing:
        errors.append("missing required scenario coverage: " + ", ".join(missing))

    visual = _mapping(manifest.get("visual_regression"))
    _required_text(visual, "command", errors, path="visual_regression")
    viewports = {}
    for index, item in enumerate(_mapping_list(visual.get("viewports"))):
        viewport_id = str(item.get("id") or "")
        if viewport_id:
            viewports[viewport_id] = item
        width = item.get("width")
        if not isinstance(width, int) or width <= 0:
            errors.append(f"visual_regression.viewports[{index}].width must be positive int")
    missing_viewports = sorted(REQUIRED_VIEWPORTS - set(viewports))
    if missing_viewports:
        errors.append("missing visual regression viewports: " + ", ".join(missing_viewports))
    if viewports.get("desktop_1440", {}).get("width") != 1440:
        errors.append("desktop_1440 viewport width must be 1440")
    if viewports.get("mobile_375", {}).get("width") != 375:
        errors.append("mobile_375 viewport width must be 375")
    status = str(visual.get("baseline_status") or "")
    if status not in {"recorded", "prerequisite_required"}:
        errors.append("visual_regression.baseline_status is invalid")
    approved_hashes = visual.get("approved_snapshot_hashes")
    if not isinstance(approved_hashes, dict):
        errors.append("visual_regression.approved_snapshot_hashes must be an object")
    elif status == "recorded":
        for viewport_id in REQUIRED_VIEWPORTS:
            value = str(approved_hashes.get(viewport_id) or "")
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                errors.append(f"visual_regression.approved_snapshot_hashes.{viewport_id} must be sha256")
    elif approved_hashes:
        errors.append("prerequisite_required visual baselines must not claim snapshot hashes")
    _required_text(visual, "update_policy", errors, path="visual_regression")
    _required_text(visual, "redaction_policy", errors, path="visual_regression")

    if errors:
        raise ReportV2RegressionFixtureError("; ".join(errors))


def _repo_root_for_manifest(manifest_path: str | Path | None) -> Path:
    if manifest_path is not None:
        current = Path(manifest_path).resolve()
        for parent in (current.parent, *current.parents):
            if (parent / "src").exists() and (parent / "tests").exists():
                return parent
    return Path.cwd().resolve()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any, path: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{path} must be a list")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        text = str(item or "").strip()
        if not text:
            errors.append(f"{path}[{index}] must be non-empty")
            continue
        result.append(text)
    return result


def _required_text(
    value: Mapping[str, Any],
    field: str,
    errors: list[str],
    *,
    path: str = "",
) -> str:
    text = str(value.get(field) or "").strip()
    if not text:
        errors.append(f"{path + '.' if path else ''}{field} is required")
    return text
