"""Baseline chunker: fixed-size token windows with overlap.

The simplest strategy there is, and the reference point for step 7. It glues
a document's text together and cuts it every `size` tokens, ignoring structure:
a window can start mid-sentence, cut a table in half, or span two sections.

Traceability still holds: we track where each element's text sits in the
glued string, so every window knows which elements (and pages) it overlaps.
"""

from rag.models import Chunk, Element
from rag.tokens import get_encoding

SEPARATOR = "\n\n"


class FixedChunker:
    def __init__(self, size: int = 512, overlap: int = 64):
        if not 0 <= overlap < size:
            raise ValueError("overlap must be smaller than size")
        self.size, self.overlap = size, overlap
        self.name = f"fixed-{size}-{overlap}"

    def chunk(self, elements: list[Element]) -> list[Chunk]:
        if not elements:
            return []
        doc_id, parser = elements[0].doc_id, elements[0].parser

        # Glue the text together, remembering each element's character span.
        spans: list[tuple[int, int, Element]] = []
        parts, pos = [], 0
        for e in elements:
            spans.append((pos, pos + len(e.text), e))
            parts.append(e.text)
            pos += len(e.text) + len(SEPARATOR)
        text = SEPARATOR.join(parts)

        enc = get_encoding()
        tokens = enc.encode(text)
        # Character offset where each token starts, to map windows back to text.
        _, offsets = enc.decode_with_offsets(tokens)

        chunks = []
        step = self.size - self.overlap
        for i, start in enumerate(range(0, len(tokens), step)):
            end = min(start + self.size, len(tokens))
            char_start = offsets[start]
            char_end = offsets[end] if end < len(tokens) else len(text)
            covered = [e for s, t, e in spans if s < char_end and t > char_start]
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{self.name}:{i:04d}",
                    doc_id=doc_id,
                    text=text[char_start:char_end].strip(),
                    element_ids=[e.element_id for e in covered],
                    pages=[e.page for e in covered],
                    token_count=end - start,
                    chunker=self.name,
                    parser=parser,
                )
            )
            if end == len(tokens):
                break
        return chunks
