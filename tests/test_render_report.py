import tempfile
import unittest
from pathlib import Path

from output.render_report import render_report_html, write_report_html


class TestRenderReport(unittest.TestCase):
    def test_write_report_html_writes_h2_tags(self):
        report_text = "## Strong Signals\n- item one\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = write_report_html("2026-W13", report_text, output_dir=Path(tmpdir))

            self.assertTrue(output_path.exists())
            html = output_path.read_text(encoding="utf-8")

        self.assertIn("<h2>Strong Signals</h2>", html)

    def test_render_list_items_grouped_in_ul(self):
        html = render_report_html("- alpha\n- beta\n")
        self.assertIn("<ul>", html)
        self.assertIn("</ul>", html)
        self.assertIn("<li>alpha</li>", html)
        self.assertIn("<li>beta</li>", html)
        self.assertEqual(html.count("<ul>"), 1)

    def test_render_bold_formatting(self):
        html = render_report_html("This is **bold** text.\n")
        self.assertIn("<b>bold</b>", html)

    def test_render_plain_paragraph(self):
        html = render_report_html("Plain paragraph line\n")
        self.assertIn("<p>Plain paragraph line</p>", html)

    def test_render_html_escaping(self):
        html = render_report_html("5 < 6 & 7 > 3\n")
        self.assertIn("5 &lt; 6 &amp; 7 &gt; 3", html)
        self.assertNotIn("<p>5 < 6", html)

    def test_render_whitespace_only_produces_no_content_tags(self):
        html = render_report_html("   \n\n\t\n")
        self.assertNotIn("<h2>", html)
        self.assertNotIn("<p>", html)
        self.assertNotIn("<ul>", html)


if __name__ == "__main__":
    unittest.main()
