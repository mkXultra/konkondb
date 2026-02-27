"""Project resolution — System-level (no Bounded Context).

Responsibilities:
- Resolve project root (find .konkon/ directory)
- Provide paths to project resources (.konkon/raw.db, konkon.py)
- Lazy Raw DB initialization (create on first insert, not on init)

References:
- 04_cli_design.md §4.1 (init creates .konkon/ but NOT the DB)
- 04_cli_design.md §4.2 (insert lazily creates DB)

Used by:
- cli/init.py — create .konkon/ and konkon.py template
- cli/insert.py — open/create Raw DB, delegate to core/raw_db.py
- cli/build.py — open Raw DB (read), delegate to core/plugin_host.py
- cli/search.py — delegate to core/plugin_host.py
- serving/api.py — same as cli but via HTTP
- serving/mcp.py — same as cli but via MCP
"""

from pathlib import Path

KONKON_DIR = ".konkon"
RAW_DB_NAME = "raw.db"
PLUGIN_FILE = "konkon.py"

PLUGIN_TEMPLATE = '''\
"""konkon plugin."""

from konkon.types import RawDataAccessor, QueryRequest, QueryResult


def build(raw_data: RawDataAccessor) -> None:
    """Transform raw data into AI-ready context."""
    pass


def query(request: QueryRequest) -> str | QueryResult:
    """Handle a query request."""
    return ""
'''


def init_project(directory: Path, *, force: bool = False) -> None:
    """Create a konkon project in *directory*.

    Creates .konkon/ (idempotent) and konkon.py template.
    Raises FileExistsError if konkon.py already exists and force is False.
    Does NOT create Raw DB (lazy init on first insert).
    """
    directory.mkdir(parents=True, exist_ok=True)

    plugin_path = directory / PLUGIN_FILE
    if plugin_path.exists() and not force:
        raise FileExistsError(f"{PLUGIN_FILE} already exists in {directory}")

    (directory / KONKON_DIR).mkdir(exist_ok=True)
    plugin_path.write_text(PLUGIN_TEMPLATE)


# TODO: Implement
# - resolve_project(start: Path = Path.cwd()) -> Path
#   - Walk up directories to find konkon.py
#   - Return project root or raise error
# - open_raw_db(project_root: Path) -> RawDB
#   - Lazy: create .konkon/raw.db if not exists
#   - Return RawDB instance
