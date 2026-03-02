"""Raw DB access layer (03_data_model.md).

Manages the SQLite raw_records table and provides RawDataAccessor
for plugin consumption via ACL #1.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from konkon.core.ingestion.backend import (
    format_datetime,
    generate_uuid_v7,
    parse_datetime,
    validate_utc,
)
from konkon.core.models import ConfigError, JSONValue, RawRecord

# -- DDL (03_data_model.md §12, Version 2) --

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS raw_records (
    id          TEXT PRIMARY KEY COLLATE BINARY,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    content     TEXT NOT NULL,
    meta        TEXT,

    CHECK (id <> ''),
    CHECK (meta IS NULL OR (json_valid(meta) AND json_type(meta) = 'object')),

    CHECK (length(created_at) = 27),
    CHECK (substr(created_at, 5, 1)  = '-'),
    CHECK (substr(created_at, 8, 1)  = '-'),
    CHECK (substr(created_at, 11, 1) = 'T'),
    CHECK (substr(created_at, 14, 1) = ':'),
    CHECK (substr(created_at, 17, 1) = ':'),
    CHECK (substr(created_at, 20, 1) = '.'),
    CHECK (substr(created_at, 27, 1) = 'Z'),

    CHECK (length(updated_at) = 27),
    CHECK (substr(updated_at, 5, 1)  = '-'),
    CHECK (substr(updated_at, 8, 1)  = '-'),
    CHECK (substr(updated_at, 11, 1) = 'T'),
    CHECK (substr(updated_at, 14, 1) = ':'),
    CHECK (substr(updated_at, 17, 1) = ':'),
    CHECK (substr(updated_at, 20, 1) = '.'),
    CHECK (substr(updated_at, 27, 1) = 'Z')
) STRICT;
"""

_CREATE_INDEX_CREATED = """\
CREATE INDEX IF NOT EXISTS idx_raw_records_created_at_id
    ON raw_records (created_at ASC, id ASC);
"""

_CREATE_INDEX_UPDATED = """\
CREATE INDEX IF NOT EXISTS idx_raw_records_updated_at_id
    ON raw_records (updated_at ASC, id ASC);
"""

_CURRENT_VERSION = 2

_SELECT_COLS = "id, created_at, updated_at, content, meta"


# -- Internal helpers --
# UUID v7, datetime formatting/parsing, and UTC validation
# are shared with other backends via backend.py.
# Aliases for backward compatibility within this module:
_generate_uuid_v7 = generate_uuid_v7
_format_datetime = format_datetime
_parse_datetime = parse_datetime


def _row_to_record(row: tuple) -> RawRecord:
    """Convert a raw_records row to RawRecord (03_data_model.md §11.1)."""
    id_, created_at_str, updated_at_str, content, meta_str = row
    created_at = _parse_datetime(created_at_str)
    updated_at = _parse_datetime(updated_at_str)
    meta: dict[str, object] = json.loads(meta_str) if meta_str else {}
    return RawRecord(
        id=id_,
        created_at=created_at,
        content=content,
        meta=meta,
        updated_at=updated_at,
    )


# -- RawDataAccessor implementation --


class SqliteRawDataAccessor:
    """Concrete RawDataAccessor backed by a SQLite connection.

    Satisfies the RawDataAccessor Protocol defined in
    02_interface_contracts.md.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        since_ts: str | None = None,
        modified_since_ts: str | None = None,
    ) -> None:
        self._conn = conn
        self._since_ts = since_ts  # filter by created_at
        self._modified_since_ts = modified_since_ts  # filter by updated_at

    def _where_clause(self) -> tuple[str, tuple[str, ...]]:
        """Build WHERE clause and bind params."""
        conditions: list[str] = []
        params: list[str] = []
        if self._since_ts is not None:
            conditions.append("created_at > ?")
            params.append(self._since_ts)
        if self._modified_since_ts is not None:
            conditions.append("updated_at > ?")
            params.append(self._modified_since_ts)
        if conditions:
            return " WHERE " + " AND ".join(conditions), tuple(params)
        return "", ()

    def __iter__(self) -> Iterator[RawRecord]:
        where, params = self._where_clause()
        sql = (
            f"SELECT {_SELECT_COLS} FROM raw_records"
            f"{where} ORDER BY created_at ASC, id ASC"
        )
        cursor = self._conn.execute(sql, params)
        for row in cursor:
            yield _row_to_record(row)

    def __len__(self) -> int:
        where, params = self._where_clause()
        sql = f"SELECT COUNT(*) FROM raw_records{where}"
        return self._conn.execute(sql, params).fetchone()[0]

    def since(self, timestamp: datetime) -> SqliteRawDataAccessor:
        """Return a new accessor filtering records after *timestamp* (exclusive).

        Validates that *timestamp* is UTC-aware per 03_data_model.md §11.2.
        """
        validate_utc(timestamp)
        return SqliteRawDataAccessor(
            self._conn,
            since_ts=_format_datetime(timestamp),
            modified_since_ts=self._modified_since_ts,
        )

    def modified_since(self, timestamp: datetime) -> SqliteRawDataAccessor:
        """Return a new accessor filtering records modified after *timestamp*.

        Used by the framework for incremental builds (catches both new inserts
        and updates). Not part of the RawDataAccessor Protocol.
        """
        validate_utc(timestamp)
        return SqliteRawDataAccessor(
            self._conn,
            since_ts=self._since_ts,
            modified_since_ts=_format_datetime(timestamp),
        )


# -- RawDB manager --


class RawDB:
    """Raw DB manager: SQLite initialization, insert, update, and accessor.

    Owns the SQLite connection and applies the schema defined in
    03_data_model.md §12.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._conn = sqlite3.connect(str(db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        # Session pragmas (03_data_model.md §8)
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA synchronous = NORMAL")

        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            # Fresh database — create version 2 schema directly
            self._conn.execute(_CREATE_TABLE)
            self._conn.execute(_CREATE_INDEX_CREATED)
            self._conn.execute(_CREATE_INDEX_UPDATED)
            self._conn.execute(f"PRAGMA user_version = {_CURRENT_VERSION}")
            self._conn.commit()
        elif version == 1:
            self._migrate_v1_to_v2()
        elif version > _CURRENT_VERSION:
            raise ConfigError(
                f"Raw DB schema version mismatch "
                f"(expected: {_CURRENT_VERSION}, found: {version}). "
                f"Please update konkon."
            )

    def _migrate_v1_to_v2(self) -> None:
        """Migrate from schema version 1 (no updated_at) to version 2."""
        self._conn.executescript(f"""
            ALTER TABLE raw_records RENAME TO _raw_records_v1;

            {_CREATE_TABLE}

            INSERT INTO raw_records (id, created_at, updated_at, content, meta)
                SELECT id, created_at, created_at, content, meta
                FROM _raw_records_v1;

            DROP TABLE _raw_records_v1;

            {_CREATE_INDEX_CREATED}
            {_CREATE_INDEX_UPDATED}

            PRAGMA user_version = {_CURRENT_VERSION};
        """)

    def insert(
        self,
        content: str,
        meta: dict[str, JSONValue] | None = None,
    ) -> RawRecord:
        """Insert a single raw record and return it as RawRecord.

        ID is auto-generated as UUID v7.  created_at and updated_at are
        captured at call time (UTC).  Empty or None meta is stored as NULL
        (03_data_model.md §11.3).
        """
        now = datetime.now(timezone.utc)
        record_id = _generate_uuid_v7(now)
        ts_str = _format_datetime(now)
        meta_str = json.dumps(meta) if meta else None
        self._conn.execute(
            "INSERT INTO raw_records (id, created_at, updated_at, content, meta) "
            "VALUES (?, ?, ?, ?, ?)",
            (record_id, ts_str, ts_str, content, meta_str),
        )
        self._conn.commit()
        return RawRecord(
            id=record_id,
            created_at=now,
            content=content,
            meta=meta or {},
            updated_at=now,
        )

    def update(
        self,
        record_id: str,
        content: str | None = None,
        meta: dict[str, JSONValue] | None = None,
    ) -> RawRecord:
        """Update an existing raw record's content and/or meta.

        At least one of content or meta must be provided.
        Returns the updated RawRecord.  Raises KeyError if id not found.
        """
        if content is None and meta is None:
            raise ValueError("at least one of content or meta must be provided")

        # Fetch existing record
        row = self._conn.execute(
            f"SELECT {_SELECT_COLS} FROM raw_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"record not found: {record_id}")

        existing = _row_to_record(row)
        new_content = content if content is not None else existing.content
        new_meta = meta if meta is not None else dict(existing.meta)
        now = datetime.now(timezone.utc)
        updated_at_str = _format_datetime(now)
        meta_str = json.dumps(new_meta) if new_meta else None

        self._conn.execute(
            "UPDATE raw_records SET content = ?, meta = ?, updated_at = ? "
            "WHERE id = ?",
            (new_content, meta_str, updated_at_str, record_id),
        )
        self._conn.commit()
        return RawRecord(
            id=existing.id,
            created_at=existing.created_at,
            content=new_content,
            meta=new_meta or {},
            updated_at=now,
        )

    def get_record(self, record_id: str) -> RawRecord | None:
        """Return a single record by ID, or None if not found."""
        row = self._conn.execute(
            f"SELECT {_SELECT_COLS} FROM raw_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    def list_records(self, limit: int) -> list[RawRecord]:
        """Return up to *limit* records ordered by created_at DESC, id DESC.

        Newest records first — suitable for ``konkon raw list`` display.
        """
        rows = self._conn.execute(
            f"SELECT {_SELECT_COLS} FROM raw_records "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_record(row) for row in rows]

    def accessor(self) -> SqliteRawDataAccessor:
        """Return a RawDataAccessor over all records."""
        return SqliteRawDataAccessor(self._conn)

    def _write_record(self, record: RawRecord) -> None:
        """Insert a pre-built RawRecord preserving all original fields.

        For migration use only. NOT part of RawDBBackend Protocol.
        Does NOT call commit() — caller is responsible for transaction control.
        """
        meta_str = json.dumps(dict(record.meta)) if record.meta else None
        self._conn.execute(
            "INSERT INTO raw_records (id, created_at, updated_at, content, meta) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                record.id,
                _format_datetime(record.created_at),
                _format_datetime(record.updated_at or record.created_at),
                record.content,
                meta_str,
            ),
        )

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()
