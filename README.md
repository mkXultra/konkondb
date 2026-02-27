# konkondb

AI-oriented context DB middleware — a pluggable engine between raw data and AI-ready context.

## What it does

konkondb lets you store raw data (text, JSON, documents) and transform it into AI-optimized context through a user-defined plugin. You write a `konkon.py` with two functions — `build()` to transform raw data into your preferred format (vector DB, SQLite views, Markdown, etc.) and `query()` to retrieve context from it. The framework handles storage, orchestration, and serving.

## Quick Start

```bash
# Install
pip install konkondb

# Create a new project
konkon init myproject
cd myproject

# Store some raw data
konkon insert "The quick brown fox jumps over the lazy dog"
konkon insert -m source=notes.md "Meeting notes from 2026-02-27"

# Transform data via your plugin
konkon build

# Query the transformed context
konkon search "fox"
```

## Plugin

`konkon init` generates a `konkon.py` template:

```python
"""konkon plugin."""

from konkon.types import RawDataAccessor, QueryRequest, QueryResult


def build(raw_data: RawDataAccessor) -> None:
    """Transform raw data into AI-ready context."""
    for record in raw_data:
        # record.id, record.content, record.meta, record.created_at
        pass


def query(request: QueryRequest) -> str | QueryResult:
    """Handle a query request."""
    # request.query — the search string
    # request.params — optional parameters dict
    return ""
```

`build()` receives a read-only accessor over all raw records. Use it to populate your own context store — a vector DB, a SQLite index, a set of Markdown files, or anything else.

`query()` receives a search request and returns results from your context store.

## Architecture

konkondb is organized into three Bounded Contexts with strict dependency boundaries:

```
CLI (orchestrator)
 |
 +---> Ingestion Context    — Raw DB (SQLite, append-only)
 |
 +---> Transformation Context — Plugin Host (load + invoke konkon.py)
 |
 +---> Serving Context      — REST API / MCP server adapters
```

- **Ingestion** owns the Raw DB (single source of truth). Plugins never access it directly — they receive a `RawDataAccessor` protocol instead.
- **Transformation** loads the user plugin, validates the contract (`build` + `query`), and orchestrates execution.
- **Serving** exposes `query()` results over REST or MCP. Fully stateless — no direct DB access.

Module boundaries are enforced at the import level by [tach](https://docs.gauge.sh/).

## Development

```bash
# Install dependencies
uv sync

# Run all tests (unit tests + module boundary checks)
uv run pytest

# Run boundary checks only
uv run tach check
```

Requires Python >= 3.11.

## Status

Alpha — under active development. API may change.

## License

TBD
