"""Ingestion Context facade."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from konkon.core.ingestion.backend import RawDBBackend
from konkon.core.ingestion.json_db import JsonDB
from konkon.core.ingestion.migration import run_migration
from konkon.core.ingestion.postgres_db import PostgresDB, setup_postgres_db as _setup_postgres_db
from konkon.core.ingestion.raw_db import RawDB
from konkon.core.instance import (
    RuntimeConfig,
    json_db_path,
    load_project_runtime,
    raw_db_path,
)
from konkon.core.models import (
    ConfigError,
    DeletedRecord,
    JSONValue,
    RawDataAccessor,
    RawRecord,
)


class _ManagedRawDataAccessor:
    """Accessor wrapper that keeps the underlying backend alive."""

    def __init__(self, backend: RawDBBackend, accessor: RawDataAccessor) -> None:
        self._backend = backend
        self._accessor = accessor

    def __iter__(self):
        return iter(self._accessor)

    def __len__(self) -> int:
        return len(self._accessor)

    def since(self, timestamp: datetime) -> _ManagedRawDataAccessor:
        return _ManagedRawDataAccessor(
            self._backend,
            self._accessor.since(timestamp),
        )

    def modified_since(self, timestamp: datetime) -> _ManagedRawDataAccessor:
        accessor = getattr(self._accessor, "modified_since")(timestamp)
        return _ManagedRawDataAccessor(self._backend, accessor)

    def close(self) -> None:
        self._backend.close()


def _coerce_runtime(
    project_root: Path | None = None,
    *,
    runtime: RuntimeConfig | None = None,
) -> RuntimeConfig:
    if runtime is not None:
        return runtime
    if project_root is None:
        raise ValueError("project_root or runtime is required")
    return load_project_runtime(project_root)


def _check_backend_consistency(runtime: RuntimeConfig) -> None:
    """Warn about mismatches for explicit project-mode local backends."""
    if not runtime.backend_explicit or runtime.project_root is None:
        return
    db_exists = raw_db_path(runtime.project_root).exists()
    json_exists = json_db_path(runtime.project_root).exists()

    if runtime.raw_backend == "json" and db_exists and not json_exists:
        print(
            "[WARN] .konkon/raw.db exists but backend is 'json'. "
            "A new raw.json will be created.",
            file=sys.stderr,
        )
    elif runtime.raw_backend == "sqlite" and json_exists and not db_exists:
        print(
            "[WARN] .konkon/raw.json exists but backend is 'sqlite'. "
            "A new raw.db will be created.",
            file=sys.stderr,
        )


def _open_db(
    runtime: RuntimeConfig,
    *,
    connection: Any | None = None,
) -> RawDBBackend:
    """Open the configured raw backend."""
    backend = runtime.raw_backend
    if backend not in ("sqlite", "json", "postgres"):
        raise ConfigError(
            f"Unknown backend: {backend!r}. Use 'sqlite', 'json', or 'postgres'."
        )
    if backend in ("sqlite", "json"):
        if runtime.project_root is None:
            raise ConfigError(
                "Stateless mode currently requires the postgres backend."
            )
        _check_backend_consistency(runtime)
        if backend == "json":
            return JsonDB(json_db_path(runtime.project_root))
        return RawDB(raw_db_path(runtime.project_root))

    if connection is None:
        raise ConfigError("Postgres backend requires an active connection.")
    return PostgresDB(connection, runtime)


def _backend_exists(runtime: RuntimeConfig) -> bool:
    """Return whether a read-only operation should attempt backend access."""
    if runtime.raw_backend == "postgres":
        return True
    if runtime.project_root is None:
        return False
    if runtime.raw_backend == "json":
        return json_db_path(runtime.project_root).exists()
    return raw_db_path(runtime.project_root).exists()


def ingest(
    content: str,
    meta: dict[str, JSONValue] | None,
    project_root: Path | None = None,
    *,
    runtime: RuntimeConfig | None = None,
    connection: Any | None = None,
) -> RawRecord:
    runtime = _coerce_runtime(project_root, runtime=runtime)
    db = _open_db(runtime, connection=connection)
    try:
        return db.insert(content, meta)
    finally:
        db.close()


def update(
    record_id: str,
    content: str | None,
    meta: dict[str, JSONValue] | None,
    project_root: Path | None = None,
    *,
    runtime: RuntimeConfig | None = None,
    connection: Any | None = None,
) -> RawRecord:
    runtime = _coerce_runtime(project_root, runtime=runtime)
    db = _open_db(runtime, connection=connection)
    try:
        return db.update(record_id, content=content, meta=meta)
    finally:
        db.close()


def get_record(
    project_root: Path | None,
    record_id: str,
    *,
    runtime: RuntimeConfig | None = None,
    connection: Any | None = None,
) -> RawRecord | None:
    runtime = _coerce_runtime(project_root, runtime=runtime)
    if not _backend_exists(runtime):
        return None
    db = _open_db(runtime, connection=connection)
    try:
        return db.get_record(record_id)
    finally:
        db.close()


def list_records(
    project_root: Path | None,
    limit: int = 20,
    *,
    runtime: RuntimeConfig | None = None,
    connection: Any | None = None,
) -> list[RawRecord]:
    runtime = _coerce_runtime(project_root, runtime=runtime)
    if not _backend_exists(runtime):
        return []
    db = _open_db(runtime, connection=connection)
    try:
        return db.list_records(limit)
    finally:
        db.close()


def get_accessor(
    project_root: Path | None = None,
    modified_since: datetime | None = None,
    *,
    runtime: RuntimeConfig | None = None,
    connection: Any | None = None,
) -> RawDataAccessor:
    runtime = _coerce_runtime(project_root, runtime=runtime)
    db = _open_db(runtime, connection=connection)
    accessor = db.accessor()
    if modified_since is not None:
        accessor = getattr(accessor, "modified_since")(modified_since)
    return _ManagedRawDataAccessor(db, accessor)


def delete(
    record_id: str,
    project_root: Path | None,
    *,
    runtime: RuntimeConfig | None = None,
    connection: Any | None = None,
) -> None:
    runtime = _coerce_runtime(project_root, runtime=runtime)
    if not _backend_exists(runtime):
        raise KeyError(f"record not found: {record_id}")
    db = _open_db(runtime, connection=connection)
    try:
        db.delete(record_id)
    finally:
        db.close()


def get_deleted_records_since(
    project_root: Path | None,
    since: datetime,
    *,
    runtime: RuntimeConfig | None = None,
    connection: Any | None = None,
) -> list[DeletedRecord]:
    runtime = _coerce_runtime(project_root, runtime=runtime)
    if not _backend_exists(runtime):
        return []
    db = _open_db(runtime, connection=connection)
    try:
        return db.get_deleted_records_since(since)
    finally:
        db.close()


def purge_tombstones(
    project_root: Path | None,
    before: datetime,
    *,
    runtime: RuntimeConfig | None = None,
    connection: Any | None = None,
) -> int:
    runtime = _coerce_runtime(project_root, runtime=runtime)
    if not _backend_exists(runtime):
        return 0
    db = _open_db(runtime, connection=connection)
    try:
        return db.purge_tombstones(before)
    finally:
        db.close()


def setup_db(
    project_root: Path | None = None,
    *,
    runtime: RuntimeConfig | None = None,
    connection: Any | None = None,
) -> None:
    """Bootstrap postgres schema/tables."""
    resolved_runtime = _coerce_runtime(project_root, runtime=runtime)
    if resolved_runtime.raw_backend != "postgres":
        raise ConfigError("setup-db is only available for the postgres backend.")
    if connection is None:
        raise ConfigError("Postgres backend requires an active connection.")
    _setup_postgres_db(connection, resolved_runtime)


def migrate(
    project_root: Path,
    target_backend: str,
    *,
    force: bool = False,
) -> tuple[int, str]:
    """Migrate all records from current backend to target backend."""
    if target_backend not in ("sqlite", "json"):
        raise ConfigError(
            f"Unknown backend: {target_backend!r}. Use 'sqlite' or 'json'."
        )

    runtime = load_project_runtime(project_root, require_plugin=False)
    current_backend = runtime.raw_backend
    if current_backend == "postgres":
        raise ConfigError("Migration from postgres is not supported yet.")
    if current_backend == target_backend:
        raise ConfigError(
            f"Already using {current_backend!r} backend. Nothing to migrate."
        )

    if not _backend_exists(runtime):
        src_name = "raw.db" if current_backend == "sqlite" else "raw.json"
        raise ConfigError(
            f"Source database .konkon/{src_name} does not exist. "
            "Nothing to migrate."
        )

    target_path = (
        json_db_path(project_root) if target_backend == "json"
        else raw_db_path(project_root)
    )
    if target_path.exists():
        if not force:
            raise FileExistsError(
                f"Target file .konkon/{target_path.name} already exists. "
                f"Use --force to overwrite."
            )
        print(
            f"[WARN] Removing existing .konkon/{target_path.name} (--force)",
            file=sys.stderr,
        )
        target_path.unlink()
        if target_backend == "sqlite":
            for suffix in ("-wal", "-shm"):
                aux = target_path.parent / (target_path.name + suffix)
                if aux.exists():
                    aux.unlink()

    source = _open_db(runtime)
    try:
        target: RawDBBackend
        if target_backend == "json":
            target = JsonDB(target_path)
        else:
            target = RawDB(target_path)
        try:
            count = run_migration(source, target, target_backend)
            return count, current_backend
        finally:
            target.close()
    finally:
        source.close()
