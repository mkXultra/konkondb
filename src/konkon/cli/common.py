"""Shared CLI runtime helpers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import click

from konkon.core.instance import (
    PostgresConnectionManager,
    RuntimeConfig,
    create_postgres_connection_manager,
    resolve_runtime,
)


@contextmanager
def runtime_session(
    ctx: click.Context,
    *,
    needs_connection: bool,
    require_plugin: bool = True,
) -> Iterator[tuple[RuntimeConfig, PostgresConnectionManager | None]]:
    """Resolve runtime plus an optional postgres connection manager."""
    obj = ctx.obj or {}
    project_dir = obj.get("project_dir")
    config_file = obj.get("config_file")
    runtime = resolve_runtime(
        project_dir=Path(project_dir).resolve() if project_dir else None,
        config_file=Path(config_file).resolve() if config_file else None,
        require_plugin=require_plugin,
    )
    manager: PostgresConnectionManager | None = None
    try:
        if needs_connection and runtime.raw_backend == "postgres":
            manager = create_postgres_connection_manager(
                runtime,
                dsn=obj.get("raw_dsn"),
            )
        yield runtime, manager
    finally:
        if manager is not None:
            manager.close()
