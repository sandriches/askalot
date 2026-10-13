"""Step 1b: compare two parsers' output on the same documents.

    uv run python scripts/01_compare.py                       # summary per document
    uv run python scripts/01_compare.py --page rws-vse-kribbakens 11   # one page, side by side

Run 01_parse.py for both parsers first.
"""

import argparse
from collections import Counter
from pathlib import Path

from rag.config import get_settings
from rag.ingest.manifest import load_manifest
from rag.ingest.text import numbering_level
from rag.io import read_jsonl
from rag.models import Element, ElementType

T = ElementType


def load(parser: str, doc_id: str) -> list[Element] | None:
    path: Path = get_settings().data_dir / "parsed" / parser / f"{doc_id}.jsonl"
    return read_jsonl(path, Element) if path.exists() else None


def numbered_headings(elements: list[Element]) -> set[str]:
    """The numbers of numbered headings ('3.2.1'), to compare which ones each parser found."""
    return {
        e.text.split()[0].rstrip(".")
        for e in elements
        if e.type == T.HEADING and numbering_level(e.text)
    }


def summary(a: str, b: str) -> None:
    cols = ["head", "list", "table", "other", "chars"]
    print(f"{'doc_id':<32}" + "".join(f"{c:>18}" for c in cols) + f"{'numbered hdgs':>26}")
    print(
        f"{'':<32}" + f"{a[:6] + ' / ' + b[:6]:>18}" * len(cols) + f"{'both / only a / only b':>26}"
    )
    for entry in load_manifest():
        ea, eb = load(a, entry.doc_id), load(b, entry.doc_id)
        if ea is None or eb is None:
            continue
        row = []
        for els in (ea, eb):
            types = Counter(e.type for e in els)
            chars = sum(len(e.text) for e in els if e.type != T.OTHER)
            row.append(
                [types[T.HEADING], types[T.LIST_ITEM], types[T.TABLE], types[T.OTHER], chars]
            )
        ha, hb = numbered_headings(ea), numbered_headings(eb)
        cells = "".join(f"{f'{x} / {y}':>18}" for x, y in zip(*row, strict=True))
        print(f"{entry.doc_id:<32}{cells}{f'{len(ha & hb)} / {len(ha - hb)} / {len(hb - ha)}':>26}")


def page(a: str, b: str, doc_id: str, page_no: int) -> None:
    for parser in (a, b):
        print(f"\n===== {parser} — {doc_id} p{page_no} =====")
        for e in load(parser, doc_id) or []:
            if e.page == page_no:
                level = f" L{e.heading_level}" if e.heading_level else ""
                text = e.text if e.type == T.TABLE else e.text[:140]
                print(f"[{e.type.value}{level}] {text}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="pymupdf")
    ap.add_argument("--b", default="docintel")
    ap.add_argument("--page", nargs=2, metavar=("DOC_ID", "PAGE"))
    args = ap.parse_args()
    if args.page:
        page(args.a, args.b, args.page[0], int(args.page[1]))
    else:
        summary(args.a, args.b)


if __name__ == "__main__":
    main()
