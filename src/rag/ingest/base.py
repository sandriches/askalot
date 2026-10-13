"""The parser interface. Each parser turns one PDF into a flat list of Elements."""

from pathlib import Path
from typing import Protocol

from rag.models import Element


class Parser(Protocol):
    name: str

    def parse(self, pdf_path: Path, doc_id: str) -> list[Element]:
        """Return the document's elements in reading order, with deterministic IDs."""
        ...
