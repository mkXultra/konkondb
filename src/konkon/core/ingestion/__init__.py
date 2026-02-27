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

from datetime import datetime
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


def update(
    record_id: str,
    content: str | None,
    meta: dict[str, JSONValue] | None,
    project_root: Path,
) -> RawRecord:
    """Update an existing Raw Record's content and/or meta.

    Raises KeyError if record_id is not found.
    """
    db = _open_raw_db(project_root)
    try:
        return db.update(record_id, content=content, meta=meta)
    finally:
        db.close()


def list_records(
    project_root: Path,
    limit: int = 20,
) -> list[RawRecord]:
    """Return up to *limit* recent records from the Raw DB (newest first).

    Returns an empty list if the Raw DB file does not exist yet
    (read-only command must not create the DB).
    """
    db_file = raw_db_path(project_root)
    if not db_file.exists():
        return []
    db = _open_raw_db(project_root)
    try:
        return db.list_records(limit)
    finally:
        db.close()


def get_accessor(
    project_root: Path,
    modified_since: datetime | None = None,
):
    """Return a RawDataAccessor over records in the Raw DB.

    If *modified_since* is given, the accessor is pre-filtered to records
    whose ``updated_at`` is after that timestamp (for incremental builds).
    This keeps the ``modified_since()`` call inside Ingestion Context,
    so Transformation Context never touches a non-Protocol method.

    The Raw DB must already exist (raises if not).
    """
    db = _open_raw_db(project_root)
    accessor = db.accessor()
    if modified_since is not None:
        accessor = accessor.modified_since(modified_since)
    return accessor
