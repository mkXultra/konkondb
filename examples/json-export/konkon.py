"""Example plugin: export all raw records to context.json."""

import json
from pathlib import Path

from konkon.types import RawDataAccessor, QueryRequest, QueryResult


def build(raw_data: RawDataAccessor) -> None:
    """Append all raw records to context.json."""
    records = [
        {
            "id": r.id,
            "content": r.content,
            "meta": r.meta,
            "created_at": str(r.created_at),
        }
        for r in raw_data
    ]
    Path("context.json").write_text(json.dumps(records, indent=2, ensure_ascii=False))


def query(request: QueryRequest) -> str | QueryResult:
    """Read context.json and return it."""
    path = Path("context.json")
    if not path.exists():
        return "No context built yet. Run 'konkon build' first."
    return path.read_text()
