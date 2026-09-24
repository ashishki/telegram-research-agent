from pathlib import Path

import pytest

from prm.pdf_inspection import PdfInspection, PdfPageInfo, inspect_pdf, rasterize_pdf


def _minimal_text_pdf(text: str) -> bytes:
    """A tiny valid PDF with a real text layer (no external dependency)."""

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    content = ("BT /F1 18 Tf 72 720 Td (" + text + ") Tj ET").encode("latin-1")
    objects.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)


def _synthetic_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "brief.pdf"
    path.write_bytes(_minimal_text_pdf("Hello brief text"))
    return path


def test_inspect_pdf_reads_text_layer_and_expected(tmp_path):
    pdf = _synthetic_pdf(tmp_path)
    inspection = inspect_pdf(pdf, expected_strings=["Hello", "Missing"])
    assert inspection.page_count >= 1
    assert inspection.has_text_layer is True
    assert inspection.total_text_chars > 0
    assert inspection.missing_expected == ("Missing",)
    assert "missing_expected:Missing" in inspection.failures()
    assert inspection.to_payload()["has_text_layer"] is True


def test_expected_matching_is_case_insensitive(tmp_path):
    pdf = _synthetic_pdf(tmp_path)
    inspection = inspect_pdf(pdf, expected_strings=["HELLO BRIEF", "hello brief"])
    assert inspection.missing_expected == ()


def test_rasterize_pdf_produces_page_images(tmp_path):
    pdf = _synthetic_pdf(tmp_path)
    pages = rasterize_pdf(pdf, tmp_path / "pages", scale=1.0)
    assert len(pages) >= 1
    assert all(path.is_file() and path.suffix == ".png" for path in pages)


def test_failures_detect_structural_problems():
    page = PdfPageInfo(1, 595.0, 842.0, 0, 0, 0, 0)
    broken = PdfInspection(
        page_count=0,
        encrypted=False,
        total_text_chars=0,
        replacement_char_count=3,
        missing_expected=("X",),
        https_link_count=0,
        non_https_link_count=1,
        embedded_font_names=(),
        pages=(page,),
        truncated=True,
    )
    failures = broken.failures()
    assert "empty" in failures
    assert "no_text_layer" in failures
    assert "replacement_chars" in failures
    assert "non_https_links" in failures
    assert "too_many_pages" in failures


def test_inspect_pdf_rejects_bad_max_pages(tmp_path):
    pdf = _synthetic_pdf(tmp_path)
    with pytest.raises(ValueError):
        inspect_pdf(pdf, max_pages=0)
