"""Example plugin: export all raw records to context.json."""

import json
from pathlib import Path

from konkon.types import RawDataAccessor, QueryRequest, QueryResult


def schema():
    """Declare query interface."""
    return {
        "description": "Full-text search over raw records exported to JSON",
        "params": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 100,
            },
        },
        "result": {
            "description": "Matching records as JSON array",
            "metadata_keys": ["total"],
        },
    }


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
    """Search context.json for records whose content matches the query."""
    path = Path("context.json")
    if not path.exists():
        return "No context built yet. Run 'konkon build' first."

    records = json.loads(path.read_text())
    matches = [r for r in records if request.query.lower() in r["content"].lower()]

    if not matches:
        return QueryResult(content=f"No records matching '{request.query}'.")

    return QueryResult(
        content=json.dumps(matches, indent=2, ensure_ascii=False),
        metadata={"total": len(matches)},
    )
