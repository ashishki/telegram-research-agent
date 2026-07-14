import copy
import os
import subprocess
import sys
import unittest
from pathlib import Path

from output.report_v2_regression_fixtures import (
    REQUIRED_SCENARIO_COVERAGE,
    REQUIRED_VIEWPORTS,
    ReportV2RegressionFixtureError,
    load_report_v2_regression_manifest,
    validate_report_v2_regression_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "intelligence_report_v2"
    / "irx13_fixture_manifest.v1.json"
)


class ReportV2RegressionFixtureTests(unittest.TestCase):
    def test_manifest_validates_required_release_candidate_coverage(self):
        manifest = load_report_v2_regression_manifest(MANIFEST_PATH)

        coverage = {
            item
            for scenario in manifest["scenarios"]
            for item in scenario["coverage"]
        }
        self.assertTrue(REQUIRED_SCENARIO_COVERAGE.issubset(coverage))
        self.assertEqual(
            set(manifest["expected_contracts"]),
            {
                "split_ai_report",
                "report_quality",
                "reader_value_quality",
                "report_visuals",
                "feedback_receipt",
                "mvp_radar_reader",
            },
        )

    def test_fixture_refs_are_committed_sanitized_files(self):
        manifest = load_report_v2_regression_manifest(MANIFEST_PATH)

        refs = [
            ref
            for scenario in manifest["scenarios"]
            for ref in scenario.get("fixture_refs", [])
        ]
        self.assertGreaterEqual(len(refs), 8)
        for scenario in manifest["scenarios"]:
            self.assertFalse(scenario.get("private_data", False))
            self.assertTrue(scenario["structured_assertions"])
        for ref in refs:
            path = Path(ref["path"])
            self.assertFalse(path.is_absolute())
            self.assertNotIn("..", path.parts)
            self.assertTrue((PROJECT_ROOT / path).exists(), ref)
            self.assertTrue(str(path).startswith("tests/fixtures/"), ref)

    def test_visual_policy_is_explicit_and_unrecorded_hashes_do_not_claim_evidence(self):
        manifest = load_report_v2_regression_manifest(MANIFEST_PATH)
        visual = manifest["visual_regression"]

        viewports = {item["id"]: item for item in visual["viewports"]}
        self.assertTrue(REQUIRED_VIEWPORTS.issubset(viewports))
        self.assertEqual(viewports["desktop_1440"]["width"], 1440)
        self.assertEqual(viewports["mobile_375"]["width"], 375)
        self.assertEqual(visual["baseline_status"], "prerequisite_required")
        self.assertEqual(visual["approved_snapshot_hashes"], {})
        self.assertIn("review", visual["update_policy"].lower())
        self.assertIn("Raw Telegram", visual["redaction_policy"])

    def test_missing_required_coverage_fails_closed(self):
        manifest = load_report_v2_regression_manifest(MANIFEST_PATH)
        invalid = copy.deepcopy(manifest)
        invalid["scenarios"] = [
            scenario
            for scenario in invalid["scenarios"]
            if "desktop_viewport" not in scenario["coverage"]
        ]

        with self.assertRaisesRegex(ReportV2RegressionFixtureError, "desktop_viewport"):
            validate_report_v2_regression_manifest(invalid, manifest_path=MANIFEST_PATH)

    def test_snapshot_harness_reports_local_prerequisites_without_fabricating_evidence(self):
        command = [
            sys.executable,
            "scripts/report_v2_visual_snapshots.py",
            "--manifest",
            str(MANIFEST_PATH.relative_to(PROJECT_ROOT)),
            "--viewports",
            "1440x1000",
            "375x1000",
            "--check-prerequisites",
        ]
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env={**os.environ, "PYTHONPATH": "src"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertIn(result.returncode, {0, 2})
        combined = result.stdout + result.stderr
        if result.returncode == 0:
            self.assertIn("harness ready", combined)
        else:
            self.assertIn("prerequisites unavailable", combined)


if __name__ == "__main__":
    unittest.main()
