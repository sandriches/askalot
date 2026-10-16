"""Domain models shared by every pipeline stage.

The lineage is the backbone of traceability:

    Document  1──*  Element  *──*  Chunk
    (a PDF)         (a parsed block    (the unit we embed and retrieve)
                     on one page)

Every Chunk lists the Element IDs it was built from, and every Element knows
its document, page and bounding box. So any retrieved chunk, and any answer
citing it, can be traced back to an exact region of a source page.

Answer / Citation models are added in step 6, when we need them.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


class BBox(BaseModel):
    """Rectangle on a page, in PDF points (1/72 inch), origin top-left.

    PyMuPDF already reports points with a top-left origin. Document Intelligence
    reports inches for PDFs, so its parser multiplies by 72 to match.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def _check_order(self) -> Self:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError(f"degenerate bbox: {self}")
        return self


class Document(BaseModel):
    """One source file, as described in `data/raw/manifest.yaml`."""

    doc_id: str = Field(description="Stable, human-readable slug, e.g. 'rws-rok-1-4'")
    title: str
    source_path: str = Field(description="Path relative to the project root")
    source_url: str | None = None
    sha256: str = Field(description="Content hash; detects a changed file under the same name")
    n_pages: int = Field(ge=1)
    language: str = "nl"


class ElementType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"  # text holds the table as Markdown
    OTHER = "other"  # headers/footers, captions, anything unclassified


class Element(BaseModel):
    """One block of content on one page, as produced by a parser (step 1)."""

    element_id: str
    doc_id: str
    page: int = Field(ge=1, description="1-based, matching what a PDF viewer shows")
    type: ElementType
    text: str
    bbox: BBox | None = None
    heading_level: int | None = Field(default=None, ge=1)
    parser: str = Field(description="Which parser made this, e.g. 'pymupdf' or 'docintel'")

    @staticmethod
    def make_id(doc_id: str, page: int, index: int) -> str:
        """Deterministic ID, so re-parsing a file gives the same IDs."""
        return f"{doc_id}:p{page}:e{index}"


class Chunk(BaseModel):
    """A retrievable unit of text, built from one or more Elements (step 2)."""

    chunk_id: str
    doc_id: str
    text: str
    element_ids: list[str] = Field(min_length=1)
    pages: list[int] = Field(min_length=1)
    section_path: list[str] = Field(
        default_factory=list,
        description="Heading trail, e.g. ['3 Eisen', '3.2 Geluid']",
    )
    token_count: int = Field(ge=0)
    chunker: str = Field(description="Which chunking strategy made this, e.g. 'fixed-512'")
    parser: str = Field(description="Which parser made the underlying elements")

    @model_validator(mode="after")
    def _sort_pages(self) -> Self:
        self.pages = sorted(set(self.pages))
        return self
