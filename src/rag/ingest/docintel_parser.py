"""Layout-model parser: Azure Document Intelligence `prebuilt-layout`.

Where the PyMuPDF baseline guesses structure from fonts and positions,
Document Intelligence runs a layout model and returns it directly:

- paragraphs, in reading order, each with a *role*: title, sectionHeading,
  pageHeader, pageFooter, pageNumber, footnote (or none = body text)
- tables as cells with row/column indexes and spans (merged cells appear once)
- a section tree, from which we derive heading levels for unnumbered headings
- figures, plus OCR for any text that isn't in the PDF's text layer

Every analysis costs money (~$10 per 1000 pages), so the raw response is cached
under data/parsed/docintel/raw/, keyed by the file's hash. Converting the cached
JSON into Elements is free and repeatable.
"""

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from azure.ai.documentintelligence.models import AnalyzeResult

from rag.clients import get_docintel_client
from rag.config import get_settings
from rag.ingest.manifest import sha256_file
from rag.ingest.postprocess import mark_repeating_margins
from rag.ingest.text import (
    LIST_MARKER,
    clean_text,
    is_non_heading,
    is_unstyled_heading,
    numbering_level,
    table_markdown,
)
from rag.models import BBox, Element, ElementType

MODEL_ID = "prebuilt-layout"
POINTS_PER_UNIT = {"inch": 72.0, "pixel": 1.0}  # PDFs come back in inches
SELECTION_MARK = re.compile(r":(un)?selected:")
OTHER_ROLES = {"pageHeader", "pageFooter", "pageNumber"}


@dataclass
class _Item:
    page: int
    offset: int  # position in DI's reading order
    text: str
    type: ElementType
    bbox: BBox | None
    heading_level: int | None = None


class DocIntelParser:
    name = "docintel"

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or get_settings().data_dir / "parsed" / self.name / "raw"

    def parse(self, pdf_path: Path, doc_id: str) -> list[Element]:
        return to_elements(self.analyze(pdf_path, doc_id), doc_id, self.name)

    def analyze(self, pdf_path: Path, doc_id: str) -> AnalyzeResult:
        """Run the layout model, or load the cached result for this exact file."""
        cache = self.cache_dir / f"{doc_id}-{sha256_file(pdf_path)[:12]}.json"
        if cache.exists():
            return AnalyzeResult(json.loads(cache.read_text(encoding="utf-8")))
        with pdf_path.open("rb") as f:
            poller = get_docintel_client().begin_analyze_document(
                MODEL_ID, f, content_type="application/octet-stream"
            )
        result = poller.result()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result.as_dict(), ensure_ascii=False), encoding="utf-8")
        return result


def to_elements(result: AnalyzeResult, doc_id: str, parser: str = "docintel") -> list[Element]:
    """Convert a Document Intelligence result into our Element schema."""
    units = {p.page_number: POINTS_PER_UNIT.get(p.unit or "inch", 72.0) for p in result.pages}
    table_spans = [(s.offset, s.offset + s.length) for t in result.tables or [] for s in t.spans]
    figure_spans = [(s.offset, s.offset + s.length) for f in result.figures or [] for s in f.spans]
    section_depth = _section_depths(result)

    items: list[_Item] = []
    for i, para in enumerate(result.paragraphs or []):
        offset = para.spans[0].offset
        if _inside(offset, table_spans):
            continue  # cell text; the table element carries it
        text = clean_text(SELECTION_MARK.sub("", para.content))
        if not text:
            continue
        region = para.bounding_regions[0]
        el_type, level = _classify(para.role, text, section_depth.get(i))
        if _inside(offset, figure_spans):
            el_type, level = ElementType.OTHER, None  # labels inside a diagram
        bbox = _bbox(region.polygon, units[region.page_number])
        items.append(_Item(region.page_number, offset, text, el_type, bbox, level))

    for table in result.tables or []:
        items.extend(_table_items(table, units))

    items.sort(key=lambda it: (it.page, it.offset))
    elements: list[Element] = []
    index_on_page: Counter[int] = Counter()
    for it in items:
        idx = index_on_page[it.page]
        index_on_page[it.page] += 1
        elements.append(
            Element(
                element_id=Element.make_id(doc_id, it.page, idx),
                doc_id=doc_id,
                page=it.page,
                type=it.type,
                text=it.text,
                bbox=it.bbox,
                heading_level=it.heading_level,
                parser=parser,
            )
        )
    heights = {p.page_number: (p.height or 11.69) * units[p.page_number] for p in result.pages}
    mark_repeating_margins(elements, heights)
    return elements


def _classify(role: str | None, text: str, depth: int | None) -> tuple[ElementType, int | None]:
    if role in OTHER_ROLES:
        return ElementType.OTHER, None
    if role == "title":
        return ElementType.HEADING, 1
    if role == "sectionHeading" and not is_non_heading(text):
        return ElementType.HEADING, numbering_level(text) or max(1, depth or 1)
    if is_unstyled_heading(text):
        return ElementType.HEADING, numbering_level(text)
    if LIST_MARKER.match(text):
        return ElementType.LIST_ITEM, None
    return ElementType.PARAGRAPH, None


def _table_items(table, units: dict[int, float]) -> list[_Item]:
    """One TABLE item per page the table appears on, so citations stay page-exact.

    Merged cells are reported once, at their top-left position, so the other
    positions stay empty: no duplicated text.
    """
    cells_by_page = defaultdict(list)
    for cell in table.cells:
        page = (cell.bounding_regions or table.bounding_regions)[0].page_number
        cells_by_page[page].append(cell)

    items = []
    for page, cells in cells_by_page.items():
        grid: dict[int, list[str]] = defaultdict(lambda: [""] * table.column_count)
        for cell in cells:
            grid[cell.row_index][cell.column_index] = SELECTION_MARK.sub("", cell.content)
        # min_rows=1: a table continuing onto a page may have a single row there
        markdown = table_markdown([grid[r] for r in sorted(grid)], min_rows=1)
        if not markdown:
            continue
        region = next((r for r in table.bounding_regions if r.page_number == page), None)
        bbox = _bbox(region.polygon, units[page]) if region else None
        offsets = [c.spans[0].offset for c in cells if c.spans]
        offset = min(offsets) if offsets else table.spans[0].offset
        items.append(_Item(page, offset, markdown, ElementType.TABLE, bbox))
    return items


def _section_depths(result: AnalyzeResult) -> dict[int, int]:
    """Map paragraph index -> nesting depth of the section that contains it.

    Sections reference their children as "/sections/3", "/paragraphs/12", etc.
    The root section (the whole document) has depth 0, so top-level sections
    have depth 1.
    """
    sections = result.sections or []
    children: dict[int, list[int]] = defaultdict(list)
    for i, section in enumerate(sections):
        for ref in section.elements or []:
            kind, idx = ref.strip("/").split("/")
            if kind == "sections":
                children[i].append(int(idx))
    nested = {c for cs in children.values() for c in cs}

    depth: dict[int, int] = {}
    stack = [(i, 0) for i in range(len(sections)) if i not in nested]
    while stack:
        i, d = stack.pop()
        depth[i] = d
        stack.extend((c, d + 1) for c in children[i])

    para_depth: dict[int, int] = {}
    for i, section in enumerate(sections):
        for ref in section.elements or []:
            kind, idx = ref.strip("/").split("/")
            if kind == "paragraphs":
                para_depth.setdefault(int(idx), depth.get(i, 0))
    return para_depth


def _bbox(polygon: list[float] | None, scale: float) -> BBox | None:
    """DI polygons are [x1, y1, x2, y2, ...] in page units; we want points."""
    if not polygon:
        return None
    xs, ys = polygon[0::2], polygon[1::2]
    return BBox(x0=min(xs) * scale, y0=min(ys) * scale, x1=max(xs) * scale, y1=max(ys) * scale)


def _inside(offset: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= offset < end for start, end in spans)
