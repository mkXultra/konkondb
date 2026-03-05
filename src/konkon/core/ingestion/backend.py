"""RawDBBackend Protocol and shared utilities.

Defines the internal contract for Raw DB backends (SQLite, JSON, etc.)
and provides shared helper functions (UUID v7, datetime formatting).

Visibility: Ingestion Context internal only (raw_db.py, json_db.py, facade).
NOT exposed to Transformation Context, Serving, or Plugins.

References:
- 03_data_model.md §5 (UUID v7), §6 (datetime format)
- json_backend_unified.md §3 (RawDBBackend Protocol)
"""

from __future__ import annotations

import os
import struct
from datetime import datetime, timedelta, timezone
from typing import Protocol

from konkon.core.models import DeletedRecord, JSONValue, RawDataAccessor, RawRecord


class RawDBBackend(Protocol):
    """Ingestion Context internal Raw DB backend contract.

    Facade (__init__.py) is the sole consumer. NOT exposed beyond ACL.
    Existing RawDB (raw_db.py) satisfies this Protocol structurally.

    The accessor() method must return an object that satisfies
    RawDataAccessor Protocol AND implements modified_since(timestamp)
    for incremental build support (see §3.2).
    """

    def insert(
        self,
        content: str,
        meta: dict[str, JSONValue] | None = None,
    ) -> RawRecord: ...

    def update(
        self,
        record_id: str,
        content: str | None = None,
        meta: dict[str, JSONValue] | None = None,
    ) -> RawRecord: ...

    def get_record(self, record_id: str) -> RawRecord | None: ...

    def list_records(self, limit: int) -> list[RawRecord]: ...

    def delete(self, record_id: str) -> None: ...

    def get_deleted_records_since(
        self, timestamp: datetime
    ) -> list[DeletedRecord]: ...

    def purge_tombstones(self, before: datetime) -> int: ...

    def accessor(self) -> RawDataAccessor: ...

    def close(self) -> None: ...


# ---------------------------------------------------------
# Shared utilities (moved from raw_db.py)
# ---------------------------------------------------------


def generate_uuid_v7(now: datetime) -> str:
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


def format_datetime(dt: datetime) -> str:
    """Format datetime as RFC3339 UTC fixed-width (27 chars).

    Example: 2026-02-27T12:34:56.789012Z
    """
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def parse_datetime(s: str) -> datetime:
    """Parse RFC3339 UTC fixed-width string to UTC-aware datetime."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def validate_utc(timestamp: datetime) -> None:
    """Validate that timestamp is timezone-aware and UTC.

    Raises ValueError if not.
    """
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    if timestamp.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be UTC")
