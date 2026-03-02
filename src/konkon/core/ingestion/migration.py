"""Raw DB backend migration logic.

Copies all records from source backend to target backend,
preserving id, created_at, updated_at, content, and meta.

Visibility: Ingestion Context internal (facade only).
NOT exposed beyond ACL.
"""

from __future__ import annotations

from konkon.core.ingestion.json_db import JsonDB
from konkon.core.ingestion.raw_db import RawDB


def run_migration(
    source: RawDB | JsonDB,
    target: RawDB | JsonDB,
    target_backend: str,
) -> int:
    """Copy all records from source to target backend.

    Preserves all fields (id, created_at, updated_at, content, meta).
    Returns the number of migrated records.

    Caller is responsible for:
    - Opening/closing source and target
    - Validating that migration is appropriate
    - Updating config.toml after success

    Transaction/flush semantics:
    - SQLite target: caller wraps in a single transaction
    - JSON target: caller calls _sort_records() + _save() after completion
    """
    count = 0
    for record in source.accessor():
        target._write_record(record)
        count += 1

    # Finalize based on target backend type
    if target_backend == "json":
        target._sort_records()
        target._save()
    elif target_backend == "sqlite":
        target._conn.commit()

    return count
