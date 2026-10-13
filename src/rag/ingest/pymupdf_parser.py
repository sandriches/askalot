"""Baseline parser: PyMuPDF's text layer plus a few layout heuristics.

PyMuPDF gives us text blocks with exact coordinates and font information, but
no idea what a block *is*. So we infer structure with heuristics:

- blocks are first split into runs of lines (a heading line and the paragraph
             under it often share one PyMuPDF block), then each run is typed:
- heading:   short run in a larger font, or bold and short. Level comes from
             the numbering ("3.2.1 ..." -> 3) or, if unnumbered, the font size.
- list item: starts with a bullet or "a." / "1)" style marker.
- table:     PyMuPDF's line-based table finder, rendered as Markdown by us
             (merged cells handled). Text blocks inside a table area are
             dropped so the text isn't duplicated.
- header/footer: a block near the top/bottom edge whose text (digits ignored)
             repeats on many pages. Kept, but typed OTHER so chunking can skip it.

These heuristics are the weak point, and that's intentional: step 1b compares
this baseline against Azure Document Intelligence, which uses a layout model.
"""

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from rag.models import BBox, Element, ElementType

NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")
LIST_MARKER = re.compile(r"^(?:[•\-–▪◦·●○■□]|\(?[a-z0-9]{1,2}[.)])\s+")
CAPTION = re.compile(r"^(Tabel|Figuur|Afbeelding)\s*[\dA-Z][\d.\-]*\s*[:.]", re.IGNORECASE)
BOLD_FLAG = 1 << 4  # PyMuPDF span flag for bold

MAX_HEADING_CHARS = 150
HEADING_SIZE_RATIO = 1.15  # font must be this much larger than body text
EDGE_FRACTION = 0.08  # top/bottom 8% of the page counts as header/footer zone
MIN_TABLE_OVERLAP = 0.5


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
            for page in pdf:
                blocks.extend(_parse_page(page, body_size))
            _mark_headers_and_footers(blocks, pdf)

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
        return elements


def _parse_page(page: pymupdf.Page, body_size: float) -> list[_Block]:
    page_no = page.number + 1
    out: list[_Block] = []

    tables = [t for t in page.find_tables().tables if t.row_count >= 2 and t.col_count >= 2]
    table_rects = [pymupdf.Rect(t.bbox) for t in tables]
    for t, rect in zip(tables, table_rects, strict=True):
        if markdown := _table_markdown(t.extract()):
            out.append(_Block(page_no, rect, markdown, ElementType.TABLE))

    for block in page.get_text("dict", sort=True)["blocks"]:
        if block["type"] != 0:  # 1 = image block
            continue
        if any(_overlap(pymupdf.Rect(block["bbox"]), tr) > MIN_TABLE_OVERLAP for tr in table_rects):
            continue
        for lines in _split_block(block["lines"], body_size):
            text, max_size, all_bold = _lines_text(lines)
            if not text:
                continue
            rect = pymupdf.Rect(lines[0]["bbox"])
            for line in lines[1:]:
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
    or when it starts with a list marker.
    """
    runs: list[list[dict]] = []
    prev_heading_style: bool | None = None
    for line in lines:
        spans = [s for s in line["spans"] if s["text"].strip()]
        if not spans:
            continue
        text = "".join(s["text"] for s in line["spans"]).strip()
        heading_style = all(s["flags"] & BOLD_FLAG for s in spans) or (
            max(s["size"] for s in spans) >= body_size * HEADING_SIZE_RATIO
        )
        if not runs or heading_style != prev_heading_style or LIST_MARKER.match(text):
            runs.append([])
        runs[-1].append(line)
        prev_heading_style = heading_style
    return runs


def _table_markdown(rows: list[list[str | None]]) -> str:
    """Render extracted cells as a Markdown table.

    PyMuPDF returns None for cells covered by a merged cell. Its own
    to_markdown() repeats the merged text in each of them, which triples the
    requirement text in RWS requirement cards, so we render it ourselves.
    """
    clean = [[_clean_cell(c) for c in row] for row in rows]
    clean = [row for row in clean if any(row)]
    if len(clean) < 2:
        return ""
    lines = ["|" + "|".join(clean[0]) + "|", "|" + "|".join("---" for _ in clean[0]) + "|"]
    lines += ["|" + "|".join(row) + "|" for row in clean[1:]]
    return "\n".join(lines)


def _clean_cell(cell: str | None) -> str:
    if not cell:
        return ""
    text = re.sub(r"-\n(?=[a-z])", "", cell)  # undo hyphenation inside a cell
    return re.sub(r"\s+", " ", text.replace("|", "/")).strip()


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
    text = re.sub(r"\s+", " ", text.replace("­", "")).strip()
    return text, max_size, all_bold and bool(text)


def _classify(
    text: str, size: float, bold: bool, body_size: float
) -> tuple[ElementType, int | None]:
    is_short = len(text) <= MAX_HEADING_CHARS
    is_large = size >= body_size * HEADING_SIZE_RATIO
    # Bold or large text that still isn't a heading: captions ("Tabel 6-5: ..."),
    # form labels ("Aanvangsdatum:"), and bare numbers.
    not_a_heading = CAPTION.match(text) or text.endswith(":") or sum(c.isalpha() for c in text) < 2
    if is_short and not not_a_heading and (is_large or (bold and len(text) <= 100)):
        if m := NUMBERED_HEADING.match(text):
            return ElementType.HEADING, m.group(1).count(".") + 1
        return ElementType.HEADING, 1 if size >= body_size * 1.5 else 2
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


def _mark_headers_and_footers(blocks: list[_Block], pdf: pymupdf.Document) -> None:
    """Re-type repeating blocks in the page margins as OTHER."""
    if pdf.page_count < 3:
        return

    def in_margin(b: _Block) -> bool:
        height = pdf[b.page - 1].rect.height
        return b.rect.y1 < height * EDGE_FRACTION or b.rect.y0 > height * (1 - EDGE_FRACTION)

    def key(b: _Block) -> str:
        return re.sub(r"\d+", "#", b.text.lower())

    margin_blocks = [b for b in blocks if b.type != ElementType.TABLE and in_margin(b)]
    pages_per_key: dict[str, set[int]] = {}
    for b in margin_blocks:
        pages_per_key.setdefault(key(b), set()).add(b.page)
    threshold = max(3, pdf.page_count * 0.3)
    for b in margin_blocks:
        if len(pages_per_key[key(b)]) >= threshold:
            b.type, b.heading_level = ElementType.OTHER, None


def _overlap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    """Fraction of a's area that lies inside b."""
    inter = pymupdf.Rect(a) & b
    return 0.0 if inter.is_empty or a.is_empty else inter.get_area() / a.get_area()
