"""Parser tests against a small PDF generated on the fly, with known structure."""

import pymupdf
import pytest

from rag.ingest.pymupdf_parser import (
    BOLD_FLAG,
    PyMuPDFParser,
    _classify,
    _split_block,
)
from rag.models import ElementType

N_PAGES = 4


@pytest.fixture
def sample_pdf(tmp_path):
    pdf = pymupdf.open()
    for i in range(N_PAGES):
        page = pdf.new_page()  # A4-ish, 595 x 842 pt
        page.insert_text((72, 30), "Vraagspecificatie Eisen - versie 1.0", fontsize=8)
        page.insert_text((72, 200), f"{i + 1}.2 Geluid", fontsize=16)
        page.insert_textbox(
            pymupdf.Rect(72, 220, 520, 300),
            "De geluidsbelasting mag niet hoger zijn dan de grenswaarde uit de "
            "vergunning. Dit geldt voor alle fasen van het werk.",
            fontsize=10,
        )
        page.insert_text((72, 330), "- Metingen worden maandelijks uitgevoerd", fontsize=10)
        page.insert_text((72, 820), f"Pagina {i + 1} van {N_PAGES}", fontsize=8)
    path = tmp_path / "sample.pdf"
    pdf.save(path)
    return path


@pytest.fixture
def elements(sample_pdf):
    return PyMuPDFParser().parse(sample_pdf, "sample")


def test_every_page_is_covered(elements):
    assert {e.page for e in elements} == set(range(1, N_PAGES + 1))


def test_numbered_heading_gets_level_from_numbering(elements):
    headings = [e for e in elements if e.type == ElementType.HEADING]
    assert [h.text for h in headings][:2] == ["1.2 Geluid", "2.2 Geluid"]
    assert all(h.heading_level == 2 for h in headings)


def test_paragraph_lines_are_joined(elements):
    para = next(e for e in elements if e.type == ElementType.PARAGRAPH)
    assert para.text.startswith("De geluidsbelasting mag niet hoger")
    assert "\n" not in para.text


def test_bullet_is_list_item(elements):
    items = [e for e in elements if e.type == ElementType.LIST_ITEM]
    assert len(items) == N_PAGES
    assert items[0].text.startswith("- Metingen")


def test_repeating_header_and_footer_are_marked_other(elements):
    other = {e.text for e in elements if e.type == ElementType.OTHER}
    assert "Vraagspecificatie Eisen - versie 1.0" in other
    assert "Pagina 1 van 4" in other  # page numbers differ, but the pattern repeats


def test_ids_are_deterministic_and_bboxes_present(sample_pdf, elements):
    again = PyMuPDFParser().parse(sample_pdf, "sample")
    assert [e.element_id for e in again] == [e.element_id for e in elements]
    assert elements[0].element_id == "sample:p1:e0"
    assert all(e.bbox is not None for e in elements)


def test_table_becomes_markdown(tmp_path):
    pdf = pymupdf.open()
    page = pdf.new_page()
    rows = [("Eis", "Waarde"), ("Geluid", "60 dB"), ("Trilling", "2 mm/s")]
    x0, y0, w, h = 72, 100, 150, 20
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            rect = pymupdf.Rect(x0 + c * w, y0 + r * h, x0 + (c + 1) * w, y0 + (r + 1) * h)
            page.draw_rect(rect, color=(0, 0, 0), width=0.5)
            page.insert_text((rect.x0 + 4, rect.y1 - 6), cell, fontsize=10)
    path = tmp_path / "table.pdf"
    pdf.save(path)

    elements = PyMuPDFParser().parse(path, "t")
    tables = [e for e in elements if e.type == ElementType.TABLE]
    assert len(tables) == 1
    assert "60 dB" in tables[0].text and "|" in tables[0].text
    # cell text must not also appear as separate paragraphs
    assert not any(e.type == ElementType.PARAGRAPH and "60 dB" in e.text for e in elements)


def _line(text, size=10.0, bold=False):
    flags = BOLD_FLAG if bold else 0
    return {"bbox": (0, 0, 100, 10), "spans": [{"text": text, "size": size, "flags": flags}]}


def test_heading_sharing_a_block_with_its_paragraph_is_split_off():
    lines = [
        _line("2.2 Realisatiefase", bold=True),
        _line("Deze paragraaf geeft een beschrijving"),
        _line("van het systeem."),
    ]
    runs = _split_block(lines, body_size=10.0)
    assert [len(r) for r in runs] == [1, 2]


def test_each_list_marker_starts_a_new_run():
    lines = [_line("1. Grondoever"), _line("2. Steenoever"), _line("3. Krib")]
    assert len(_split_block(lines, body_size=10.0)) == 3


@pytest.mark.parametrize("text", ["Tabel 6-5: Warmtegeleiding hout", "Aanvangsdatum:", "60"])
def test_bold_non_headings_are_not_headings(text):
    el_type, _ = _classify(text, size=10.0, bold=True, body_size=10.0)
    assert el_type != ElementType.HEADING


def test_appendix_title_is_still_a_heading():
    el_type, _ = _classify("Bijlage B Systeemdecompositie", size=10.0, bold=True, body_size=10.0)
    assert el_type == ElementType.HEADING


def test_vertical_gap_starts_a_new_run():
    caption = {
        "bbox": (0, 0, 100, 10),
        "spans": [{"text": "Tabel 2: Normen", "size": 10.0, "flags": 0}],
    }
    para = {"bbox": (0, 30, 100, 40), "spans": [{"text": "Bovenop de", "size": 10.0, "flags": 0}]}
    assert len(_split_block([caption, para], body_size=10.0)) == 2


def test_paragraph_sharing_a_block_with_a_table_is_kept(tmp_path):
    """Regression: a whole block was dropped if it mostly overlapped a table."""
    pdf = pymupdf.open()
    page = pdf.new_page()
    for r in range(6):
        for c in range(2):
            rect = pymupdf.Rect(72 + c * 150, 100 + r * 14, 72 + (c + 1) * 150, 114 + r * 14)
            page.draw_rect(rect, color=(0, 0, 0), width=0.5)
            page.insert_text((rect.x0 + 3, rect.y1 - 3), f"cel {r}{c}", fontsize=9)
    page.insert_text((72, 200), "Bovenop de algemene regelgeving gelden voorschriften.", fontsize=9)
    path = tmp_path / "t.pdf"
    pdf.save(path)

    elements = PyMuPDFParser().parse(path, "t")
    assert any("Bovenop de algemene" in e.text for e in elements if e.type != ElementType.TABLE)


def test_consecutive_numbered_headings_are_split():
    lines = [
        _line("3.3.1 Casco algemeen"),
        _line("3.3.2 Waterdichte kruipruimte"),
        _line("3.3.4 Dak"),
    ]
    assert len(_split_block(lines, body_size=10.0)) == 3
