"""Step 2: chunk the parsed documents with each strategy and print statistics.

    uv run python scripts/02_chunk.py [--parser docintel|pymupdf]

Writes data/chunks/<parser>/<chunker>.jsonl (all documents in one file).
"""

import argparse
import statistics

from rag.chunking.base import Chunker, chunkable, toc_pages
from rag.chunking.fixed import FixedChunker
from rag.chunking.structural import StructureChunker
from rag.config import get_settings
from rag.ingest.manifest import load_manifest
from rag.io import read_jsonl, write_jsonl
from rag.models import Chunk, Element


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parser", default="docintel")
    args = ap.parse_args()

    data = get_settings().data_dir
    chunkers: list[Chunker] = [FixedChunker(size=512, overlap=64), StructureChunker(max_tokens=512)]
    results: dict[str, list[Chunk]] = {c.name: [] for c in chunkers}

    print("Table-of-contents pages skipped:")
    for entry in load_manifest():
        path = data / "parsed" / args.parser / f"{entry.doc_id}.jsonl"
        if not path.exists():
            continue
        elements = read_jsonl(path, Element)
        print(f"  {entry.doc_id:<32} {sorted(toc_pages(elements)) or '-'}")
        kept = chunkable(elements)
        for chunker in chunkers:
            results[chunker.name].extend(chunker.chunk(kept))

    print(
        f"\n{'chunker':<18}{'chunks':>8}{'min':>6}{'median':>8}{'p90':>6}{'max':>6}"
        f"{'<50 tok':>9}{'multi-page':>12}{'with path':>11}"
    )
    for name, chunks in results.items():
        write_jsonl(data / "chunks" / args.parser / f"{name}.jsonl", chunks)
        tokens = sorted(c.token_count for c in chunks)
        p90 = tokens[int(len(tokens) * 0.9)]
        small = sum(t < 50 for t in tokens)
        multi = sum(len(c.pages) > 1 for c in chunks)
        with_path = sum(bool(c.section_path) for c in chunks)
        print(
            f"{name:<18}{len(chunks):>8}{tokens[0]:>6}{statistics.median(tokens):>8.0f}{p90:>6}"
            f"{tokens[-1]:>6}{small:>9}{multi:>12}{with_path:>11}"
        )


if __name__ == "__main__":
    main()
