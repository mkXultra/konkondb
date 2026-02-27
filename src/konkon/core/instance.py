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


def resolve_project(start: Path | None = None) -> Path:
    """Walk up from *start* to find the project root (directory containing konkon.py).

    Raises FileNotFoundError if konkon.py is not found up to the filesystem root.
    Per 04_cli_design.md §3.4.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        if (current / PLUGIN_FILE).exists():
            return current
        parent = current.parent
        if parent == current:
            raise FileNotFoundError(
                f"Error: {PLUGIN_FILE} not found. "
                "Run 'konkon init' to create a project, "
                "or use '--project-dir' to specify the project root."
            )
        current = parent


def raw_db_path(project_root: Path) -> Path:
    """Return the path to the Raw DB file under *project_root*/.konkon/."""
    return project_root / KONKON_DIR / RAW_DB_NAME
