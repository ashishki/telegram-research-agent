import logging
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from output.report_schema import ResearchReport

try:
    from weasyprint import HTML as WeasyHTML
except ImportError:  # pragma: no cover - optional dependency
    WeasyHTML = None


LOGGER = logging.getLogger(__name__)
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(enabled_extensions=("html", "xml"), default=True),
)


def _paragraphs(text: str) -> list[str]:
    return [part.strip() for part in text.split("\n") if part.strip()]


def _finding_count(finding_body: str, evidence_count: int) -> int:
    match = re.search(r"(\d+)", finding_body or "")
    if match:
        return int(match.group(1))
    return evidence_count


def _build_topic_distribution_svg(report: ResearchReport) -> str:
    chart_items = [
        {
            "label": finding.title,
            "count": _finding_count(finding.body, len(finding.evidence_ids)),
        }
        for finding in report.key_findings
        if finding.title.strip()
    ]
    if not chart_items:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 120" role="img" aria-label="No topic data">'
            '<rect width="640" height="120" fill="#f3efe6"/>'
            '<text x="320" y="64" text-anchor="middle" fill="#6a6357" font-size="18">No topic distribution available</text>'
            "</svg>"
        )

    width = 640
    height = 70 + len(chart_items) * 44
    left = 190
    top = 30
    bar_height = 24
    gap = 20
    bar_width = width - left - 40
    max_count = max(item["count"] for item in chart_items) or 1
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Topic distribution chart">',
        f'<rect width="{width}" height="{height}" fill="#f7f3eb"/>',
        '<text x="24" y="22" fill="#201a12" font-size="18" font-weight="700">Topic Distribution</text>',
    ]
    for index, item in enumerate(chart_items):
        y = top + index * (bar_height + gap)
        scaled_width = max(8, int((item["count"] / max_count) * bar_width))
        label = _escape_svg(item["label"][:32])
        parts.append(f'<text x="24" y="{y + 17}" fill="#4f4436" font-size="14">{label}</text>')
        parts.append(
            f'<rect x="{left}" y="{y}" width="{bar_width}" height="{bar_height}" rx="12" fill="#e5dbcd"/>'
        )
        parts.append(
            f'<rect x="{left}" y="{y}" width="{scaled_width}" height="{bar_height}" rx="12" fill="#b65c2a"/>'
        )
        parts.append(
            f'<text x="{left + scaled_width + 10}" y="{y + 17}" fill="#201a12" font-size="13">{item["count"]}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _escape_svg(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def render_html(report: ResearchReport) -> str:
    template = _ENV.get_template("digest.html.j2")
    section_map = {section.heading: _paragraphs(section.body) for section in report.sections}
    return template.render(
        report=report,
        section_map=section_map,
        topic_chart_svg=_build_topic_distribution_svg(report),
    )


def render_pdf(report: ResearchReport, output_path: Path) -> Path | None:
    if WeasyHTML is None:
        LOGGER.warning("PDF rendering skipped because WeasyPrint is not installed")
        return None

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        html_content = render_html(report)
        WeasyHTML(string=html_content, base_url=str(TEMPLATE_DIR.parent.parent)).write_pdf(str(output_path))
        return output_path
    except Exception:
        LOGGER.warning("PDF rendering failed for week=%s", report.meta.week_label, exc_info=True)
        return None
