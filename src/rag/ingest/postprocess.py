"""Clean-up passes that run on any parser's Elements."""

import re

from rag.models import Element, ElementType

EDGE_FRACTION = 0.15  # top/bottom 15% of the page counts as header/footer zone
MIN_PAGE_SHARE = 0.3  # a header word appears in the margin of at least this share of pages
MIN_HEADER_WORDS = 0.8  # share of an element's words that must be header words


def mark_repeating_margins(elements: list[Element], page_heights: dict[int, float]) -> None:
    """Re-type running headers and footers as OTHER (in place).

    We compare *words*, not exact text, because parsers cut the same header
    box differently from page to page: Document Intelligence reads the ROK's
    boxed header as one table on one page, a paragraph plus a table on the
    next. So:

    1. Collect the words (letters only, digits ignored) of everything in the
       top/bottom margin, and count on how many pages each word appears there.
    2. Words that appear on many pages are the header vocabulary.
    3. A margin element made (almost) entirely of header vocabulary is a
       header/footer. Margin elements with no letters (page numbers) are too.

    Elements are re-typed rather than deleted, so nothing disappears silently.
    """
    n_pages = len(page_heights)
    if n_pages < 3:
        return

    def in_margin(e: Element) -> bool:
        height = page_heights[e.page]
        return e.bbox is not None and (
            e.bbox.y1 < height * EDGE_FRACTION or e.bbox.y0 > height * (1 - EDGE_FRACTION)
        )

    def words(e: Element) -> set[str]:
        return set(re.findall(r"[a-zà-ÿ]{2,}", e.text.lower()))

    margin = [e for e in elements if in_margin(e)]
    pages_per_word: dict[str, set[int]] = {}
    for e in margin:
        for w in words(e):
            pages_per_word.setdefault(w, set()).add(e.page)
    threshold = max(3, n_pages * MIN_PAGE_SHARE)
    header_words = {w for w, pages in pages_per_word.items() if len(pages) >= threshold}

    for e in margin:
        if e.type == ElementType.OTHER:
            continue
        ws = words(e)
        is_page_number = not ws and len(e.text) <= 15
        if is_page_number or (ws and len(ws & header_words) / len(ws) >= MIN_HEADER_WORDS):
            e.type, e.heading_level = ElementType.OTHER, None
