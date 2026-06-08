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

    def test_render_numbered_actions_grouped_in_ol(self):
        html = render_report_html("## Actions This Week\n1. Apply gates\n2. Defer weak signal\n")

        self.assertIn("<ol>", html)
        self.assertIn("</ol>", html)
        self.assertIn("<li>Apply gates</li>", html)
        self.assertIn("<li>Defer weak signal</li>", html)

    def test_render_bold_formatting(self):
        html = render_report_html("This is **bold** text.\n")
        self.assertIn("<b>bold</b>", html)

    def test_render_signal_item_groups_indented_details(self):
        html = render_report_html(
            "## Project Insights\n"
            "**telegram-research-agent**\n"
            "- **Anthropic macro signal**\n"
            "  Key takeaway: Compute matters.\n"
            "  Why now: Official source.\n"
            "  Source: @data_secrets | https://t.me/data_secrets/9220\n"
        )

        self.assertIn("<h3>telegram-research-agent</h3>", html)
        self.assertIn("<article class=\"signal-item\">", html)
        self.assertIn("<h4><b>Anthropic macro signal</b></h4>", html)
        self.assertIn("<b>Takeaway:</b> Compute matters.", html)
        self.assertIn("<b>Why now:</b> Official source.", html)

    def test_render_markdown_links(self):
        html = render_report_html("- [repo](https://github.com/example/repo) — active\n")

        self.assertIn('<a href="https://github.com/example/repo">repo</a>', html)
        self.assertNotIn("](<a href", html)

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
