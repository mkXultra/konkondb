"""Ingestion Context facade (01_conceptual_architecture.md §1.1).

Public API for data ingestion. Called by CLI and Serving layers.
Internal implementation delegates to raw_db.py or json_db.py.

Responsibilities:
- Insert a Document into Raw DB as a Raw Record
- Provide RawDataAccessor for Transformation Context (ACL #1)
- Lazy Raw DB initialization (create on first access)
- Backend resolution (SQLite or JSON)

Owns:
- Raw DB (SQLite or JSON), ingest metadata

Does NOT know about:
- AI, vectors, context, plugins, build, query

References:
- 01_conceptual_architecture.md §1.1, §2.1, §3.1
- 03_data_model.md (Raw DB schema)
- json_backend_unified.md §5, §6
- commands/insert.md
"""

import os
import sys
from datetime import datetime
from pathlib import Path

from konkon.core.ingestion.backend import RawDBBackend
from konkon.core.ingestion.json_db import JsonDB
from konkon.core.ingestion.raw_db import RawDB
from konkon.core.instance import KONKON_DIR, load_config, raw_db_path
from konkon.core.models import ConfigError, JSONValue, RawDataAccessor, RawRecord

_JSON_DB_NAME = "raw.json"


def _json_db_path(project_root: Path) -> Path:
    return project_root / KONKON_DIR / _JSON_DB_NAME


def _resolve_backend(project_root: Path) -> tuple[str, bool]:
    """Resolve backend type and whether it was explicitly set.

    Returns (backend, explicitly_set).
    Priority: env > config > auto-detect > 'sqlite' fallback.
    """
    env = os.environ.get("KONKON_RAW_BACKEND")
    if env is not None:
        return env.lower(), True
    config = load_config(project_root)
    if "raw_backend" in config:
        return str(config["raw_backend"]).lower(), True
    # Limited auto-detect: only when env/config are both unset
    db_exists = raw_db_path(project_root).exists()
    json_exists = _json_db_path(project_root).exists()
    if db_exists and json_exists:
        raise ConfigError(
            "Both .konkon/raw.db and .konkon/raw.json exist. "
            "Set 'raw_backend' in .konkon/config.toml to specify "
            "which backend to use."
        )
    if json_exists and not db_exists:
        return "json", False
    return "sqlite", False  # default (includes db-only and neither-exists)


def _check_backend_consistency(
    project_root: Path, backend: str, explicit: bool
) -> None:
    """Warn about mismatch between explicit config and existing files."""
    if not explicit:
        return  # auto-detect handles its own consistency
    db_exists = raw_db_path(project_root).exists()
    json_exists = _json_db_path(project_root).exists()

    if backend == "json" and db_exists and not json_exists:
        print(
            "[WARN] .konkon/raw.db exists but backend is 'json'. "
            "A new raw.json will be created.",
            file=sys.stderr,
        )
    elif backend == "sqlite" and json_exists and not db_exists:
        print(
            "[WARN] .konkon/raw.json exists but backend is 'sqlite'. "
            "A new raw.db will be created.",
            file=sys.stderr,
        )


def _open_db(project_root: Path) -> RawDBBackend:
    """Open (or lazily create) the appropriate Raw DB backend."""
    backend, explicit = _resolve_backend(project_root)
    if backend not in ("sqlite", "json"):
        raise ConfigError(
            f"Unknown backend: {backend!r}. Use 'sqlite' or 'json'."
        )
    _check_backend_consistency(project_root, backend, explicit)
    if backend == "json":
        return JsonDB(_json_db_path(project_root))
    return RawDB(raw_db_path(project_root))


def _db_file_exists(project_root: Path) -> bool:
    """Check if the configured backend's DB file exists."""
    backend, _ = _resolve_backend(project_root)
    if backend not in ("sqlite", "json"):
        raise ConfigError(
            f"Unknown backend: {backend!r}. Use 'sqlite' or 'json'."
        )
    if backend == "json":
        return _json_db_path(project_root).exists()
    return raw_db_path(project_root).exists()


def ingest(
    content: str,
    meta: dict[str, JSONValue] | None,
    project_root: Path,
) -> RawRecord:
    """Ingest a document into Raw DB as a Raw Record.

    Opens (or lazily creates) the Raw DB, delegates to backend.insert(),
    and returns the resulting RawRecord.
    """
    db = _open_db(project_root)
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
    db = _open_db(project_root)
    try:
        return db.update(record_id, content=content, meta=meta)
    finally:
        db.close()


def get_record(
    project_root: Path,
    record_id: str,
) -> RawRecord | None:
    """Return a single record by ID, or None if not found.

    Returns None if the Raw DB file does not exist yet
    (read-only command must not create the DB).
    """
    if not _db_file_exists(project_root):
        return None
    db = _open_db(project_root)
    try:
        return db.get_record(record_id)
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
    if not _db_file_exists(project_root):
        return []
    db = _open_db(project_root)
    try:
        return db.list_records(limit)
    finally:
        db.close()


def get_accessor(
    project_root: Path,
    modified_since: datetime | None = None,
) -> RawDataAccessor:
    """Return a RawDataAccessor over records in the Raw DB.

    If *modified_since* is given, the accessor is pre-filtered to records
    whose ``updated_at`` is after that timestamp (for incremental builds).
    This keeps the ``modified_since()`` call inside Ingestion Context,
    so Transformation Context never touches a non-Protocol method.

    The Raw DB must already exist (raises if not).
    """
    db = _open_db(project_root)
    accessor = db.accessor()
    if modified_since is not None:
        accessor = accessor.modified_since(modified_since)
    return accessor
