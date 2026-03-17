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

from output.report_utils import _extract_markdown_section


class ExtractMarkdownSectionTests(unittest.TestCase):
    def test_section_found_in_middle_of_document(self) -> None:
        text = "## First\nalpha\n\n## Target\nwanted\nline two\n\n## Last\nomega\n"
        self.assertEqual(_extract_markdown_section(text, "Target"), "wanted\nline two")

    def test_section_found_at_end_of_document(self) -> None:
        text = "## Intro\nalpha\n\n## Tail\nfinal line\n"
        self.assertEqual(_extract_markdown_section(text, "Tail"), "final line")

    def test_section_not_found_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            _extract_markdown_section("## Intro\nalpha\n", "Missing")

    def test_heading_with_special_regex_chars_is_escaped(self) -> None:
        text = "## Intro\nalpha\n\n## C++ [Core] (v2)?\nmatched\n"
        self.assertEqual(_extract_markdown_section(text, "C++ [Core] (v2)?"), "matched")


if __name__ == "__main__":
    unittest.main()
