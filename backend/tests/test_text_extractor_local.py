from __future__ import annotations

from app.services.extraction.text_extractor import _render_tables


def test_render_tables_pipe_delimited():
    tables = [[["Test", "Value", "Units"], ["Glucose", "95", "mg/dL"], ["A1c", "5.4", "%"]]]
    out = _render_tables(tables)
    assert "Test | Value | Units" in out
    assert "Glucose | 95 | mg/dL" in out
    assert "A1c | 5.4 | %" in out


def test_render_tables_handles_none_cells():
    tables = [[["A", None, "C"], [None, "2", None]]]
    out = _render_tables(tables)
    assert "A |  | C" in out
    assert " | 2 | " in out


def test_render_tables_empty_returns_empty():
    assert _render_tables([]) == ""
    assert _render_tables(None) == ""


from unittest.mock import MagicMock, patch


def _fake_page(text: str, tables: list | None = None):
    pg = MagicMock()
    pg.extract_text.return_value = text
    pg.extract_tables.return_value = tables or []
    return pg


def _fake_pdf(pages):
    pdf = MagicMock()
    pdf.pages = pages
    pdf.__enter__.return_value = pdf
    pdf.__exit__.return_value = False
    return pdf


def test_local_extraction_good_text_high_confidence(tmp_path):
    from app.services.extraction import text_extractor
    f = tmp_path / "n.pdf"; f.write_bytes(b"%PDF-1.4")
    pages = [_fake_page("A" * 400), _fake_page("B" * 400)]
    with patch.object(text_extractor.pdfplumber, "open", return_value=_fake_pdf(pages)):
        text, conf = text_extractor.extract_text_from_pdf_local(f)
    assert "AAA" in text and "BBB" in text
    assert conf == 400.0


def test_local_extraction_includes_tables(tmp_path):
    from app.services.extraction import text_extractor
    f = tmp_path / "n.pdf"; f.write_bytes(b"%PDF-1.4")
    pages = [_fake_page("Labs:", tables=[[["Glucose", "95"]]])]
    with patch.object(text_extractor.pdfplumber, "open", return_value=_fake_pdf(pages)):
        text, conf = text_extractor.extract_text_from_pdf_local(f)
    assert "Glucose | 95" in text


def test_local_extraction_empty_is_zero_confidence(tmp_path):
    from app.services.extraction import text_extractor
    f = tmp_path / "scan.pdf"; f.write_bytes(b"%PDF-1.4")
    pages = [_fake_page(""), _fake_page("")]
    with patch.object(text_extractor.pdfplumber, "open", return_value=_fake_pdf(pages)):
        text, conf = text_extractor.extract_text_from_pdf_local(f)
    assert conf == 0.0
