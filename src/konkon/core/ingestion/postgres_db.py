"""PostgreSQL raw backend and bootstrap helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping

from konkon.core.ingestion.backend import (
    generate_uuid_v7,
    validate_utc,
)
from konkon.core.instance import RuntimeConfig
from konkon.core.models import ConfigError, DeletedRecord, JSONValue, RawRecord


def quote_identifier(identifier: str) -> str:
    """Quote a validated SQL identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def qualified_table_name(schema: str, table: str) -> str:
    """Return a fully-qualified table reference."""
    return f"{quote_identifier(schema)}.{quote_identifier(table)}"


def normalize_timestamp(value: datetime | str | None) -> datetime | None:
    """Normalize a DB timestamp value to UTC-aware datetime."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def assert_postgres_setup(
    connection: Any,
    runtime: RuntimeConfig,
    *,
    require_build_state: bool,
) -> None:
    """Ensure the configured schema/tables already exist."""
    schema_row = connection.execute(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name = %s",
        (runtime.schema,),
    ).fetchone()
    if schema_row is None:
        raise ConfigError(
            f"Postgres schema '{runtime.schema}' is not initialized. "
            "Run 'konkon setup-db' first."
        )

    expected = [
        runtime.raw_records_table,
        runtime.raw_deletions_table,
    ]
    if require_build_state:
        expected.append(runtime.build_state_table)

    rows = connection.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = ANY(%s)",
        (runtime.schema, expected),
    ).fetchall()
    existing = {row[0] for row in rows}
    missing = [table for table in expected if table not in existing]
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ConfigError(
            f"Postgres schema '{runtime.schema}' is missing required tables: "
            f"{missing_str}. Run 'konkon setup-db' first."
        )


def setup_postgres_db(connection: Any, runtime: RuntimeConfig) -> None:
    """Create the postgres schema and tables needed for the MVP."""
    schema_ref = quote_identifier(runtime.schema)
    records_ref = qualified_table_name(runtime.schema, runtime.raw_records_table)
    deletions_ref = qualified_table_name(runtime.schema, runtime.raw_deletions_table)
    state_ref = qualified_table_name(runtime.schema, runtime.build_state_table)
    statements = [
        f"CREATE SCHEMA IF NOT EXISTS {schema_ref}",
        f"""
        CREATE TABLE IF NOT EXISTS {records_ref} (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            content TEXT NOT NULL,
            meta JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {deletions_ref} (
            record_id TEXT NOT NULL,
            deleted_at TIMESTAMPTZ NOT NULL,
            meta JSONB NOT NULL DEFAULT '{{}}'::jsonb
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {state_ref} (
            build_state_key TEXT PRIMARY KEY,
            last_checkpoint TIMESTAMPTZ NULL,
            last_build_at TIMESTAMPTZ NULL,
            last_tombstone_at TIMESTAMPTZ NULL,
            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS
            {quote_identifier(f'idx_{runtime.raw_records_table}_created_at_id')}
        ON {records_ref} (created_at ASC, id ASC)
        """,
        f"""
        CREATE INDEX IF NOT EXISTS
            {quote_identifier(f'idx_{runtime.raw_records_table}_updated_at_id')}
        ON {records_ref} (updated_at ASC, id ASC)
        """,
        f"""
        CREATE INDEX IF NOT EXISTS
            {quote_identifier(f'idx_{runtime.raw_deletions_table}_deleted_at_record_id')}
        ON {deletions_ref} (deleted_at ASC, record_id ASC)
        """,
    ]
    try:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    except Exception:
        if hasattr(connection, "rollback"):
            connection.rollback()
        raise


def _row_value(row: Any, *names: str) -> Any:
    """Read a value from either a tuple-like or mapping row."""
    if isinstance(row, Mapping):
        for name in names:
            if name in row:
                return row[name]
        raise KeyError(names[0])
    raise TypeError("row mappings are required for named access")


def _row_to_record(row: Any) -> RawRecord:
    """Convert a postgres row to RawRecord."""
    if isinstance(row, Mapping):
        meta_text = _row_value(row, "meta")
        meta = json.loads(meta_text) if meta_text else {}
        return RawRecord(
            id=_row_value(row, "id"),
            created_at=normalize_timestamp(_row_value(row, "created_at")),
            updated_at=normalize_timestamp(_row_value(row, "updated_at")),
            content=_row_value(row, "content"),
            meta=meta,
        )
    id_, created_at, updated_at, content, meta_text = row
    meta = json.loads(meta_text) if meta_text else {}
    return RawRecord(
        id=id_,
        created_at=normalize_timestamp(created_at),
        updated_at=normalize_timestamp(updated_at),
        content=content,
        meta=meta,
    )


class PostgresRawDataAccessor:
    """RawDataAccessor backed by postgres."""

    def __init__(
        self,
        connection: Any,
        runtime: RuntimeConfig,
        *,
        since_ts: datetime | None = None,
        modified_since_ts: datetime | None = None,
    ) -> None:
        self._connection = connection
        self._runtime = runtime
        self._since_ts = since_ts
        self._modified_since_ts = modified_since_ts
        self._records_ref = qualified_table_name(
            runtime.schema,
            runtime.raw_records_table,
        )

    def _where_clause(self) -> tuple[str, list[datetime]]:
        conditions: list[str] = []
        params: list[datetime] = []
        if self._since_ts is not None:
            conditions.append("created_at > %s")
            params.append(self._since_ts)
        if self._modified_since_ts is not None:
            conditions.append("updated_at > %s")
            params.append(self._modified_since_ts)
        if conditions:
            return " WHERE " + " AND ".join(conditions), params
        return "", []

    def __iter__(self) -> Iterator[RawRecord]:
        where, params = self._where_clause()
        sql = (
            "SELECT id, created_at, updated_at, content, meta::text "
            f"FROM {self._records_ref}{where} "
            "ORDER BY created_at ASC, id ASC"
        )
        cursor = self._connection.execute(sql, params)
        for row in cursor:
            yield _row_to_record(row)

    def __len__(self) -> int:
        where, params = self._where_clause()
        row = self._connection.execute(
            f"SELECT COUNT(*) FROM {self._records_ref}{where}",
            params,
        ).fetchone()
        return 0 if row is None else row[0]

    def since(self, timestamp: datetime) -> PostgresRawDataAccessor:
        validate_utc(timestamp)
        return PostgresRawDataAccessor(
            self._connection,
            self._runtime,
            since_ts=timestamp,
            modified_since_ts=self._modified_since_ts,
        )

    def modified_since(self, timestamp: datetime) -> PostgresRawDataAccessor:
        validate_utc(timestamp)
        return PostgresRawDataAccessor(
            self._connection,
            self._runtime,
            since_ts=self._since_ts,
            modified_since_ts=timestamp,
        )


class PostgresDB:
    """Raw DB backend using an existing postgres connection."""

    def __init__(self, connection: Any, runtime: RuntimeConfig) -> None:
        assert_postgres_setup(connection, runtime, require_build_state=False)
        self._connection = connection
        self._runtime = runtime
        self._records_ref = qualified_table_name(
            runtime.schema,
            runtime.raw_records_table,
        )
        self._deletions_ref = qualified_table_name(
            runtime.schema,
            runtime.raw_deletions_table,
        )

    def insert(
        self,
        content: str,
        meta: dict[str, JSONValue] | None = None,
    ) -> RawRecord:
        now = datetime.now(timezone.utc)
        record_id = generate_uuid_v7(now)
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        self._connection.execute(
            f"""
            INSERT INTO {self._records_ref}
                (id, created_at, updated_at, content, meta)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (record_id, now, now, content, meta_json),
        )
        self._connection.commit()
        return RawRecord(
            id=record_id,
            created_at=now,
            updated_at=now,
            content=content,
            meta=meta or {},
        )

    def update(
        self,
        record_id: str,
        content: str | None = None,
        meta: dict[str, JSONValue] | None = None,
    ) -> RawRecord:
        if content is None and meta is None:
            raise ValueError("at least one of content or meta must be provided")

        existing = self.get_record(record_id)
        if existing is None:
            raise KeyError(f"record not found: {record_id}")

        new_content = content if content is not None else existing.content
        new_meta = meta if meta is not None else dict(existing.meta)
        now = datetime.now(timezone.utc)
        self._connection.execute(
            f"""
            UPDATE {self._records_ref}
            SET content = %s, meta = %s::jsonb, updated_at = %s
            WHERE id = %s
            """,
            (new_content, json.dumps(new_meta, ensure_ascii=False), now, record_id),
        )
        self._connection.commit()
        return RawRecord(
            id=existing.id,
            created_at=existing.created_at,
            updated_at=now,
            content=new_content,
            meta=new_meta,
        )

    def get_record(self, record_id: str) -> RawRecord | None:
        row = self._connection.execute(
            f"""
            SELECT id, created_at, updated_at, content, meta::text
            FROM {self._records_ref}
            WHERE id = %s
            """,
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    def list_records(self, limit: int) -> list[RawRecord]:
        rows = self._connection.execute(
            f"""
            SELECT id, created_at, updated_at, content, meta::text
            FROM {self._records_ref}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_row_to_record(row) for row in rows]

    def delete(self, record_id: str) -> None:
        existing = self.get_record(record_id)
        if existing is None:
            raise KeyError(f"record not found: {record_id}")
        now = datetime.now(timezone.utc)
        meta_json = json.dumps(dict(existing.meta), ensure_ascii=False)
        try:
            self._connection.execute(
                f"DELETE FROM {self._records_ref} WHERE id = %s",
                (record_id,),
            )
            self._connection.execute(
                f"""
                INSERT INTO {self._deletions_ref}
                    (record_id, deleted_at, meta)
                VALUES (%s, %s, %s::jsonb)
                """,
                (record_id, now, meta_json),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def get_deleted_records_since(
        self,
        timestamp: datetime,
    ) -> list[DeletedRecord]:
        validate_utc(timestamp)
        rows = self._connection.execute(
            f"""
            SELECT record_id, meta::text
            FROM {self._deletions_ref}
            WHERE deleted_at > %s
            ORDER BY deleted_at ASC, record_id ASC
            """,
            (timestamp,),
        ).fetchall()
        result: list[DeletedRecord] = []
        for record_id, meta_text in rows:
            result.append(
                DeletedRecord(
                    id=record_id,
                    meta=json.loads(meta_text) if meta_text else {},
                )
            )
        return result

    def purge_tombstones(self, before: datetime) -> int:
        """Postgres tombstone purge is disabled for the MVP."""
        validate_utc(before)
        return 0

    def accessor(self) -> PostgresRawDataAccessor:
        return PostgresRawDataAccessor(self._connection, self._runtime)

    def close(self) -> None:
        """The connection lifecycle is managed externally."""
        return None
