"""Conversion tests on a small hand-written Document Intelligence response."""

from azure.ai.documentintelligence.models import AnalyzeResult

from rag.ingest.docintel_parser import to_elements
from rag.models import ElementType

# One-inch squares, so bboxes are easy to check: 1 inch = 72 points.
SQUARE = [1, 1, 2, 1, 2, 2, 1, 2]


def _region(page, polygon=SQUARE):
    return [{"pageNumber": page, "polygon": polygon}]


def _para(offset, content, page=1, role=None):
    p = {
        "content": content,
        "spans": [{"offset": offset, "length": len(content)}],
        "boundingRegions": _region(page),
    }
    if role:
        p["role"] = role
    return p


def _cell(row, col, content, page, offset, **span):
    return {
        "rowIndex": row,
        "columnIndex": col,
        "content": content,
        "boundingRegions": _region(page),
        "spans": [{"offset": offset, "length": len(content)}],
        **span,
    }


RESULT = AnalyzeResult(
    {
        "pages": [{"pageNumber": 1, "unit": "inch"}, {"pageNumber": 2, "unit": "inch"}],
        "paragraphs": [
            _para(0, "DEFINITIEF | Vraagspecificatie Eisen", role="pageHeader"),  # 0
            _para(40, "Systeemeisen", role="sectionHeading"),  # 1
            _para(60, "3.2 Kribbaken", role="sectionHeading"),  # 2
            _para(80, "De eisen staan hieronder."),  # 3
            _para(110, "SYS-0010"),  # 4 (in table)
            _para(200, "• Metingen worden maandelijks uitgevoerd :selected:", page=2),  # 5
            _para(260, "Pagina 2 van 2", page=2, role="pageFooter"),  # 6
        ],
        "tables": [
            {
                "rowCount": 3,
                "columnCount": 2,
                "spans": [{"offset": 110, "length": 80}],
                "boundingRegions": _region(1) + _region(2),
                "cells": [
                    _cell(0, 0, "SYS-0010", 1, 110),
                    _cell(0, 1, "Ontwerp Topteken", 1, 120),
                    _cell(1, 0, "Het Topteken dient te voldoen", 1, 140, columnSpan=2),
                    _cell(2, 0, "V&V", 2, 175),
                    _cell(2, 1, "Geen", 2, 180),
                ],
            }
        ],
        "sections": [
            {"elements": ["/sections/1"]},
            {"elements": ["/paragraphs/1", "/sections/2"]},
            {"elements": ["/paragraphs/2", "/paragraphs/3", "/tables/0"]},
        ],
    }
)


def test_roles_map_to_types_and_levels():
    els = to_elements(RESULT, "d")
    by_text = {e.text: e for e in els}
    assert by_text["DEFINITIEF | Vraagspecificatie Eisen"].type == ElementType.OTHER
    assert by_text["Pagina 2 van 2"].type == ElementType.OTHER
    # unnumbered heading: level from the section tree; numbered: from its numbering
    assert by_text["Systeemeisen"].heading_level == 1
    assert by_text["3.2 Kribbaken"].heading_level == 2
    assert by_text["• Metingen worden maandelijks uitgevoerd"].type == ElementType.LIST_ITEM


def test_cell_paragraphs_are_not_duplicated():
    els = to_elements(RESULT, "d")
    assert not any(e.type != ElementType.TABLE and e.text == "SYS-0010" for e in els)


def test_table_is_split_per_page_with_merged_cell_once():
    tables = [e for e in to_elements(RESULT, "d") if e.type == ElementType.TABLE]
    assert [t.page for t in tables] == [1, 2]
    assert tables[0].text.count("Het Topteken dient te voldoen") == 1
    assert "V&V" in tables[1].text


def test_bbox_converted_from_inches_to_points():
    el = to_elements(RESULT, "d")[0]
    assert (el.bbox.x0, el.bbox.y0, el.bbox.x1, el.bbox.y1) == (72, 72, 144, 144)


def test_reading_order_and_ids():
    els = to_elements(RESULT, "d")
    page1 = [e for e in els if e.page == 1]
    assert [e.element_id for e in page1] == [f"d:p1:e{i}" for i in range(len(page1))]
    assert page1[-1].type == ElementType.TABLE  # the table comes after the paragraph above it
