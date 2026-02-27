"""Raw DB access layer (03_data_model.md).

Manages the SQLite raw_records table and provides RawDataAccessor
for plugin consumption via ACL #1.
"""

from __future__ import annotations

import json
import os
import sqlite3
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from konkon.core.models import JSONValue, RawRecord

# -- DDL (03_data_model.md §12) --

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS raw_records (
    id          TEXT PRIMARY KEY COLLATE BINARY,
    created_at  TEXT NOT NULL,
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
    CHECK (substr(created_at, 27, 1) = 'Z')
) STRICT;
"""

_CREATE_INDEX = """\
CREATE INDEX IF NOT EXISTS idx_raw_records_created_at_id
    ON raw_records (created_at ASC, id ASC);
"""

_SELECT_COLS = "id, created_at, content, meta"


# -- Internal helpers --


def _generate_uuid_v7(now: datetime) -> str:
    """Generate a UUID v7 string from the given UTC datetime."""
    timestamp_ms = int(now.timestamp() * 1000)
    ts_bytes = struct.pack(">Q", timestamp_ms)[2:]  # 48-bit timestamp
    rand_a = os.urandom(2)
    rand_b = os.urandom(8)
    uuid_bytes = (
        ts_bytes
        + bytes([0x70 | (rand_a[0] & 0x0F), rand_a[1]])
        + bytes([0x80 | (rand_b[0] & 0x3F)])
        + rand_b[1:]
    )
    h = uuid_bytes.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _format_datetime(dt: datetime) -> str:
    """Format datetime as RFC3339 UTC fixed-width (27 chars).

    Example: 2026-02-27T12:34:56.789012Z
    """
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _parse_datetime(s: str) -> datetime:
    """Parse RFC3339 UTC fixed-width string to UTC-aware datetime."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _row_to_record(row: tuple) -> RawRecord:
    """Convert a raw_records row to RawRecord (03_data_model.md §11.1)."""
    id_, created_at_str, content, meta_str = row
    created_at = _parse_datetime(created_at_str)
    meta: dict[str, object] = json.loads(meta_str) if meta_str else {}
    return RawRecord(id=id_, created_at=created_at, content=content, meta=meta)


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
    ) -> None:
        self._conn = conn
        self._since_ts = since_ts  # pre-formatted RFC3339 string

    def __iter__(self) -> Iterator[RawRecord]:
        if self._since_ts is not None:
            sql = (
                f"SELECT {_SELECT_COLS} FROM raw_records "
                "WHERE created_at > ? ORDER BY created_at ASC, id ASC"
            )
            cursor = self._conn.execute(sql, (self._since_ts,))
        else:
            sql = (
                f"SELECT {_SELECT_COLS} FROM raw_records "
                "ORDER BY created_at ASC, id ASC"
            )
            cursor = self._conn.execute(sql)
        for row in cursor:
            yield _row_to_record(row)

    def __len__(self) -> int:
        if self._since_ts is not None:
            sql = "SELECT COUNT(*) FROM raw_records WHERE created_at > ?"
            return self._conn.execute(sql, (self._since_ts,)).fetchone()[0]
        return self._conn.execute(
            "SELECT COUNT(*) FROM raw_records"
        ).fetchone()[0]

    def since(self, timestamp: datetime) -> SqliteRawDataAccessor:
        """Return a new accessor filtering records after *timestamp* (exclusive).

        Validates that *timestamp* is UTC-aware per 03_data_model.md §11.2.
        """
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be UTC")
        return SqliteRawDataAccessor(
            self._conn, since_ts=_format_datetime(timestamp)
        )


# -- RawDB manager --


class RawDB:
    """Raw DB manager: SQLite initialization, insert, and accessor.

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
        # DDL
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_INDEX)
        self._conn.execute("PRAGMA user_version = 1")
        self._conn.commit()

    def insert(
        self,
        content: str,
        meta: dict[str, JSONValue] | None = None,
    ) -> RawRecord:
        """Insert a single raw record and return it as RawRecord.

        ID is auto-generated as UUID v7.  created_at is captured at
        call time (UTC).  Empty or None meta is stored as NULL
        (03_data_model.md §11.3).
        """
        now = datetime.now(timezone.utc)
        record_id = _generate_uuid_v7(now)
        created_at_str = _format_datetime(now)
        meta_str = json.dumps(meta) if meta else None
        self._conn.execute(
            "INSERT INTO raw_records (id, created_at, content, meta) "
            "VALUES (?, ?, ?, ?)",
            (record_id, created_at_str, content, meta_str),
        )
        self._conn.commit()
        return RawRecord(
            id=record_id,
            created_at=now,
            content=content,
            meta=meta or {},
        )

    def accessor(self) -> SqliteRawDataAccessor:
        """Return a RawDataAccessor over all records."""
        return SqliteRawDataAccessor(self._conn)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()
