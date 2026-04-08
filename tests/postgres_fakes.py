"""Reusable postgres fakes for tests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any


def _normalize_sql(sql: Any) -> str:
    return " ".join(str(sql).split())


@dataclass
class FakeCursor:
    rows: list[tuple[Any, ...]]
    rowcount: int = 0

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)

    def __iter__(self):
        return iter(self.rows)


class FakePostgresConnection:
    """Very small in-memory simulation of the postgres paths under test."""

    def __init__(self, *, schema: str = "public") -> None:
        self.schema = schema
        self.schema_exists = True
        self.available_tables: set[str] = set()
        self.records: dict[str, dict[str, Any]] = {}
        self.deletions: list[dict[str, Any]] = []
        self.build_states: dict[str, dict[str, Any]] = {}
        self.queries: list[tuple[str, tuple[Any, ...]]] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def execute(self, sql: Any, params: Any | None = None) -> FakeCursor:
        normalized = _normalize_sql(sql)
        params_tuple = tuple(params or ())
        self.queries.append((normalized, params_tuple))

        if "FROM information_schema.schemata" in normalized:
            requested_schema = params_tuple[0]
            rows = [(requested_schema,)] if self.schema_exists and requested_schema == self.schema else []
            return FakeCursor(rows, rowcount=len(rows))

        if "FROM information_schema.tables" in normalized:
            requested_schema, requested_tables = params_tuple
            if requested_schema != self.schema:
                return FakeCursor([], rowcount=0)
            rows = [(name,) for name in requested_tables if name in self.available_tables]
            return FakeCursor(rows, rowcount=len(rows))

        if normalized.startswith("CREATE SCHEMA IF NOT EXISTS"):
            self.schema_exists = True
            return FakeCursor([], rowcount=0)

        match = re.match(r'CREATE TABLE IF NOT EXISTS "([^"]+)"\."([^"]+)"', normalized)
        if match:
            self.schema = match.group(1)
            self.available_tables.add(match.group(2))
            return FakeCursor([], rowcount=0)

        if normalized.startswith("CREATE INDEX IF NOT EXISTS"):
            return FakeCursor([], rowcount=0)

        if 'INSERT INTO "' in normalized and '"."raw_records"' in normalized:
            record_id, created_at, updated_at, content, meta_json = params_tuple
            self.records[record_id] = {
                "id": record_id,
                "created_at": created_at,
                "updated_at": updated_at,
                "content": content,
                "meta": meta_json,
            }
            return FakeCursor([], rowcount=1)

        if 'UPDATE "' in normalized and '"."raw_records"' in normalized:
            content, meta_json, updated_at, record_id = params_tuple
            row = self.records[record_id]
            row["content"] = content
            row["meta"] = meta_json
            row["updated_at"] = updated_at
            return FakeCursor([], rowcount=1)

        if 'DELETE FROM "' in normalized and '"."raw_records"' in normalized:
            record_id = params_tuple[0]
            existed = self.records.pop(record_id, None)
            return FakeCursor([], rowcount=1 if existed else 0)

        if 'INSERT INTO "' in normalized and '"."raw_deletions"' in normalized:
            record_id, deleted_at, meta_json = params_tuple
            self.deletions.append(
                {
                    "record_id": record_id,
                    "deleted_at": deleted_at,
                    "meta": meta_json,
                }
            )
            return FakeCursor([], rowcount=1)

        if 'SELECT id, created_at, updated_at, content, meta::text FROM "' in normalized and '"."raw_records"' in normalized:
            rows = self._select_records(normalized, params_tuple)
            return FakeCursor(rows, rowcount=len(rows))

        if 'SELECT COUNT(*) FROM "' in normalized and '"."raw_records"' in normalized:
            rows = self._select_records(
                normalized.replace("SELECT COUNT(*)", "SELECT id, created_at, updated_at, content, meta::text"),
                params_tuple,
            )
            return FakeCursor([(len(rows),)], rowcount=1)

        if 'SELECT record_id, meta::text FROM "' in normalized and '"."raw_deletions"' in normalized:
            since = params_tuple[0]
            rows = [
                (entry["record_id"], entry["meta"])
                for entry in sorted(
                    self.deletions,
                    key=lambda item: (item["deleted_at"], item["record_id"]),
                )
                if entry["deleted_at"] > since
            ]
            return FakeCursor(rows, rowcount=len(rows))

        if 'SELECT build_state_key, last_checkpoint, last_build_at, last_tombstone_at, metadata::text FROM "' in normalized:
            key = params_tuple[0]
            row = self.build_states.get(key)
            if row is None:
                return FakeCursor([], rowcount=0)
            return FakeCursor(
                [
                    (
                        row["build_state_key"],
                        row["last_checkpoint"],
                        row["last_build_at"],
                        row["last_tombstone_at"],
                        row["metadata"],
                    )
                ],
                rowcount=1,
            )

        if 'INSERT INTO "' in normalized and '"."build_state"' in normalized:
            (
                build_state_key,
                last_checkpoint,
                last_build_at,
                last_tombstone_at,
                metadata_json,
                updated_at,
            ) = params_tuple
            self.build_states[build_state_key] = {
                "build_state_key": build_state_key,
                "last_checkpoint": last_checkpoint,
                "last_build_at": last_build_at,
                "last_tombstone_at": last_tombstone_at,
                "metadata": metadata_json,
                "updated_at": updated_at,
            }
            return FakeCursor([], rowcount=1)

        raise AssertionError(f"Unhandled SQL in fake connection: {normalized}")

    def _select_records(
        self,
        normalized: str,
        params: tuple[Any, ...],
    ) -> list[tuple[Any, ...]]:
        rows = list(self.records.values())
        if "WHERE id = %s" in normalized:
            record_id = params[0]
            rows = [row for row in rows if row["id"] == record_id]
        if "WHERE created_at > %s" in normalized and "AND updated_at > %s" not in normalized:
            since = params[0]
            rows = [row for row in rows if row["created_at"] > since]
        if "WHERE updated_at > %s" in normalized and "AND" not in normalized:
            since = params[0]
            rows = [row for row in rows if row["updated_at"] > since]
        if "WHERE created_at > %s AND updated_at > %s" in normalized:
            created_since, updated_since = params[0], params[1]
            rows = [
                row for row in rows
                if row["created_at"] > created_since and row["updated_at"] > updated_since
            ]
        reverse = "ORDER BY created_at DESC, id DESC" in normalized
        rows.sort(key=lambda row: (row["created_at"], row["id"]), reverse=reverse)
        if "LIMIT %s" in normalized:
            limit = params[-1]
            rows = rows[:limit]
        return [
            (
                row["id"],
                row["created_at"],
                row["updated_at"],
                row["content"],
                row["meta"],
            )
            for row in rows
        ]

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        self.closed = True


class FakePsycopgModule:
    """Tiny object with connect() for monkeypatching."""

    def __init__(self, connection: FakePostgresConnection) -> None:
        self._connection = connection
        self.calls: list[str] = []

    def connect(self, dsn: str) -> FakePostgresConnection:
        self.calls.append(dsn)
        return self._connection
