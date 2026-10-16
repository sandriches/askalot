"""Step 2: print chunks, to see what each strategy actually produces.

uv run python scripts/02_inspect_chunks.py DOC_ID --page 18
uv run python scripts/02_inspect_chunks.py DOC_ID --grep SYS-0015 --chunker fixed-512-64
"""

import argparse

from rag.config import get_settings
from rag.io import read_jsonl
from rag.models import Chunk


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("doc_id")
    ap.add_argument("--parser", default="docintel")
    ap.add_argument("--chunker", default="structure-512")
    ap.add_argument("--page", type=int, help="chunks that include this page")
    ap.add_argument("--grep", help="chunks whose text contains this string")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    path = get_settings().data_dir / "chunks" / args.parser / f"{args.chunker}.jsonl"
    chunks = [c for c in read_jsonl(path, Chunk) if c.doc_id == args.doc_id]
    if args.page:
        chunks = [c for c in chunks if args.page in c.pages]
    if args.grep:
        chunks = [c for c in chunks if args.grep in c.text]
    for c in chunks[: args.limit]:
        meta = f"pages={c.pages}  tokens={c.token_count}  elements={len(c.element_ids)}"
        print(f"\n━━ {c.chunk_id}  {meta}")
        print(f"   section: {' > '.join(c.section_path) or '(none)'}")
        print("   " + c.text.replace("\n", "\n   "))
    print(f"\n({len(chunks)} matching chunks, showing {min(len(chunks), args.limit)})")


if __name__ == "__main__":
    main()
