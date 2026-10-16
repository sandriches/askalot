"""Token counting. Chunk sizes are measured in tokens, the unit the models see."""

from functools import lru_cache

import tiktoken

# The tokenizer used by text-embedding-3-*. Dutch needs roughly twice as many
# tokens per word as English with it, so budgets fill up faster than you'd expect.
ENCODING = "cl100k_base"


@lru_cache
def get_encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODING)


def count_tokens(text: str) -> int:
    return len(get_encoding().encode(text))
