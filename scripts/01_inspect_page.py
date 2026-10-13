"""Step 1: draw parsed elements onto a page image, to see what the parser found.

    uv run python scripts/01_inspect_page.py DOC_ID PAGE [--parser pymupdf]

Saves data/parsed/inspect/<parser>/<doc_id>-p<page>.png with one coloured box
per element (colour = type, label = index on the page and heading level).
"""

import argparse

import pymupdf

from rag.config import get_settings
from rag.ingest.manifest import load_manifest
from rag.io import read_jsonl
from rag.models import Element, ElementType

COLOURS = {
    ElementType.HEADING: (0.85, 0.1, 0.1),
    ElementType.PARAGRAPH: (0.1, 0.4, 0.85),
    ElementType.LIST_ITEM: (0.1, 0.6, 0.2),
    ElementType.TABLE: (0.6, 0.1, 0.7),
    ElementType.OTHER: (0.55, 0.55, 0.55),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("doc_id")
    ap.add_argument("page", type=int)
    ap.add_argument("--parser", default="pymupdf")
    args = ap.parse_args()

    data = get_settings().data_dir
    entry = next(e for e in load_manifest() if e.doc_id == args.doc_id)
    elements = read_jsonl(data / "parsed" / args.parser / f"{args.doc_id}.jsonl", Element)
    on_page = [e for e in elements if e.page == args.page and e.bbox]

    with pymupdf.open(entry.path) as pdf:
        page = pdf[args.page - 1]
        for i, el in enumerate(on_page):
            rect = pymupdf.Rect(el.bbox.x0, el.bbox.y0, el.bbox.x1, el.bbox.y1)
            colour = COLOURS[el.type]
            page.draw_rect(rect, color=colour, width=1.2)
            label = f"{i} {el.type.value}" + (f" L{el.heading_level}" if el.heading_level else "")
            page.insert_text((rect.x0, rect.y0 - 1.5), label, fontsize=6, color=colour)
        out = data / "parsed" / "inspect" / args.parser / f"{args.doc_id}-p{args.page}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        page.get_pixmap(dpi=110).save(out)
    print(out)
    for i, el in enumerate(on_page):
        print(f"  {i:>3} {el.type.value:<10} {el.text[:90]!r}")


if __name__ == "__main__":
    main()
