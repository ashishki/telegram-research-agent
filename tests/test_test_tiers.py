import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path


def _load_test_tiers_module():
    module_path = Path(__file__).resolve().parents[1] / "tools" / "test_tiers.py"
    spec = importlib.util.spec_from_file_location("test_tiers", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestTestTiers(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_test_tiers_module()

    def test_required_tiers_are_declared(self):
        self.assertEqual(
            sorted(self.module.TEST_TIERS),
            ["block-review", "fast-contract", "focused-prm", "full", "ops-date-sensitive"],
        )

    def test_focused_prm_prints_exact_command_without_running(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            exit_code = self.module.main(["focused-prm", "--print-only"])

        output = stream.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("PYTHONPATH=src", output)
        self.assertIn("tests/test_archive_retrieval_eval.py", output)
        self.assertIn("tests/test_pi_chat.py", output)

    def test_fast_contract_excludes_date_sensitive_ops_file(self):
        commands = [
            self.module.display_command(command)
            for command in self.module.TEST_TIERS["fast-contract"].commands
        ]

        self.assertFalse(any("tests/test_product_ops.py" in command for command in commands))
        self.assertTrue(any("tests/test_core_boundaries.py" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
