from __future__ import annotations
import json
from typing import Iterable, Mapping, Iterator, Any

def write_jsonl(records_iterable: Iterable[Mapping], out_path: str) -> None:
    """Write an iterable of mapping records to a UTF-8 JSONL file."""
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records_iterable:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def read_jsonl(path: str) -> Iterator[Any]:
    """Yield Python objects from a JSONL file lazily."""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
