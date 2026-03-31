import html
import logging
import re
from pathlib import Path

from config.settings import PROJECT_ROOT


LOGGER = logging.getLogger(__name__)
REVIEWS_OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "reviews"


def render_report_html(report_text: str) -> str:
    lines = report_text.splitlines()
    body_parts: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            body_parts.append("</ul>")
            in_list = False

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            close_list()
            continue

        if line.startswith("## "):
            close_list()
            body_parts.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
            continue

        if line.startswith("- "):
            if not in_list:
                body_parts.append("<ul>")
                in_list = True
            body_parts.append(f"<li>{_format_inline_markup(line[2:].strip())}</li>")
            continue

        close_list()
        body_parts.append(f"<p>{_format_inline_markup(line.strip())}</p>")

    close_list()
    joined = "\n".join(body_parts)
    return (
        "<html><body style=\"font-family: Arial, sans-serif; line-height: 1.5; color: #222; "
        "max-width: 860px; margin: 0 auto; padding: 24px;\">"
        f"{joined}</body></html>"
    )


def _format_inline_markup(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


def write_report_html(week_label: str, report_text: str, output_dir: Path | None = None) -> Path:
    target_dir = output_dir or REVIEWS_OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"{week_label}.html"
    output_path.write_text(render_report_html(report_text), encoding="utf-8")
    return output_path
