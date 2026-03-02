# konkondb

Materialized views for AI — pre-build the context your LLM actually needs.

## The Problem

Most RAG systems follow a **Compute on Read** pattern: chunk documents, vector-search at query time, and hope the retrieved fragments give the LLM enough context. This leads to:

- **Lost context** — chunking destroys document structure, cross-references, and the big picture
- **Wasted tokens** — raw fragments flood the context window, leaving less room for reasoning
- **Fragile iteration** — "AI gives bad answers" but you can't tell if the problem is your prompt, your retrieval, or your data

## The Solution

konkondb flips this to **Compute on Write**. Instead of searching raw data at query time, you **pre-build** AI-optimized views — summaries, structured Markdown, relationship maps, filtered tables — and serve them directly.

```
Raw Data ──▶ build() ──▶ Context Store ──▶ query() ──▶ AI-ready context
             (your logic)   (your format)    (your logic)
```

**You control the transformation.** Write a `konkon.py` plugin with your own `build()` and `query()` logic. Use any technology inside — LLM summarization, vector DBs, SQL views, plain Markdown files. konkondb handles the rest: data storage, incremental builds, CLI, Python API, and serving over REST/MCP.

### Why this matters

- **Stable, predictable output** — same query always returns the same pre-built context, no retrieval variance
- **Fast iteration** — change your transform logic, run `konkon build`, test immediately. No prompt tweaking.
- **Token efficient** — deliver exactly the context the LLM needs, pre-structured and pre-condensed
- **Fully portable** — SQLite-based, no external services required. Your data + plugin = reproducible context anywhere

## Quick Start

```bash
# Install
pip install konkondb

# Initialize a project in the current directory
konkon init

# Store some raw data
konkon insert "The quick brown fox jumps over the lazy dog"
konkon insert -m source_uri=notes.md "Meeting notes from 2026-02-27"

# Transform data via your plugin
konkon build

# Query the transformed context
konkon search "fox"

# Pass parameters to query()
konkon search "fox" --param view=summary
```

## Plugin

`konkon init` generates a `konkon.py` template:

```python
"""konkon plugin."""

from konkon.types import RawDataAccessor, QueryRequest, QueryResult


def schema():
    """Declare the query interface."""
    return {
        "description": "My konkon plugin",
        "params": {},
        "result": {
            "description": "Query result",
        },
    }


def build(raw_data: RawDataAccessor) -> None:
    """Transform raw data into AI-ready context."""
    pass


def query(request: QueryRequest) -> str | QueryResult:
    """Handle a query request."""
    return ""
```

All three functions are required:

- **`schema()`** declares the plugin's query interface — description, accepted parameters, and result metadata. Used by `konkon describe`, MCP tool definitions, and REST API docs.
- **`build()`** receives a read-only accessor over raw records. Use it to populate your own context store — a vector DB, a SQLite index, a set of Markdown files, or anything else.
- **`query()`** receives a search request (`request.query` + `request.params`) and returns results from your context store.

## CLI Commands

| Command | Description |
|---|---|
| `konkon init [DIR]` | Create a konkon project (generates `konkon.py` template and `.konkon/` directory) |
| `konkon insert [TEXT]` | Append text data to Raw DB (supports stdin) |
| `konkon update ID` | Update an existing Raw Record's content or metadata |
| `konkon build` | Run `build()` from the plugin (supports incremental builds) |
| `konkon search "query"` | Run `query()` from the plugin and output results |
| `konkon describe` | Show the plugin's schema (query interface) |
| `konkon raw list` | List recent Raw Records (debug) |
| `konkon raw get ID` | Show a single Raw Record by ID (debug) |
| `konkon serve api\|mcp` | Start a REST API or MCP server (not yet implemented) |

## Python API

konkondb can also be used as a library. The public API mirrors the CLI commands:

```python
from pathlib import Path
import konkon

project = Path(".")
konkon.init(project)
record = konkon.insert("some content", {"source_uri": "test.md"}, project)
konkon.build(project)
result = konkon.search(project, "query", params={"view": "summary"})
schema = konkon.describe(project)
```

## Example: Self-Indexing Plugin

[`examples/konkondb/`](examples/konkondb/) is a real-world plugin that konkondb uses to index its own project. It builds structured context for AI coding agents using LLM-based document condensation.

```
targets.py                   konkon.py                    context.json
┌─────────────┐              ┌──────────────┐             ┌──────────┐
│ BUILDS      │──build()────▶│ _build_*()   │────────────▶│ views    │
│ (what to store) │           │              │             │ tables   │
└─────────────┘              └──────────────┘             └──────────┘
┌─────────────┐              ┌──────────────┐             ┌──────────┐
│ QUERIES     │──query()────▶│ _render_*()  │◀────────────│ views    │
│ (how to assemble)│           │              │             │ tables   │
└─────────────┘              └──────────────┘             └──────────┘
```

The plugin provides multiple views via `--param view=`:

| View | Purpose |
|---|---|
| `implementation` | Condensed design docs + source file map for implementation tasks |
| `design` | Raw design docs + doc index for architectural decisions |
| `plugin-dev` | Plugin Contract specs + example plugin code |
| `dev-full` | Combined design + implementation context |

```bash
# Build context (LLM condenses docs, generates file summaries)
uv run konkon build --full

# Get implementation context
uv run konkon search "" --param view=implementation

# Filter by source path
uv run konkon search "" --param view=implementation --param source=cli
```

Key patterns demonstrated:
- **Declarative configuration**: `targets.py` separates build targets and query views from the engine in `konkon.py`
- **LLM integration**: Parallel LLM calls with caching for document condensation
- **Multiple views**: One plugin serves different context needs via `params`
- **Context Store**: Simple `context.json` as the materialized view

## Architecture

konkondb is organized into three Bounded Contexts with an Application Layer providing unified orchestration:

```
CLI / Python API (Entry Points)
 |
 +---> Application Layer     — Thin Orchestrator (Use Cases)
        |
        +---> Ingestion Context       — Raw DB (SQLite, append-only)
        |
        +---> Transformation Context  — Plugin Host (load + invoke konkon.py)
        |
        +---> Serving Context         — REST API / MCP server adapters
```

- **Application Layer** orchestrates Context Facades without business logic. CLI and Python API are symmetric entry points that delegate to the same Use Cases.
- **Ingestion** owns the Raw DB (single source of truth). Plugins never access it directly — they receive a `RawDataAccessor` protocol instead.
- **Transformation** loads the user plugin, validates the contract (`schema` + `build` + `query`), and orchestrates execution.
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
