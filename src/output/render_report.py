import html
import logging
import re
from pathlib import Path

from config.settings import PROJECT_ROOT


LOGGER = logging.getLogger(__name__)
REVIEWS_OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "reviews"
URL_RE = re.compile(r"(https?://[^\s<]+)")


def render_report_html(report_text: str) -> str:
    lines = report_text.splitlines()
    body_parts: list[str] = []
    in_list = False
    current_section_open = False
    section_started = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            body_parts.append("</ul>")
            in_list = False

    def close_section() -> None:
        nonlocal current_section_open
        if current_section_open:
            close_list()
            body_parts.append("</section>")
            current_section_open = False

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            close_list()
            continue

        if line.startswith("## "):
            close_section()
            heading = html.escape(line[3:].strip())
            body_parts.append("<section class=\"brief-section\">")
            body_parts.append(f"<h2>{heading}</h2>")
            current_section_open = True
            section_started = True
            continue

        if line.startswith("- "):
            if not in_list:
                body_parts.append("<ul>")
                in_list = True
            body_parts.append(f"<li>{_format_inline_markup(line[2:].strip())}</li>")
            continue

        close_list()
        body_parts.append(f"<p>{_format_inline_markup(line.strip())}</p>")

    if not section_started:
        body_parts.append("<section class=\"brief-section\">")
        current_section_open = True
    close_section()
    joined = "\n".join(body_parts)
    return (
        "<html><head><meta charset=\"utf-8\"></head><body style=\"font-family: Georgia, serif; "
        "line-height: 1.68; color: #18212b; background: #f7f2e8; max-width: 860px; "
        "margin: 0 auto; padding: 20px;\">"
        "<style>"
        "body{font-size:17px;}"
        "section.brief-section{background:#fffdf8;border:1px solid #eadfcb;border-radius:16px;padding:18px 18px 8px 18px;margin:0 0 14px 0;box-shadow:0 1px 0 rgba(0,0,0,.03);}"
        "h1,h2{font-family: Georgia, serif;color:#102a43;}"
        "h2{font-size:22px;line-height:1.25;margin:0 0 12px 0;}"
        "p{margin:0 0 12px 0;}"
        "ul{margin:0 0 10px 0;padding-left:22px;}"
        "li{margin:0 0 10px 0;}"
        "a{color:#0b6bcb;text-decoration:none;}"
        "b{color:#0f1720;}"
        "</style>"
        f"{joined}</body></html>"
    )


def _format_inline_markup(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = URL_RE.sub(r'<a href="\1">\1</a>', escaped)
    return escaped


def write_report_html(week_label: str, report_text: str, output_dir: Path | None = None) -> Path:
    target_dir = output_dir or REVIEWS_OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"{week_label}.html"
    output_path.write_text(render_report_html(report_text), encoding="utf-8")
    return output_path
