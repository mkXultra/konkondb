"""JSON file backend for Raw DB (json_backend_unified.md §9).

All records are held in memory. Changes are flushed to disk
atomically via os.replace().

Satisfies RawDBBackend Protocol (backend.py).
"""

from __future__ import annotations

import json
import os
import sys
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

_CURRENT_VERSION = 2
_WARN_THRESHOLD = 10_000


class JsonRawDataAccessor:
    """RawDataAccessor backed by an in-memory list of RawRecord.

    Satisfies RawDataAccessor Protocol (models.py).
    Also implements modified_since() per §3.2 internal requirement.
    """

    def __init__(
        self,
        records: list[RawRecord],
        since_ts: datetime | None = None,
        modified_since_ts: datetime | None = None,
    ) -> None:
        self._records = records
        self._since_ts = since_ts
        self._modified_since_ts = modified_since_ts

    def _filtered(self) -> list[RawRecord]:
        result = self._records
        if self._since_ts is not None:
            result = [r for r in result if r.created_at > self._since_ts]
        if self._modified_since_ts is not None:
            result = [
                r for r in result
                if r.updated_at is not None and r.updated_at > self._modified_since_ts
            ]
        return result

    def __iter__(self) -> Iterator[RawRecord]:
        return iter(self._filtered())

    def __len__(self) -> int:
        return len(self._filtered())

    def since(self, timestamp: datetime) -> JsonRawDataAccessor:
        """Return a new accessor filtering records after *timestamp* (exclusive)."""
        validate_utc(timestamp)
        return JsonRawDataAccessor(
            self._records,
            since_ts=timestamp,
            modified_since_ts=self._modified_since_ts,
        )

    def modified_since(self, timestamp: datetime) -> JsonRawDataAccessor:
        """Return a new accessor filtering records modified after *timestamp*."""
        validate_utc(timestamp)
        return JsonRawDataAccessor(
            self._records,
            since_ts=self._since_ts,
            modified_since_ts=timestamp,
        )


class JsonDB:
    """Raw DB backend using a single JSON file.

    All records are held in memory. Changes are flushed to disk
    atomically via os.replace().

    Satisfies RawDBBackend Protocol (backend.py).
    """

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._records: list[RawRecord] = []
        self._index: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        """Load records from JSON file, or start empty if file doesn't exist."""
        if not self._path.exists():
            return

        try:
            text = self._path.read_text(encoding="utf-8")
            data = json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ConfigError(
                f"Failed to parse {self._path}: {e}"
            ) from e

        version = data.get("version")
        if version is None or version < _CURRENT_VERSION:
            raise ConfigError(
                f"Raw JSON schema version mismatch "
                f"(expected: {_CURRENT_VERSION}, found: {version}). "
                f"Please update konkon."
            )
        if version > _CURRENT_VERSION:
            raise ConfigError(
                f"Raw JSON schema version mismatch "
                f"(expected: {_CURRENT_VERSION}, found: {version}). "
                f"Please update konkon."
            )

        raw_records = data.get("records", [])
        for entry in raw_records:
            record = RawRecord(
                id=entry["id"],
                created_at=parse_datetime(entry["created_at"]),
                content=entry["content"],
                meta=entry.get("meta") or {},
                updated_at=parse_datetime(entry["updated_at"]),
            )
            self._records.append(record)

        # Ensure deterministic order even for manually-edited files
        self._sort_records()

    def _rebuild_index(self) -> None:
        """Rebuild the id → list index lookup."""
        self._index = {r.id: i for i, r in enumerate(self._records)}

    def _sort_records(self) -> None:
        """Sort records by (created_at, id) ASC and rebuild index."""
        self._records.sort(key=lambda r: (r.created_at, r.id))
        self._rebuild_index()

    def _serialize_records(self) -> list[dict[str, object]]:
        """Serialize records list to JSON-compatible dicts."""
        result = []
        for r in self._records:
            entry: dict[str, object] = {
                "id": r.id,
                "created_at": format_datetime(r.created_at),
                "updated_at": format_datetime(r.updated_at) if r.updated_at else format_datetime(r.created_at),
                "content": r.content,
                "meta": dict(r.meta) if r.meta else {},
            }
            result.append(entry)
        return result

    def _save(self) -> None:
        """Atomically write all records to the JSON file."""
        data = {"version": _CURRENT_VERSION, "records": self._serialize_records()}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self._path)

    def insert(
        self,
        content: str,
        meta: dict[str, JSONValue] | None = None,
    ) -> RawRecord:
        """Insert a single raw record and return it as RawRecord."""
        if len(self._records) >= _WARN_THRESHOLD:
            print(
                f"[WARN] {self._path.name} contains over {_WARN_THRESHOLD} records. "
                f"Consider switching to SQLite backend for better performance.",
                file=sys.stderr,
            )

        now = datetime.now(timezone.utc)
        record_id = generate_uuid_v7(now)
        record = RawRecord(
            id=record_id,
            created_at=now,
            content=content,
            meta=meta or {},
            updated_at=now,
        )
        self._records.append(record)
        self._sort_records()
        self._save()
        return record

    def update(
        self,
        record_id: str,
        content: str | None = None,
        meta: dict[str, JSONValue] | None = None,
    ) -> RawRecord:
        """Update an existing raw record's content and/or meta."""
        if content is None and meta is None:
            raise ValueError("at least one of content or meta must be provided")

        idx = self._index.get(record_id)
        if idx is None:
            raise KeyError(f"record not found: {record_id}")

        existing = self._records[idx]
        new_content = content if content is not None else existing.content
        new_meta = meta if meta is not None else dict(existing.meta)
        now = datetime.now(timezone.utc)

        updated = RawRecord(
            id=existing.id,
            created_at=existing.created_at,
            content=new_content,
            meta=new_meta or {},
            updated_at=now,
        )
        self._records[idx] = updated
        self._save()
        return updated

    def get_record(self, record_id: str) -> RawRecord | None:
        """Return a single record by ID, or None if not found."""
        idx = self._index.get(record_id)
        if idx is None:
            return None
        return self._records[idx]

    def list_records(self, limit: int) -> list[RawRecord]:
        """Return up to *limit* records ordered by created_at DESC, id DESC."""
        sorted_desc = sorted(
            self._records,
            key=lambda r: (r.created_at, r.id),
            reverse=True,
        )
        return sorted_desc[:limit]

    def accessor(self) -> JsonRawDataAccessor:
        """Return a RawDataAccessor over all records.

        The returned accessor implements modified_since() per §3.2.
        """
        return JsonRawDataAccessor(self._records)

    def close(self) -> None:
        """No-op. JSON backend has no connection to release."""
        pass
