import pytest
from pydantic import ValidationError

from rag.models import BBox, Chunk, Element, ElementType


def test_element_id_is_deterministic():
    assert Element.make_id("rws-rok", 3, 7) == "rws-rok:p3:e7"


def test_bbox_rejects_inverted_rectangle():
    with pytest.raises(ValidationError):
        BBox(x0=100, y0=0, x1=50, y1=10)


def test_element_pages_are_one_based():
    with pytest.raises(ValidationError):
        Element(
            element_id="d:p0:e0",
            doc_id="d",
            page=0,
            type=ElementType.PARAGRAPH,
            text="x",
            parser="test",
        )


def test_chunk_must_trace_to_at_least_one_element():
    with pytest.raises(ValidationError):
        Chunk(
            chunk_id="c",
            doc_id="d",
            text="x",
            element_ids=[],
            pages=[1],
            token_count=1,
            chunker="test",
        )


def test_chunk_pages_are_sorted_and_deduplicated():
    chunk = Chunk(
        chunk_id="c",
        doc_id="d",
        text="x",
        element_ids=["d:p2:e0", "d:p1:e4"],
        pages=[2, 1, 2],
        token_count=1,
        chunker="test",
    )
    assert chunk.pages == [1, 2]


def test_element_roundtrips_through_json():
    el = Element(
        element_id="d:p1:e0",
        doc_id="d",
        page=1,
        type=ElementType.TABLE,
        text="| a | b |",
        bbox=BBox(x0=0, y0=0, x1=10, y1=10),
        parser="test",
    )
    assert Element.model_validate_json(el.model_dump_json()) == el
