import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "docs" / "evidence" / "public_dogfood_status.json"
DEMO_PATH = ROOT / "docs" / "evidence" / "public_demo_scorecard.json"


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return payload


class TestPublicEvidence(unittest.TestCase):
    def test_public_dogfood_count_is_zero_and_claims_stay_blocked(self):
        status = _load_json(STATUS_PATH)

        self.assertEqual(status["schema_version"], "public-dogfood-evidence-ledger.v1")
        self.assertEqual(status["portfolio_role"], "secondary_project")
        self.assertEqual(status["operation_model"], "private_single_operator")
        self.assertEqual(status["target"]["required_verified_public_weeks"], 4)
        self.assertEqual(status["current"]["verified_public_week_count"], 0)
        self.assertEqual(status["current"]["verified_public_weeks"], [])
        self.assertEqual(
            status["current"]["verified_public_week_count"],
            len(status["current"]["verified_public_weeks"]),
        )
        self.assertTrue(status["blocked_claims"])
        self.assertEqual(
            {claim["status"] for claim in status["blocked_claims"]},
            {"not_evidenced"},
        )

    def test_synthetic_demo_is_content_addressed_and_not_dogfood(self):
        status = _load_json(STATUS_PATH)
        demo = _load_json(DEMO_PATH)
        evidence = status["public_evidence_items"][0]
        digest = hashlib.sha256(DEMO_PATH.read_bytes()).hexdigest()

        self.assertEqual(evidence["sha256"], digest)
        self.assertEqual(evidence["kind"], "synthetic_fixture")
        self.assertIn("dogfood_week", evidence["does_not_support"])
        self.assertEqual(demo["evidence_boundary"]["data_class"], "synthetic_fixture")
        self.assertIn("dogfood_week", demo["evidence_boundary"]["does_not_support"])
        self.assertNotIn("dogfood_review_json_path", demo["source_artifacts"])
        self.assertEqual(
            demo["dimensions"]["decisions_actions"]["metrics"]["decisions_changed_count"]["state"],
            "unknown",
        )
        self.assertEqual(
            demo["dimensions"]["ux"]["metrics"]["time_to_understand_week_minutes"]["state"],
            "unknown",
        )
        self.assertEqual(
            demo["dimensions"]["radar"]["metrics"]["radar_gate_decision"]["value"],
            "do_not_build",
        )
        self.assertEqual(
            demo["dimensions"]["radar"]["metrics"]["matched_gate_evidence_count"]["value"],
            0,
        )

    def test_committed_demo_matches_credential_free_regeneration(self):
        result = subprocess.run(
            [sys.executable, "scripts/public_scorecard_demo.py", "--check"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified sha256:", result.stdout)

    def test_public_json_contains_no_secret_bearing_keys(self):
        forbidden_key_fragments = {
            "api_key",
            "password",
            "phone_number",
            "session_string",
            "telegram_username",
        }
        public_json_paths = [
            STATUS_PATH,
            DEMO_PATH,
            ROOT / "examples" / "public_scorecard_demo" / "weekly-brief.json",
            ROOT / "examples" / "public_scorecard_demo" / "knowledge-atlas.json",
            ROOT / "examples" / "public_scorecard_demo" / "observations.json",
        ]

        def keys(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    yield str(key).lower()
                    yield from keys(nested)
            elif isinstance(value, list):
                for nested in value:
                    yield from keys(nested)

        for path in public_json_paths:
            key_names = set(keys(_load_json(path)))
            self.assertFalse(
                forbidden_key_fragments & key_names,
                f"secret-bearing key in {path}",
            )

    def test_readme_exposes_exact_public_evidence_boundary(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("0/4 verified public dogfood weeks", readme)
        self.assertIn("secondary portfolio project", readme)
        self.assertIn("docs/evidence/public_dogfood_status.json", readme)
        self.assertIn("it is not a dogfood run", readme)


if __name__ == "__main__":
    unittest.main()
