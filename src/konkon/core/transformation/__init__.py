"""Transformation Context facade."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from konkon.core import ingestion
from konkon.core.instance import (
    PostgresConnectionManager,
    RuntimeConfig,
    load_project_runtime,
)
from konkon.core.models import BuildContext, QueryRequest, QueryResult
from konkon.core.state import create_build_state_store
from konkon.core.transformation.plugin_host import (
    invoke_build,
    invoke_query,
    invoke_schema,
    load_plugin,
)


def _coerce_runtime(project_root: Path | RuntimeConfig) -> RuntimeConfig:
    if isinstance(project_root, RuntimeConfig):
        return project_root
    return load_project_runtime(project_root)


def run_build(
    project_root: Path | RuntimeConfig,
    *,
    full: bool = False,
    plugin_path: Path | None = None,
    import_root: Path | None = None,
    connection: Any | None = None,
) -> None:
    """Load the user plugin and invoke build(raw_data, context)."""
    runtime = _coerce_runtime(project_root)
    resolved_plugin = plugin_path or runtime.plugin_path
    resolved_import_root = import_root if plugin_path is not None else (import_root or runtime.import_root)
    plugin = load_plugin(resolved_plugin, import_root=resolved_import_root)

    build_start = datetime.now(timezone.utc)
    state_manager = (
        PostgresConnectionManager(connection=connection)
        if runtime.raw_backend == "postgres"
        else None
    )
    state_store = create_build_state_store(
        runtime,
        connection_manager=state_manager,
    )
    snapshot = state_store.read()

    if full or snapshot.last_checkpoint is None:
        mode = "full"
        accessor = ingestion.get_accessor(runtime=runtime, connection=connection)
        deleted_records = ()
    else:
        mode = "incremental"
        accessor = ingestion.get_accessor(
            runtime=runtime,
            modified_since=snapshot.last_checkpoint,
            connection=connection,
        )
        tombstone_since = snapshot.last_tombstone_at or snapshot.last_checkpoint
        deleted_records = tuple(
            ingestion.get_deleted_records_since(
                None,
                tombstone_since,
                runtime=runtime,
                connection=connection,
            )
        )

    context = BuildContext(mode=mode, deleted_records=deleted_records)

    saved_cwd = os.getcwd()
    try:
        os.chdir(resolved_plugin.parent)
        invoke_build(plugin, accessor, context)
    finally:
        if hasattr(accessor, "close"):
            accessor.close()
        os.chdir(saved_cwd)

    completed_at = datetime.now(timezone.utc)
    state_store.write_success(
        build_started_at=build_start,
        completed_at=completed_at,
    )

    try:
        ingestion.purge_tombstones(
            None,
            build_start,
            runtime=runtime,
            connection=connection,
        )
    except Exception:
        print(
            "[WARN] Failed to purge tombstones. They will be retried on next build.",
            file=sys.stderr,
        )


def run_describe(
    project_root: Path | RuntimeConfig,
    *,
    plugin_path: Path | None = None,
    import_root: Path | None = None,
) -> dict:
    """Load the user plugin and invoke schema()."""
    runtime = _coerce_runtime(project_root)
    resolved_plugin = plugin_path or runtime.plugin_path
    resolved_import_root = import_root if plugin_path is not None else (import_root or runtime.import_root)
    plugin = load_plugin(resolved_plugin, import_root=resolved_import_root)

    saved_cwd = os.getcwd()
    try:
        os.chdir(resolved_plugin.parent)
        return invoke_schema(plugin)
    finally:
        os.chdir(saved_cwd)


def run_query(
    project_root: Path | RuntimeConfig,
    query_str: str,
    *,
    params: dict[str, str] | None = None,
    plugin_path: Path | None = None,
    import_root: Path | None = None,
) -> str | QueryResult:
    """Load the user plugin and invoke query(request)."""
    runtime = _coerce_runtime(project_root)
    resolved_plugin = plugin_path or runtime.plugin_path
    resolved_import_root = import_root if plugin_path is not None else (import_root or runtime.import_root)
    plugin = load_plugin(resolved_plugin, import_root=resolved_import_root)
    request = QueryRequest(query=query_str, params=params or {})

    saved_cwd = os.getcwd()
    try:
        os.chdir(resolved_plugin.parent)
        return invoke_query(plugin, request)
    finally:
        os.chdir(saved_cwd)
