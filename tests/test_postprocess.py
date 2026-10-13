from rag.ingest.postprocess import mark_repeating_margins
from rag.models import BBox, Element, ElementType


def _el(page, text, y0, el_type=ElementType.PARAGRAPH):
    return Element(
        element_id=f"d:p{page}:e{y0}",
        doc_id="d",
        page=page,
        type=el_type,
        text=text,
        bbox=BBox(x0=50, y0=y0, x1=500, y1=y0 + 40),
        parser="t",
    )


def test_boxed_header_table_repeating_in_top_margin_becomes_other():
    pages = range(1, 6)
    els = [_el(p, f"|ROK|Pagina:|{p} van 5|", 44, ElementType.TABLE) for p in pages]
    els += [_el(p, f"Inhoud van pagina {p} is uniek {'x' * p}", 400) for p in pages]
    mark_repeating_margins(els, {p: 842 for p in pages})
    assert all(e.type == ElementType.OTHER for e in els if e.bbox.y0 == 44)
    assert all(e.type == ElementType.PARAGRAPH for e in els if e.bbox.y0 == 400)


def test_repeating_text_in_body_is_kept():
    pages = range(1, 6)
    els = [_el(p, "Geen specifieke V&V-voorwaarden bepaald.", 400) for p in pages]
    mark_repeating_margins(els, {p: 842 for p in pages})
    assert all(e.type == ElementType.PARAGRAPH for e in els)


def test_header_split_differently_per_page_is_still_found():
    """Document Intelligence cuts the ROK header box differently per page."""
    pages = range(1, 7)
    els = []
    for p in pages:
        if p % 2:
            els.append(
                _el(
                    p, f"|Richtlijnen Ontwerp Kunstwerken|Pagina: {p} van 6|", 44, ElementType.TABLE
                )
            )
        else:
            els.append(_el(p, "Richtlijnen Ontwerp Kunstwerken", 30))
            els.append(_el(p, f"|Pagina:|{p} van 6|", 60, ElementType.TABLE))
        els.append(_el(p, str(p), 800))  # bare page number in the footer
    mark_repeating_margins(els, {p: 842 for p in pages})
    assert all(e.type == ElementType.OTHER for e in els)
