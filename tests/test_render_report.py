import tempfile
import unittest
from pathlib import Path

from output.render_report import write_report_html


class TestRenderReport(unittest.TestCase):
    def test_write_report_html_writes_h2_tags(self):
        report_text = "## Strong Signals\n- item one\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = write_report_html("2026-W13", report_text, output_dir=Path(tmpdir))

            self.assertTrue(output_path.exists())
            html = output_path.read_text(encoding="utf-8")

        self.assertIn("<h2>Strong Signals</h2>", html)


if __name__ == "__main__":
    unittest.main()
