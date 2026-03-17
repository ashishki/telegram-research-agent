import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

if "anthropic" not in sys.modules:
    anthropic_stub = types.ModuleType("anthropic")
    anthropic_stub.APIConnectionError = RuntimeError
    anthropic_stub.APIStatusError = RuntimeError
    anthropic_stub.APITimeoutError = RuntimeError
    anthropic_stub.RateLimitError = RuntimeError
    anthropic_stub.Anthropic = object
    sys.modules["anthropic"] = anthropic_stub

from output.map_project_insights import _split_keywords


class SplitKeywordsTests(unittest.TestCase):
    def test_json_array_keywords(self) -> None:
        self.assertEqual(_split_keywords('["python", "ml", "rust"]'), ["python", "ml", "rust"])

    def test_csv_keywords(self) -> None:
        self.assertEqual(_split_keywords("python, ml, rust"), ["python", "ml", "rust"])

    def test_empty_string_returns_empty_list(self) -> None:
        self.assertEqual(_split_keywords(""), [])

    def test_none_returns_empty_list(self) -> None:
        self.assertEqual(_split_keywords(None), [])

    def test_malformed_json_falls_back_to_csv_split(self) -> None:
        self.assertEqual(_split_keywords("[not valid"), ["[not valid"])


if __name__ == "__main__":
    unittest.main()
