"""Baseline parser: PyMuPDF's text layer plus a few layout heuristics.

PyMuPDF gives us text blocks with exact coordinates and font information, but
no idea what a block *is*. So we infer structure with heuristics:

- runs:      blocks are first split into runs of lines (a heading and the
             paragraph under it often share one PyMuPDF block); each run is typed:
- heading:   short run in a larger font, or bold and short. Level comes from
             the numbering ("3.2.1 ..." -> 3) or, if unnumbered, the font size.
- list item: starts with a bullet or "a." / "1)" style marker.
- table:     PyMuPDF's line-based table finder. We render the Markdown
             ourselves from the raw cells: PyMuPDF's to_markdown() repeats
             merged-cell text in every spanned column. Text lines inside a
             table area are dropped so the text isn't duplicated.
- header/footer: shared post-processing (postprocess.py) re-types repeating
             text in the page margins as OTHER, so chunking can skip it.

These heuristics are the weak point, and that's intentional: step 1b compares
this baseline against Azure Document Intelligence, which uses a layout model.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from rag.ingest.postprocess import mark_repeating_margins
from rag.ingest.text import (
    LIST_MARKER,
    MULTILEVEL_HEADING,
    clean_text,
    is_non_heading,
    is_unstyled_heading,
    numbering_level,
    table_markdown,
)
from rag.models import BBox, Element, ElementType

BOLD_FLAG = 1 << 4  # PyMuPDF span flag for bold

MAX_HEADING_CHARS = 150
HEADING_SIZE_RATIO = 1.15  # font must be this much larger than body text
PARAGRAPH_GAP = 0.8  # vertical gap, as a fraction of line height, that starts a new run


@dataclass
class _Block:
    """A text block or table on one page, before we assign IDs."""

    page: int
    rect: pymupdf.Rect
    text: str
    type: ElementType
    heading_level: int | None = None


class PyMuPDFParser:
    name = "pymupdf"

    def parse(self, pdf_path: Path, doc_id: str) -> list[Element]:
        with pymupdf.open(pdf_path) as pdf:
            body_size = _body_font_size(pdf)
            blocks: list[_Block] = []
            page_heights = {page.number + 1: page.rect.height for page in pdf}
            for page in pdf:
                blocks.extend(_parse_page(page, body_size))

        elements: list[Element] = []
        index_on_page: Counter[int] = Counter()
        for b in blocks:
            idx = index_on_page[b.page]
            index_on_page[b.page] += 1
            elements.append(
                Element(
                    element_id=Element.make_id(doc_id, b.page, idx),
                    doc_id=doc_id,
                    page=b.page,
                    type=b.type,
                    text=b.text,
                    bbox=BBox(x0=b.rect.x0, y0=b.rect.y0, x1=b.rect.x1, y1=b.rect.y1),
                    heading_level=b.heading_level,
                    parser=self.name,
                )
            )
        mark_repeating_margins(elements, page_heights)
        return elements


def _parse_page(page: pymupdf.Page, body_size: float) -> list[_Block]:
    page_no = page.number + 1
    out: list[_Block] = []

    tables = [t for t in page.find_tables().tables if t.row_count >= 2 and t.col_count >= 2]
    table_rects = [pymupdf.Rect(t.bbox) for t in tables]
    for t, rect in zip(tables, table_rects, strict=True):
        if markdown := table_markdown(t.extract()):
            out.append(_Block(page_no, rect, markdown, ElementType.TABLE))

    for block in page.get_text("dict", sort=True)["blocks"]:
        if block["type"] != 0:  # 1 = image block
            continue
        # Filter per line, not per block: PyMuPDF sometimes puts a table's cell
        # text, its caption and the next paragraph in one block, and dropping
        # the whole block would silently lose that paragraph.
        kept = [ln for ln in block["lines"] if not _in_any(ln["bbox"], table_rects)]
        for run in _split_block(kept, body_size):
            text, max_size, all_bold = _lines_text(run)
            if not text:
                continue
            rect = pymupdf.Rect(run[0]["bbox"])
            for line in run[1:]:
                rect |= line["bbox"]
            el_type, level = _classify(text, max_size, all_bold, body_size)
            out.append(_Block(page_no, rect, text, el_type, level))

    # Reading order: top to bottom, then left to right. Fine for single-column
    # pages; multi-column layouts are where a layout model does better.
    out.sort(key=lambda b: (round(b.rect.y0), b.rect.x0))
    return out


def _split_block(lines: list[dict], body_size: float) -> list[list[dict]]:
    """Split a PyMuPDF block into runs of lines that belong together.

    PyMuPDF groups lines by proximity, so a heading is often in the same block
    as the paragraph below it, and consecutive list items share one block. We
    start a new run when a line switches between heading-style and body-style,
    when it starts with a list marker or multi-level numbering ("3.3.2 ..."), or
    after a vertical gap (a blank line).
    """
    runs: list[list[dict]] = []
    prev_heading_style: bool | None = None
    prev_bottom: float | None = None
    for line in lines:
        spans = [s for s in line["spans"] if s["text"].strip()]
        if not spans:
            continue
        text = "".join(s["text"] for s in line["spans"]).strip()
        heading_style = all(s["flags"] & BOLD_FLAG for s in spans) or (
            max(s["size"] for s in spans) >= body_size * HEADING_SIZE_RATIO
        )
        height = line["bbox"][3] - line["bbox"][1]
        gap = prev_bottom is not None and line["bbox"][1] - prev_bottom > height * PARAGRAPH_GAP
        starts_item = LIST_MARKER.match(text) or MULTILEVEL_HEADING.match(text)
        if not runs or heading_style != prev_heading_style or starts_item or gap:
            runs.append([])
        runs[-1].append(line)
        prev_heading_style = heading_style
        prev_bottom = line["bbox"][3]
    return runs


def _lines_text(lines: list[dict]) -> tuple[str, float, bool]:
    """Join lines into one string, undoing end-of-line hyphenation."""
    text = ""
    max_size = 0.0
    all_bold = True
    for line in lines:
        spans = [s for s in line["spans"] if s["text"].strip()]
        if not spans:
            continue
        line_text = "".join(s["text"] for s in line["spans"]).strip()
        max_size = max(max_size, *(s["size"] for s in spans))
        all_bold = all_bold and all(s["flags"] & BOLD_FLAG for s in spans)
        if text.endswith("-") and line_text[:1].islower():
            text = text[:-1] + line_text  # "ont-" + "werp" -> "ontwerp"
        elif text.endswith("-"):
            text += line_text  # "Noord-" + "Holland" -> "Noord-Holland"
        else:
            text = f"{text} {line_text}" if text else line_text
    text = clean_text(text)
    return text, max_size, all_bold and bool(text)


def _classify(
    text: str, size: float, bold: bool, body_size: float
) -> tuple[ElementType, int | None]:
    is_short = len(text) <= MAX_HEADING_CHARS
    is_large = size >= body_size * HEADING_SIZE_RATIO
    if is_short and not is_non_heading(text) and (is_large or (bold and len(text) <= 100)):
        level = numbering_level(text) or (1 if size >= body_size * 1.5 else 2)
        return ElementType.HEADING, level
    if is_unstyled_heading(text):
        return ElementType.HEADING, numbering_level(text)
    if LIST_MARKER.match(text):
        return ElementType.LIST_ITEM, None
    return ElementType.PARAGRAPH, None


def _body_font_size(pdf: pymupdf.Document) -> float:
    """The most common font size, weighted by characters: that's body text."""
    sizes: Counter[float] = Counter()
    for page in pdf:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    sizes[round(span["size"] * 2) / 2] += len(span["text"].strip())
    return sizes.most_common(1)[0][0] if sizes else 10.0


def _in_any(bbox: tuple[float, float, float, float], rects: list[pymupdf.Rect]) -> bool:
    """True if the centre of bbox lies inside any of rects."""
    centre = pymupdf.Point((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    return any(centre in r for r in rects)
