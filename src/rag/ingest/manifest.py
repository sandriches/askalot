"""The corpus manifest (data/raw/manifest.yaml) and turning entries into Documents."""

import hashlib
from pathlib import Path

import pymupdf
import yaml
from pydantic import BaseModel

from rag.config import PROJECT_ROOT, get_settings
from rag.models import Document


class ManifestEntry(BaseModel):
    doc_id: str
    title: str
    publisher: str
    kind: str
    filename: str
    source_url: str

    @property
    def path(self) -> Path:
        return get_settings().data_dir / "raw" / self.filename


def load_manifest(path: Path | None = None) -> list[ManifestEntry]:
    path = path or get_settings().data_dir / "raw" / "manifest.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [ManifestEntry.model_validate(d) for d in data["documents"]]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def to_document(entry: ManifestEntry) -> Document:
    with pymupdf.open(entry.path) as pdf:
        n_pages = pdf.page_count
    return Document(
        doc_id=entry.doc_id,
        title=entry.title,
        source_path=str(entry.path.relative_to(PROJECT_ROOT)),
        source_url=entry.source_url,
        sha256=sha256_file(entry.path),
        n_pages=n_pages,
    )
