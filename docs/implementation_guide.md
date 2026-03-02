# Implementation Guide

Rules and conventions for implementing konkon db.
Read this before writing any code.

## Directory Structure

```
src/konkon/
├── types.py                        # Public API re-export for plugin developers
├── cli/                            # CLI layer (orchestrator)
│   ├── __init__.py                 #   click group + help command
│   ├── init.py                     #   → core.instance
│   ├── insert.py                   #   → core.ingestion
│   ├── build.py                    #   → core.transformation
│   ├── search.py                   #   → core.transformation
│   └── serve.py                    #   → serving/
├── core/
│   ├── models.py                   # Shared types (RawRecord, QueryRequest, etc.)
│   ├── instance.py                  # System-level project resolution (no BC)
│   ├── ingestion/                  # Ingestion Context (BC)
│   │   ├── __init__.py             #   Facade — public API
│   │   └── raw_db.py              #   Internal — only facade can access
│   └── transformation/             # Transformation Context (BC)
│       ├── __init__.py             #   Facade — public API
│       └── plugin_host.py         #   Internal — only facade can access
└── serving/                        # Serving Context (BC)
    ├── api.py                      # REST API adapter
    └── mcp.py                      # MCP server adapter
```

## Module Boundaries (tach)

Boundaries are enforced by [tach](https://docs.gauge.sh/) at the import level.
Configuration: `tach.toml`

### Layers (top → bottom)

```
cli        → can import: core.instance, core.ingestion, core.transformation, serving
serving    → can import: core.transformation, core.instance
core       → cannot import cli or serving
```

### Internal module visibility

| Module | Visible to |
| :--- | :--- |
| `core.ingestion.raw_db` | `core.ingestion` only |
| `core.transformation.plugin_host` | `core.transformation` only |
| `core.models` | All modules (utility) |
| `konkon.types` | All modules (utility) |

### Key restrictions

- `transformation` depends on `ingestion` **facade**, never on `raw_db` directly (ACL #1)
- `serving` cannot access `ingestion` at all (stateless principle)
- `plugin_host` receives `RawDataAccessor` as a protocol, not a concrete class

## Implementation Patterns

### CLI commands are thin wrappers

CLI modules parse arguments and delegate to core facades. No business logic.

```python
# cli/insert.py — CORRECT
@click.command()
def insert(text, meta):
    record = ingestion.ingest(content, parsed_meta, project_root)
    click.echo(record.id)

# cli/insert.py — WRONG (logic in CLI)
@click.command()
def insert(text, meta):
    db = RawDB(path)          # Don't touch internals
    db.insert(text, meta)     # Don't call internal APIs
```

### Facade → Internal delegation

Each BC has a facade (`__init__.py`) that is the only entry point.
Internal modules (`raw_db.py`, `plugin_host.py`) are never imported from outside.

```python
# core/ingestion/__init__.py — facade
from konkon.core.ingestion.raw_db import RawDB  # OK: facade imports internal

def ingest(content, meta, project_root):
    db = RawDB(project_root / ".konkon" / "raw.db")
    return db.insert(content, meta)
```

### CWD guarantee (save / restore)

Plugin invocation wraps `os.chdir` in a `try/finally` to guarantee CWD restoration,
even if the plugin raises an exception.

```python
# core/transformation/__init__.py — CORRECT
saved_cwd = os.getcwd()
try:
    os.chdir(plugin_path.parent)
    invoke_build(plugin, accessor)
finally:
    os.chdir(saved_cwd)
```

Ref: 04_cli_conventions.md §2.6 CWD 保証

### RawDB connection (open / close)

Facade functions open the DB, perform the operation, and close in `finally`.
The caller never holds a long-lived connection.

```python
# core/ingestion/__init__.py — CORRECT
def ingest(content, meta, project_root):
    db = _open_raw_db(project_root)
    try:
        return db.insert(content, meta)
    finally:
        db.close()
```

### Lazy DB initialization

Raw DB is NOT created during `konkon init`. It is lazily created on first `konkon insert`.

- `init`: creates `.konkon/` dir + `konkon.py` template only
- `insert`: opens or creates `.konkon/raw.db` on first call

Ref: commands/init.md, commands/insert.md

## Testing

### Run all tests

```bash
uv run pytest
```

This runs both unit tests and module boundary checks (`tests/test_architecture.py`).

### TDD workflow

1. Write failing test (Red)
2. Implement minimum code to pass (Green)
3. Refactor

### Test location

| Source | Test |
| :--- | :--- |
| `core/ingestion/` | `tests/test_core/test_raw_db.py` |
| `core/models.py` | `tests/test_core/test_models.py` |
| `cli/` | `tests/test_cli/test_main.py` |
| Module boundaries | `tests/test_architecture.py` |

## Adding a New Feature

1. Identify which Bounded Context owns the feature
2. Write tests first
3. Implement in the BC's internal module
4. Expose through the BC's facade (`__init__.py`)
5. Wire up from CLI (thin wrapper)
6. Run `uv run pytest` — must pass both unit tests and boundary checks

## References

- [01_conceptual_architecture.md](design/01_conceptual_architecture.md) — Bounded Contexts, ACLs
- [02_interface_contracts.md](design/02_interface_contracts.md) — Plugin Contract
- [03_data_model.md](design/03_data_model.md) — Raw DB schema
- [04_cli_conventions.md](design/04_cli_conventions.md) — CLI conventions
- [commands/](design/commands/) — Individual command specs
- [05_project_structure.md](design/05_project_structure.md) — Technology choices
