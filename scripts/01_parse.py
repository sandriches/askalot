"""Step 1: parse every downloaded PDF into Elements.

    uv run python scripts/01_parse.py [--doc DOC_ID]

Writes:
    data/parsed/documents.jsonl          one Document per source file
    data/parsed/<parser>/<doc_id>.jsonl  that document's Elements
"""

import argparse
import time
from collections import Counter

from rag.config import get_settings
from rag.ingest.manifest import load_manifest, to_document
from rag.ingest.pymupdf_parser import PyMuPDFParser
from rag.io import write_jsonl
from rag.models import Element, ElementType

PARSERS = {"pymupdf": PyMuPDFParser}
MIN_CHARS_PER_PAGE = 50  # less than this on a page suggests a scan with no text layer


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parser", choices=PARSERS, default="pymupdf")
    ap.add_argument("--doc", help="only parse this doc_id")
    args = ap.parse_args()

    parser = PARSERS[args.parser]()
    out_dir = get_settings().data_dir / "parsed"
    entries = [e for e in load_manifest() if e.path.exists()]
    if args.doc:
        entries = [e for e in entries if e.doc_id == args.doc]

    documents = []
    print(
        f"{'doc_id':<32}{'pages':>6}{'elems':>7}{'head':>6}{'list':>6}{'table':>6}"
        f"{'other':>6}{'empty pg':>9}{'sec':>6}"
    )
    for entry in entries:
        start = time.perf_counter()
        doc = to_document(entry)
        elements = parser.parse(entry.path, entry.doc_id)
        write_jsonl(out_dir / parser.name / f"{doc.doc_id}.jsonl", elements)
        documents.append(doc)

        types = Counter(e.type for e in elements)
        print(
            f"{doc.doc_id:<32}{doc.n_pages:>6}{len(elements):>7}"
            f"{types[ElementType.HEADING]:>6}{types[ElementType.LIST_ITEM]:>6}"
            f"{types[ElementType.TABLE]:>6}{types[ElementType.OTHER]:>6}"
            f"{len(_empty_pages(elements, doc.n_pages)):>9}"
            f"{time.perf_counter() - start:>6.1f}"
        )

    if not args.doc:
        write_jsonl(out_dir / "documents.jsonl", documents)


def _empty_pages(elements: list[Element], n_pages: int) -> list[int]:
    chars = Counter()
    for e in elements:
        if e.type != ElementType.OTHER:
            chars[e.page] += len(e.text)
    return [p for p in range(1, n_pages + 1) if chars[p] < MIN_CHARS_PER_PAGE]


if __name__ == "__main__":
    main()
