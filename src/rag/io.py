"""Read/write lists of Pydantic models as JSON Lines (one record per line).

JSONL keeps every pipeline artifact human-inspectable (`head`, `jq`, `grep`)
and diffable between runs.
"""

from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel


def write_jsonl[M: BaseModel](path: Path, records: Iterable[M]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(record.model_dump_json() + "\n")
            n += 1
    return n


def read_jsonl[M: BaseModel](path: Path, model: type[M]) -> list[M]:
    with path.open(encoding="utf-8") as f:
        return [model.model_validate_json(line) for line in f if line.strip()]
