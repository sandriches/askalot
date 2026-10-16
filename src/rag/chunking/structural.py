"""Structure-aware chunker: split along the document's own sections.

Rules:
- A heading always closes the current chunk, so a chunk never spans two
  sections. Headings aren't put in the chunk text; they go into
  `section_path` (e.g. ['3 Systeemeisen', '3.2 Kribbaken']), which step 3 adds
  back as context when embedding.
- Elements are packed into a chunk until the next one would exceed
  `max_tokens`. Elements are never cut, except:
- An element that is on its own larger than `max_tokens` is split: tables by
  rows (repeating the header row in each part), text by sentences.

So a requirement card (a table) always stays in one piece, together with the
other cards of its section when they fit.
"""

import re

from rag.models import Chunk, Element, ElementType
from rag.tokens import count_tokens, get_encoding

SEPARATOR = "\n\n"
SEPARATOR_TOKENS = count_tokens(SEPARATOR)
SENTENCE_END = re.compile(r"(?<=[.!?;])\s+")


class StructureChunker:
    def __init__(self, max_tokens: int = 512):
        self.max_tokens = max_tokens
        self.name = f"structure-{max_tokens}"

    def chunk(self, elements: list[Element]) -> list[Chunk]:
        if not elements:
            return []
        doc_id, parser = elements[0].doc_id, elements[0].parser
        chunks: list[Chunk] = []
        headings: list[tuple[int, str]] = []  # (level, text) of the open sections
        current: list[tuple[str, Element]] = []  # (text, source element)
        current_tokens = 0

        def emit(parts: list[tuple[str, Element]]) -> None:
            text = SEPARATOR.join(t for t, _ in parts)
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{self.name}:{len(chunks):04d}",
                    doc_id=doc_id,
                    text=text,
                    element_ids=list(dict.fromkeys(e.element_id for _, e in parts)),
                    pages=[e.page for _, e in parts],
                    section_path=[h for _, h in headings],
                    token_count=count_tokens(text),
                    chunker=self.name,
                    parser=parser,
                )
            )

        def flush() -> None:
            nonlocal current, current_tokens
            if current:
                emit(current)
            current, current_tokens = [], 0

        for e in elements:
            if e.type == ElementType.HEADING:
                flush()
                level = e.heading_level or 1
                while headings and headings[-1][0] >= level:
                    headings.pop()
                headings.append((level, e.text))
                continue

            tokens = count_tokens(e.text) + (SEPARATOR_TOKENS if current else 0)
            if tokens > self.max_tokens:
                flush()
                for part in self._split(e):
                    emit([(part, e)])
                continue
            if current_tokens + tokens > self.max_tokens:
                flush()
                tokens -= SEPARATOR_TOKENS  # now first in its chunk: no separator
            current.append((e.text, e))
            current_tokens += tokens
        flush()
        return chunks

    def _split(self, e: Element) -> list[str]:
        """Split one oversized element into parts that each fit the budget."""
        if e.type == ElementType.TABLE:
            lines = e.text.splitlines()
            header, rows = lines[:2], lines[2:]
            return _pack(rows, self.max_tokens, "\n", prefix=header)
        sentences = SENTENCE_END.split(e.text)
        parts = []
        for s in sentences:  # a single sentence over budget gets cut by tokens
            parts.extend(
                _hard_split(s, self.max_tokens) if count_tokens(s) > self.max_tokens else [s]
            )
        return _pack(parts, self.max_tokens, " ")


def _pack(items: list[str], budget: int, sep: str, prefix: list[str] | None = None) -> list[str]:
    """Greedily group items into strings of at most `budget` tokens, prefix included.

    Measures the actual joined text, so separators are counted too. An item
    that alone exceeds the budget (e.g. one huge table row) becomes its own
    oversized part rather than being cut mid-row.
    """
    prefix = prefix or []
    groups: list[list[str]] = [[]]
    for item in items:
        if groups[-1] and count_tokens(sep.join(prefix + groups[-1] + [item])) > budget:
            groups.append([])
        groups[-1].append(item)
    return [sep.join(prefix + g) for g in groups if g]


def _hard_split(text: str, size: int) -> list[str]:
    enc = get_encoding()
    tokens = enc.encode(text)
    return [enc.decode(tokens[i : i + size]) for i in range(0, len(tokens), size)]
