"""Local, deterministic PDF inspection and rasterization for quality judging.

Runs fully offline: ``pypdf`` extracts the text layer and structure, and
``pypdfium2`` rasterizes pages to PNG so a vision judge can see the real
rendered PDF (page breaks, pagination, glyphs). It never uploads a document and
never mutates the input. This is inspection for evaluation, not report export.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from pypdf import PdfReader

PDF_INSPECTION_SCHEMA_VERSION = "assistant.pdf_inspection.v1"
_REPLACEMENT_CHAR = "\ufffd"
_DEFAULT_MAX_PAGES = 60


@dataclass(frozen=True, slots=True)
class PdfPageInfo:
    page_number: int
    width_pt: float
    height_pt: float
    text_chars: int
    replacement_chars: int
    https_links: int
    non_https_links: int

    def to_payload(self) -> dict[str, object]:
        return {
            "page_number": self.page_number,
            "width_pt": round(self.width_pt, 2),
            "height_pt": round(self.height_pt, 2),
            "text_chars": self.text_chars,
            "replacement_chars": self.replacement_chars,
            "https_links": self.https_links,
            "non_https_links": self.non_https_links,
        }


@dataclass(frozen=True, slots=True)
class PdfInspection:
    page_count: int
    encrypted: bool
    total_text_chars: int
    replacement_char_count: int
    missing_expected: tuple[str, ...]
    https_link_count: int
    non_https_link_count: int
    embedded_font_names: tuple[str, ...]
    pages: tuple[PdfPageInfo, ...]
    truncated: bool
    schema_version: str = PDF_INSPECTION_SCHEMA_VERSION

    @property
    def has_text_layer(self) -> bool:
        return self.total_text_chars > 0

    def failures(self) -> tuple[str, ...]:
        result: list[str] = []
        if self.encrypted:
            result.append("encrypted")
        if self.page_count == 0:
            result.append("empty")
        if not self.has_text_layer:
            result.append("no_text_layer")
        if self.replacement_char_count > 0:
            result.append("replacement_chars")
        if self.missing_expected:
            result.append("missing_expected:" + ",".join(self.missing_expected[:5]))
        if self.non_https_link_count > 0:
            result.append("non_https_links")
        if self.truncated:
            result.append("too_many_pages")
        return tuple(result)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "page_count": self.page_count,
            "encrypted": self.encrypted,
            "total_text_chars": self.total_text_chars,
            "replacement_char_count": self.replacement_char_count,
            "missing_expected": list(self.missing_expected),
            "https_link_count": self.https_link_count,
            "non_https_link_count": self.non_https_link_count,
            "embedded_font_names": list(self.embedded_font_names),
            "has_text_layer": self.has_text_layer,
            "failures": list(self.failures()),
            "pages": [page.to_payload() for page in self.pages],
        }


def _page_links(page: object) -> tuple[int, int]:
    https = 0
    other = 0
    try:
        annots = page.get("/Annots")  # type: ignore[attr-defined]
    except Exception:
        return 0, 0
    if not annots:
        return 0, 0
    try:
        items = annots.get_object() if hasattr(annots, "get_object") else annots
    except Exception:
        return 0, 0
    for item in items or []:
        try:
            obj = item.get_object()
            action = obj.get("/A")
            uri = (action.get_object() if hasattr(action, "get_object") else action or {}).get("/URI")
        except Exception:
            continue
        if not uri:
            continue
        if str(uri).lower().startswith("https://"):
            https += 1
        else:
            other += 1
    return https, other


def _page_fonts(page: object) -> list[str]:
    names: list[str] = []
    try:
        resources = page["/Resources"].get_object()  # type: ignore[index]
        fonts = resources.get("/Font")
        fonts = fonts.get_object() if hasattr(fonts, "get_object") else fonts
    except Exception:
        return names
    for key in list(fonts or {}):
        try:
            font = fonts[key].get_object()
            base = str(font.get("/BaseFont") or "")
        except Exception:
            base = ""
        if base and base not in names:
            names.append(base)
    return names


def inspect_pdf(
    pdf_path: str | Path,
    *,
    expected_strings: Iterable[str] = (),
    max_pages: int = _DEFAULT_MAX_PAGES,
) -> PdfInspection:
    """Extract the text layer and structure without any network access."""

    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    reader = PdfReader(str(pdf_path))
    encrypted = bool(reader.is_encrypted)
    if encrypted:
        try:
            reader.decrypt("")
        except Exception:
            pass
    total_pages = len(reader.pages)
    truncated = total_pages > max_pages
    pages: list[PdfPageInfo] = []
    text_parts: list[str] = []
    fonts: list[str] = []
    https_total = 0
    other_total = 0
    replacement_total = 0
    for index in range(min(total_pages, max_pages)):
        page = reader.pages[index]
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        replacement = text.count(_REPLACEMENT_CHAR)
        replacement_total += replacement
        text_parts.append(text)
        https_links, other_links = _page_links(page)
        https_total += https_links
        other_total += other_links
        for name in _page_fonts(page):
            if name not in fonts:
                fonts.append(name)
        media = page.mediabox
        pages.append(
            PdfPageInfo(
                page_number=index + 1,
                width_pt=float(media.width),
                height_pt=float(media.height),
                text_chars=len(text),
                replacement_chars=replacement,
                https_links=https_links,
                non_https_links=other_links,
            )
        )
    combined = "\n".join(text_parts)
    folded = combined.casefold()
    expected = [str(item) for item in expected_strings if str(item).strip()]
    # Case-insensitive: CSS text-transform can change the extracted glyph case.
    missing = tuple(item for item in expected if item.casefold() not in folded)
    return PdfInspection(
        page_count=total_pages,
        encrypted=encrypted,
        total_text_chars=len(combined),
        replacement_char_count=replacement_total,
        missing_expected=missing,
        https_link_count=https_total,
        non_https_link_count=other_total,
        embedded_font_names=tuple(fonts),
        pages=tuple(pages),
        truncated=truncated,
    )


def rasterize_pdf(
    pdf_path: str | Path,
    output_dir: str | Path,
    *,
    scale: float = 2.0,
    max_pages: int = _DEFAULT_MAX_PAGES,
) -> tuple[Path, ...]:
    """Render each PDF page to a PNG for a vision judge; local only."""

    if scale <= 0:
        raise ValueError("scale must be positive")
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    import pypdfium2 as pdfium

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(pdf_path))
    stem = Path(pdf_path).stem
    rendered: list[Path] = []
    try:
        for index in range(min(len(document), max_pages)):
            page = document[index]
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            path = output / f"{stem}.page-{index + 1:03d}.png"
            image.save(path)
            rendered.append(path)
    finally:
        document.close()
    return tuple(rendered)
