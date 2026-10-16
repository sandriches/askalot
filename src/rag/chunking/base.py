"""What both chunkers share: the interface, and which elements are worth chunking."""

import math
import re
from collections import Counter
from typing import Protocol

from rag.ingest.text import numbering_level
from rag.models import Chunk, Element, ElementType

TOC_TITLE = re.compile(r"^(inhoud|inhoudsopgave|inhoudsindex|table of contents)$", re.IGNORECASE)
DOT_LEADER = re.compile(r"\.{4,}\s*\d+$")
ENDS_IN_PAGE_NUMBER = re.compile(r"\s\d{1,3}$")


class Chunker(Protocol):
    name: str

    def chunk(self, elements: list[Element]) -> list[Chunk]:
        """Chunk one document's elements (already filtered, in reading order)."""
        ...


def chunkable(elements: list[Element]) -> list[Element]:
    """Drop what shouldn't be retrieved.

    - headers/footers (OTHER)
    - the table of contents: it repeats every heading in the document, so it
      would match almost any query while containing no answers
    - stray numbering with no words ('11.1', '1.1 (3)'), left over where the
      parser separated a number from its text
    """
    skip = toc_pages(elements)
    return [
        e
        for e in elements
        if e.type != ElementType.OTHER and e.page not in skip and not _is_bare_numbering(e)
    ]


def _is_bare_numbering(e: Element) -> bool:
    return e.type != ElementType.TABLE and sum(c.isalpha() for c in e.text) < 2


def toc_pages(elements: list[Element]) -> set[int]:
    """Pages that hold the table of contents (or a list of tables/figures).

    It starts on a front page with an 'Inhoud' title or with mostly ToC-like
    lines, and continues on following pages while they still look like a ToC.
    Only the front of the document counts: RTD 1004 has a real section titled
    'Inhoudsopgave' on page 14 (about what a design report must contain).
    """
    if not elements:
        return set()
    by_page: dict[int, list[Element]] = {}
    for e in elements:
        if e.type != ElementType.OTHER:
            by_page.setdefault(e.page, []).append(e)
    n_pages = max(e.page for e in elements)
    front = max(5, math.ceil(n_pages * 0.1))

    def toc_share(page: int) -> float:
        chars = Counter()
        for e in by_page.get(page, []):
            chars[_is_toc_like(e)] += len(e.text)
        total = chars[True] + chars[False]
        return chars[True] / total if total else 0.0

    def has_toc_title(page: int) -> bool:
        return any(TOC_TITLE.match(_first_cell(e.text)) for e in by_page.get(page, []))

    pages: set[int] = set()
    for page in range(1, front + 1):
        if page in pages or not (has_toc_title(page) or toc_share(page) >= 0.5):
            continue
        pages.add(page)
        nxt = page + 1
        while nxt <= n_pages and toc_share(nxt) >= 0.5:
            pages.add(nxt)
            nxt += 1
    return pages


def _is_toc_like(e: Element) -> bool:
    if e.type == ElementType.TABLE:
        rows = [r for r in e.text.splitlines() if r.startswith("|") and "---" not in r]
        last_cells = [next((c for c in reversed(r.split("|")) if c.strip()), "") for r in rows]
        numeric = sum(c.strip().isdigit() for c in last_cells)
        return len(rows) >= 3 and numeric / len(rows) >= 0.6
    return bool(DOT_LEADER.search(e.text)) or (
        numbering_level(e.text) is not None and bool(ENDS_IN_PAGE_NUMBER.search(e.text))
    )


def _first_cell(text: str) -> str:
    """The text itself, or for a Markdown table, its first non-empty cell."""
    if text.startswith("|"):
        return next((c.strip() for c in text.split("|") if c.strip()), "")
    return text.strip()
