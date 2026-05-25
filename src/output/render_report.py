import html
import logging
import re
from pathlib import Path

from config.settings import PROJECT_ROOT


LOGGER = logging.getLogger(__name__)
REVIEWS_OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "reviews"
URL_RE = re.compile(r"https?://[^\s<>)]+")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(<?(https?://[^>)]+)>?\)")
DETAIL_LABELS = {
    "Key takeaway": "Takeaway",
    "Why now": "Why now",
    "Project application": "Project use",
    "Source": "Source",
}


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

    def render_signal_item(title: str, details: list[str]) -> None:
        close_list()
        body_parts.append("<article class=\"signal-item\">")
        body_parts.append(f"<h4>{_format_inline_markup(title)}</h4>")
        for detail in details:
            label, _, value = detail.partition(":")
            normalized_label = DETAIL_LABELS.get(label.strip(), label.strip())
            if value:
                body_parts.append(
                    f"<p><b>{html.escape(normalized_label)}:</b> {_format_inline_markup(value.strip())}</p>"
                )
            else:
                body_parts.append(f"<p>{_format_inline_markup(detail.strip())}</p>")
        body_parts.append("</article>")

    def render_list_item(text: str) -> None:
        nonlocal in_list
        if not in_list:
            body_parts.append("<ul>")
            in_list = True
        body_parts.append(f"<li>{_format_inline_markup(text.strip())}</li>")

    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.rstrip()
        if not line.strip():
            close_list()
            index += 1
            continue

        if line.startswith("# "):
            close_section()
            heading = html.escape(line[2:].strip())
            body_parts.append(f"<h1>{heading}</h1>")
            index += 1
            continue

        if line.startswith("## "):
            close_section()
            heading = html.escape(line[3:].strip())
            body_parts.append("<section class=\"brief-section\">")
            body_parts.append(f"<h2>{heading}</h2>")
            current_section_open = True
            section_started = True
            index += 1
            continue

        bold_heading = _extract_bold_only(line.strip())
        if bold_heading:
            close_list()
            body_parts.append(f"<h3>{_format_inline_markup(bold_heading)}</h3>")
            index += 1
            continue

        if line.startswith("- "):
            item_text = line[2:].strip()
            detail_lines: list[str] = []
            lookahead = index + 1
            while lookahead < len(lines):
                candidate = lines[lookahead]
                if not candidate.strip():
                    break
                if candidate.startswith(("  ", "\t")):
                    detail_lines.append(candidate.strip())
                    lookahead += 1
                    continue
                break
            if detail_lines:
                render_signal_item(item_text, detail_lines)
                index = lookahead
                continue
            render_list_item(item_text)
            index += 1
            continue

        close_list()
        body_parts.append(f"<p>{_format_inline_markup(line.strip())}</p>")
        index += 1

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
        "body{font-size:17px;-webkit-user-select:text;user-select:text;}"
        "section.brief-section{background:#fffdf8;border:1px solid #eadfcb;border-radius:10px;padding:18px;margin:0 0 14px 0;box-shadow:0 1px 0 rgba(0,0,0,.03);}"
        "article.signal-item{border:1px solid #e8ddca;border-radius:8px;background:#ffffff;padding:14px 15px;margin:0 0 12px 0;}"
        "h1,h2,h3,h4{font-family: Georgia, serif;color:#102a43;}"
        "h2{font-size:22px;line-height:1.25;margin:0 0 12px 0;}"
        "h3{font-size:18px;line-height:1.3;margin:18px 0 10px 0;}"
        "h4{font-size:17px;line-height:1.35;margin:0 0 9px 0;}"
        "p{margin:0 0 12px 0;}"
        "article.signal-item p{margin:0 0 8px 0;}"
        "ul{margin:0 0 10px 0;padding-left:22px;}"
        "li{margin:0 0 10px 0;}"
        "a{color:#0b6bcb;text-decoration:none;}"
        "b{color:#0f1720;}"
        "</style>"
        f"{joined}</body></html>"
    )


def _extract_bold_only(text: str) -> str | None:
    match = re.fullmatch(r"\*\*(.+?)\*\*", text.strip())
    if not match:
        return None
    return match.group(1).strip()


def _format_inline_markup(text: str) -> str:
    result: list[str] = []
    cursor = 0
    for match in MARKDOWN_LINK_RE.finditer(text):
        result.append(_format_plain_inline(text[cursor:match.start()]))
        label = html.escape(match.group(1).strip())
        url = html.escape(match.group(2).strip(), quote=True)
        result.append(f'<a href="{url}">{label}</a>')
        cursor = match.end()
    result.append(_format_plain_inline(text[cursor:]))
    return "".join(result)


def _format_plain_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    return URL_RE.sub(lambda match: f'<a href="{match.group(0)}">{match.group(0)}</a>', escaped)


def write_report_html(week_label: str, report_text: str, output_dir: Path | None = None) -> Path:
    target_dir = output_dir or REVIEWS_OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"{week_label}.html"
    output_path.write_text(render_report_html(report_text), encoding="utf-8")
    return output_path
