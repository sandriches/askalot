from rag.chunking.base import chunkable, toc_pages
from rag.chunking.fixed import FixedChunker
from rag.chunking.structural import StructureChunker
from rag.models import Element, ElementType
from rag.tokens import count_tokens

T = ElementType
_counter = iter(range(10_000))


def el(page, text, type_=T.PARAGRAPH, level=None):
    i = next(_counter)
    return Element(
        element_id=f"d:p{page}:e{i}",
        doc_id="d",
        page=page,
        type=type_,
        text=text,
        heading_level=level,
        parser="test",
    )


def words(n, word="woord"):
    return " ".join([word] * n)


# --- table of contents ---------------------------------------------------------------


TOC_TABLE = "|1|Inleiding|4|\n|---|---|---|\n|2|Systeemdefinitie|5|\n|2.1|Fase|6|\n|3|Eisen|9|"


def test_toc_with_title_and_continuation_page_is_skipped():
    els = [
        el(1, "Vraagspecificatie Eisen"),
        el(3, "Inhoud"),
        el(3, TOC_TABLE, T.TABLE),
        el(4, "3.1 Topeisen 9"),
        el(4, "3.2 Kribbaken 10"),  # ToC continues
        el(5, "1 Inleiding", T.HEADING, 1),
        el(5, "Dit document beschrijft het werk."),
    ]
    assert toc_pages(els) == {3, 4}
    assert [e.page for e in chunkable(els)] == [1, 5, 5]


def test_inhoudsopgave_section_deep_in_the_document_is_kept():
    els = [el(p, f"Tekst op pagina {p}.") for p in range(1, 21)]
    els.append(el(14, "Inhoudsopgave", T.HEADING, 2))
    assert toc_pages(els) == set()


def test_headers_and_footers_are_not_chunked():
    els = [el(1, "Pagina 1 van 9", T.OTHER), el(1, "Inhoud van de pagina.")]
    assert [e.text for e in chunkable(els)] == ["Inhoud van de pagina."]


# --- fixed-size chunker --------------------------------------------------------------


def test_fixed_windows_overlap_and_keep_lineage():
    els = [el(p, words(300, f"p{p}")) for p in (1, 2, 3)]
    chunks = FixedChunker(size=256, overlap=32).chunk(els)
    assert all(c.token_count <= 256 for c in chunks)
    assert chunks[0].pages == [1]
    # some window straddles the page 1 / page 2 boundary and cites both
    assert any(c.pages == [1, 2] for c in chunks)
    # consecutive windows share text (the overlap)
    assert chunks[0].text.split()[-1] in chunks[1].text
    assert chunks[-1].pages == [3]


# --- structure-aware chunker ---------------------------------------------------------


def test_heading_closes_chunk_and_sets_section_path():
    els = [
        el(1, "3 Systeemeisen", T.HEADING, 1),
        el(1, "Inleidende tekst over eisen."),
        el(1, "3.1 Topeisen", T.HEADING, 2),
        el(1, "Topeis tekst."),
        el(2, "3.2 Kribbaken", T.HEADING, 2),
        el(2, "Kribbaken tekst."),
    ]
    chunks = StructureChunker(max_tokens=512).chunk(els)
    assert [c.text for c in chunks] == [
        "Inleidende tekst over eisen.",
        "Topeis tekst.",
        "Kribbaken tekst.",
    ]
    assert chunks[1].section_path == ["3 Systeemeisen", "3.1 Topeisen"]
    assert chunks[2].section_path == ["3 Systeemeisen", "3.2 Kribbaken"]  # 3.1 was closed
    assert chunks[2].pages == [2]


def test_elements_are_packed_until_the_budget_and_never_cut():
    els = [el(1, words(20)) for _ in range(5)]  # ~40 tokens each ("woord" is 2 tokens)
    chunks = StructureChunker(max_tokens=100).chunk(els)
    assert len(chunks) == 3  # 2 + 2 + 1 elements
    assert all(len(c.element_ids) in (1, 2) for c in chunks)


def test_oversized_table_is_split_by_rows_with_header_repeated():
    header = "|ID|Eis|\n|---|---|"
    rows = [f"|SYS-{i:04d}|{words(20)}|" for i in range(20)]
    table = el(1, header + "\n" + "\n".join(rows), T.TABLE)
    chunks = StructureChunker(max_tokens=150).chunk([table])
    assert len(chunks) > 1
    assert all(c.text.startswith(header) for c in chunks)
    assert all(c.token_count <= 150 for c in chunks)
    assert sum(c.text.count("|SYS-") for c in chunks) == 20  # no row lost or duplicated
    assert all(c.element_ids == [table.element_id] for c in chunks)


def test_oversized_paragraph_is_split_by_sentences():
    text = " ".join(f"Zin nummer {i} gaat over de fundering." for i in range(60))
    chunks = StructureChunker(max_tokens=100).chunk([el(1, text)])
    assert len(chunks) > 1
    assert all(c.text.endswith(".") for c in chunks)
    assert all(count_tokens(c.text) <= 100 for c in chunks)


def test_bare_numbering_is_dropped_but_numeric_tables_kept():
    els = [el(1, "11.1"), el(1, "1.1 (3)"), el(1, "|a|b|\n|---|---|\n|1|2|", T.TABLE)]
    assert [e.type for e in chunkable(els)] == [T.TABLE]


def test_budget_includes_separators_between_elements():
    els = [el(1, words(12)) for _ in range(30)]  # ~24 tokens each
    for c in StructureChunker(max_tokens=100).chunk(els):
        assert c.token_count <= 100
