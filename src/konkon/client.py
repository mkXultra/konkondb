"""Public app-lib client entrypoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from konkon.application import build, delete, insert, raw_get, raw_list, search, update
from konkon.core.instance import (
    PostgresConnectionManager,
    RuntimeConfig,
    create_postgres_connection_manager,
    load_project_runtime,
    load_runtime_config,
)
from konkon.core.models import JSONValue, QueryResult, RawRecord


class Client:
    """Reusable app-lib client for connected operations."""

    def __init__(
        self,
        runtime: RuntimeConfig,
        *,
        connection_manager: PostgresConnectionManager | None = None,
    ) -> None:
        self._runtime = runtime
        self._connection_manager = connection_manager
        self._closed = False

    def insert(
        self,
        content: str,
        meta: dict[str, JSONValue] | None = None,
    ) -> RawRecord:
        self._ensure_open()
        return insert(
            content,
            meta,
            runtime=self._runtime,
            connection_manager=self._connection_manager,
        )

    def update(
        self,
        record_id: str,
        *,
        content: str | None = None,
        meta: dict[str, JSONValue] | None = None,
    ) -> RawRecord:
        self._ensure_open()
        return update(
            record_id,
            content=content,
            meta=meta,
            runtime=self._runtime,
            connection_manager=self._connection_manager,
        )

    def delete(self, record_id: str) -> None:
        self._ensure_open()
        delete(
            record_id,
            runtime=self._runtime,
            connection_manager=self._connection_manager,
        )

    def build(self, *, full: bool = False) -> None:
        self._ensure_open()
        build(
            full=full,
            runtime=self._runtime,
            connection_manager=self._connection_manager,
        )

    def search(
        self,
        query: str,
        *,
        params: dict[str, str] | None = None,
    ) -> str | QueryResult:
        self._ensure_open()
        return search(
            None,
            query,
            params=params,
            runtime=self._runtime,
        )

    def raw_list(self, *, limit: int = 20) -> list[RawRecord]:
        self._ensure_open()
        return raw_list(
            limit=limit,
            runtime=self._runtime,
            connection_manager=self._connection_manager,
        )

    def raw_get(self, record_id: str) -> RawRecord | None:
        self._ensure_open()
        return raw_get(
            None,
            record_id,
            runtime=self._runtime,
            connection_manager=self._connection_manager,
        )

    def close(self) -> None:
        if self._closed:
            return
        if self._connection_manager is not None:
            self._connection_manager.close()
        self._closed = True

    def __enter__(self) -> Client:
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Client is already closed.")


def connect(
    *,
    project_root: Path | None = None,
    config: Mapping[str, Any] | None = None,
    connection: Any | None = None,
    pool: Any | None = None,
    dsn: str | None = None,
) -> Client:
    """Create a reusable app-lib client."""
    if (project_root is None) == (config is None):
        raise ValueError("Specify exactly one of 'project_root' or 'config'.")

    runtime = (
        load_project_runtime(project_root)
        if project_root is not None
        else load_runtime_config(config or {})
    )
    connection_manager = create_postgres_connection_manager(
        runtime,
        connection=connection,
        pool=pool,
        dsn=dsn,
    )
    return Client(runtime, connection_manager=connection_manager)
