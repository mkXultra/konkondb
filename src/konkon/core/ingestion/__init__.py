"""Ingestion Context facade (01_conceptual_architecture.md §1.1).

Public API for data ingestion. Called by CLI and Serving layers.
Internal implementation delegates to raw_db.py.

Responsibilities:
- Insert a Document into Raw DB as a Raw Record
- Provide RawDataAccessor for Transformation Context (ACL #1)
- Lazy Raw DB initialization (create on first access)

Owns:
- Raw DB (SQLite), ingest metadata

Does NOT know about:
- AI, vectors, context, plugins, build, query

References:
- 01_conceptual_architecture.md §1.1, §2.1, §3.1
- 03_data_model.md (Raw DB schema)
- 04_cli_design.md §4.2 (insert)
"""

from pathlib import Path

from konkon.core.ingestion.raw_db import RawDB
from konkon.core.instance import raw_db_path
from konkon.core.models import JSONValue, RawRecord


def _open_raw_db(project_root: Path) -> RawDB:
    """Open (or lazily create) the Raw DB for *project_root*."""
    return RawDB(raw_db_path(project_root))


def ingest(
    content: str,
    meta: dict[str, JSONValue] | None,
    project_root: Path,
) -> RawRecord:
    """Ingest a document into Raw DB as a Raw Record.

    Opens (or lazily creates) the Raw DB, delegates to RawDB.insert(),
    and returns the resulting RawRecord.
    """
    db = _open_raw_db(project_root)
    try:
        return db.insert(content, meta)
    finally:
        db.close()


def get_accessor(project_root: Path):
    """Return a RawDataAccessor over all records in the Raw DB.

    The Raw DB must already exist (raises if not).
    """
    db = _open_raw_db(project_root)
    return db.accessor()
