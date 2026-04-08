"""Application Layer use cases."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from konkon.core import ingestion
from konkon.core.instance import (
    PostgresConnectionManager,
    RuntimeConfig,
    create_postgres_connection_manager,
    init_project as _init_project,
    load_config,
    load_project_runtime,
    save_config,
)
from konkon.core.models import JSONValue, QueryResult, RawRecord, ConfigError
from konkon.core.transformation import run_build as _run_build
from konkon.core.transformation import run_describe as _run_describe
from konkon.core.transformation import run_query as _run_query


def _resolve_runtime(
    project_root: Path | None = None,
    *,
    runtime: RuntimeConfig | None = None,
) -> RuntimeConfig:
    if runtime is not None:
        return runtime
    if project_root is None:
        raise ValueError("project_root or runtime is required")
    return load_project_runtime(project_root)


@contextmanager
def _runtime_connection(
    runtime: RuntimeConfig,
    *,
    connection_manager: PostgresConnectionManager | None = None,
) -> Iterator[Any | None]:
    if runtime.raw_backend != "postgres":
        yield None
        return

    manager = connection_manager or create_postgres_connection_manager(runtime)
    assert manager is not None
    created_manager = connection_manager is None
    try:
        with manager.acquire() as connection:
            yield connection
    finally:
        if created_manager:
            manager.close()


def init(
    directory: Path,
    *,
    force: bool = False,
    plugin: str | None = None,
    import_root: str | None = None,
    raw_backend: str | None = None,
) -> None:
    """Initialize a konkon project."""
    _init_project(
        directory,
        force=force,
        plugin=plugin,
        import_root=import_root,
        raw_backend=raw_backend,
    )


def insert(
    content: str,
    meta: dict[str, JSONValue] | None,
    project_root: Path | None = None,
    *,
    runtime: RuntimeConfig | None = None,
    connection_manager: PostgresConnectionManager | None = None,
) -> RawRecord:
    resolved_runtime = _resolve_runtime(project_root, runtime=runtime)
    with _runtime_connection(
        resolved_runtime,
        connection_manager=connection_manager,
    ) as connection:
        return ingestion.ingest(
            content,
            meta,
            runtime=resolved_runtime,
            connection=connection,
        )


def update(
    record_id: str,
    *,
    content: str | None,
    meta: dict[str, JSONValue] | None,
    project_root: Path | None = None,
    runtime: RuntimeConfig | None = None,
    connection_manager: PostgresConnectionManager | None = None,
) -> RawRecord:
    resolved_runtime = _resolve_runtime(project_root, runtime=runtime)
    with _runtime_connection(
        resolved_runtime,
        connection_manager=connection_manager,
    ) as connection:
        return ingestion.update(
            record_id,
            content,
            meta,
            runtime=resolved_runtime,
            connection=connection,
        )


def delete(
    record_id: str,
    project_root: Path | None = None,
    *,
    runtime: RuntimeConfig | None = None,
    connection_manager: PostgresConnectionManager | None = None,
) -> None:
    resolved_runtime = _resolve_runtime(project_root, runtime=runtime)
    with _runtime_connection(
        resolved_runtime,
        connection_manager=connection_manager,
    ) as connection:
        ingestion.delete(
            record_id,
            project_root,
            runtime=resolved_runtime,
            connection=connection,
        )


def build(
    project_root: Path | None = None,
    *,
    full: bool = False,
    plugin_override: Path | None = None,
    runtime: RuntimeConfig | None = None,
    connection_manager: PostgresConnectionManager | None = None,
) -> None:
    resolved_runtime = _resolve_runtime(project_root, runtime=runtime)
    with _runtime_connection(
        resolved_runtime,
        connection_manager=connection_manager,
    ) as connection:
        if plugin_override is not None:
            _run_build(
                resolved_runtime,
                full=full,
                plugin_path=plugin_override,
                import_root=None,
                connection=connection,
            )
        else:
            _run_build(
                resolved_runtime,
                full=full,
                connection=connection,
            )


def describe(
    project_root: Path | None = None,
    *,
    plugin_override: Path | None = None,
    runtime: RuntimeConfig | None = None,
) -> dict:
    resolved_runtime = _resolve_runtime(project_root, runtime=runtime)
    if plugin_override is not None:
        return _run_describe(
            resolved_runtime,
            plugin_path=plugin_override,
            import_root=None,
        )
    return _run_describe(resolved_runtime)


def search(
    project_root: Path | None,
    query: str,
    *,
    params: dict[str, str] | None = None,
    plugin_override: Path | None = None,
    runtime: RuntimeConfig | None = None,
) -> str | QueryResult:
    resolved_runtime = _resolve_runtime(project_root, runtime=runtime)
    if plugin_override is not None:
        return _run_query(
            resolved_runtime,
            query,
            params=params,
            plugin_path=plugin_override,
            import_root=None,
        )
    return _run_query(
        resolved_runtime,
        query,
        params=params,
    )


def raw_list(
    project_root: Path | None = None,
    *,
    limit: int = 20,
    runtime: RuntimeConfig | None = None,
    connection_manager: PostgresConnectionManager | None = None,
) -> list[RawRecord]:
    resolved_runtime = _resolve_runtime(project_root, runtime=runtime)
    with _runtime_connection(
        resolved_runtime,
        connection_manager=connection_manager,
    ) as connection:
        return ingestion.list_records(
            project_root,
            limit=limit,
            runtime=resolved_runtime,
            connection=connection,
        )


def raw_get(
    project_root: Path | None,
    record_id: str,
    *,
    runtime: RuntimeConfig | None = None,
    connection_manager: PostgresConnectionManager | None = None,
) -> RawRecord | None:
    resolved_runtime = _resolve_runtime(project_root, runtime=runtime)
    with _runtime_connection(
        resolved_runtime,
        connection_manager=connection_manager,
    ) as connection:
        return ingestion.get_record(
            project_root,
            record_id,
            runtime=resolved_runtime,
            connection=connection,
        )


def setup_db(
    project_root: Path | None = None,
    *,
    runtime: RuntimeConfig | None = None,
    connection_manager: PostgresConnectionManager | None = None,
) -> None:
    resolved_runtime = _resolve_runtime(project_root, runtime=runtime)
    if resolved_runtime.raw_backend != "postgres":
        raise ConfigError("setup-db is only available for the postgres backend.")
    with _runtime_connection(
        resolved_runtime,
        connection_manager=connection_manager,
    ) as connection:
        assert connection is not None
        ingestion.setup_db(runtime=resolved_runtime, connection=connection)


def migrate(
    target_backend: str,
    project_root: Path,
    *,
    force: bool = False,
) -> tuple[int, str]:
    """Migrate Raw DB to a different backend."""
    count, source_backend = ingestion.migrate(
        project_root, target_backend, force=force,
    )
    config = load_config(project_root)
    config["raw_backend"] = target_backend
    save_config(project_root, config)
    return count, source_backend
