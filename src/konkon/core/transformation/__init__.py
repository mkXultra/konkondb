"""Transformation Context facade (01_conceptual_architecture.md §1.2).

Public API for build and query operations. Called by CLI and Serving layers.
Internal implementation delegates to plugin_host.py.

Responsibilities:
- Load user plugin (konkon.py) and validate Plugin Contract
- Execute build: plugin.build(raw_data_accessor)
- Execute query: plugin.query(request) -> str | QueryResult
- Orchestrate data flow between Ingestion Context and User Plugin

Owns:
- Plugin Host (runtime), Plugin Contract enforcement

Does NOT know about:
- Context Store internals, Raw DB schema, protocol details

ACL boundaries:
- Receives RawDataAccessor from Ingestion Context (ACL #1)
- Enforces Plugin Contract with User Plugin (ACL #2)
- Returns QueryResult to callers / Serving Context (ACL #3)

References:
- 01_conceptual_architecture.md §1.2, §2.1, §3.2
- 02_interface_contracts.md §1 (Plugin Contract), §2.1 (Async/Sync)
- commands/build.md, commands/search.md
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from konkon.core import ingestion
from konkon.core.instance import last_build_path
from konkon.core.models import BuildContext, QueryRequest, QueryResult
from konkon.core.transformation.plugin_host import (
    invoke_build,
    invoke_query,
    invoke_schema,
    load_plugin,
)


def _read_last_build(project_root: Path) -> datetime | None:
    """Read the last build timestamp, or None if no build has been done."""
    path = last_build_path(project_root)
    if not path.exists():
        return None
    text = path.read_text().strip()
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _write_last_build(project_root: Path, timestamp: datetime) -> None:
    """Write the build checkpoint timestamp."""
    path = last_build_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    utc_ts = timestamp.astimezone(timezone.utc)
    path.write_text(utc_ts.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z")


def run_build(
    project_root: Path,
    *,
    full: bool = False,
    plugin_path: Path | None = None,
) -> None:
    """Load the user plugin and invoke build(raw_data, context).

    Orchestrates the data flow (06_build_context.md §5):
    1. Load and validate plugin (Plugin Contract, ACL #2)
    2. Record build_start BEFORE querying data
    3. Determine build mode (full vs incremental)
    4. Build BuildContext with mode and deleted_records
    5. Get RawDataAccessor from Ingestion Context (ACL #1)
    6. Set CWD to plugin directory (04_cli_conventions.md §2.6)
    7. Invoke plugin.build(accessor, context)
    8. On success: write checkpoint, purge tombstones (best-effort)
    """
    if plugin_path is None:
        plugin_path = project_root / "konkon.py"

    plugin = load_plugin(plugin_path)

    # Record build start time BEFORE querying data — any updates that occur
    # during the build will have updated_at >= build_start and will be picked
    # up by the next incremental build (fixes checkpoint-skip bug).
    build_start = datetime.now(timezone.utc)

    # Determine mode and build BuildContext (06_build_context.md §5)
    last_build = _read_last_build(project_root) if not full else None

    if last_build is None:
        # Full build: all records, no deleted_records
        mode = "full"
        accessor = ingestion.get_accessor(project_root)
        deleted_records = ()
    else:
        # Incremental build: filter by updated_at > last_build
        mode = "incremental"
        accessor = ingestion.get_accessor(
            project_root, modified_since=last_build
        )
        deleted_records = tuple(
            ingestion.get_deleted_records_since(project_root, last_build)
        )

    context = BuildContext(mode=mode, deleted_records=deleted_records)

    # CWD guarantee: plugin runs in its own directory (§2.6)
    saved_cwd = os.getcwd()
    try:
        os.chdir(plugin_path.parent)
        invoke_build(plugin, accessor, context)
    finally:
        os.chdir(saved_cwd)

    # Record build start time (not completion time) as checkpoint
    _write_last_build(project_root, build_start)

    # Purge tombstones (best-effort, 06_build_context.md §4.3)
    try:
        ingestion.purge_tombstones(project_root, build_start)
    except Exception:
        print(
            "[WARN] Failed to purge tombstones. They will be retried on next build.",
            file=sys.stderr,
        )


def run_describe(
    project_root: Path,
    *,
    plugin_path: Path | None = None,
) -> dict:
    """Load the user plugin and invoke schema().

    Returns the schema dict describing the plugin's query interface.
    CWD guarantee: plugin runs in its own directory (§2.6).
    """
    if plugin_path is None:
        plugin_path = project_root / "konkon.py"

    plugin = load_plugin(plugin_path)

    # CWD guarantee: plugin runs in its own directory (§2.6)
    saved_cwd = os.getcwd()
    try:
        os.chdir(plugin_path.parent)
        return invoke_schema(plugin)
    finally:
        os.chdir(saved_cwd)


def run_query(
    project_root: Path,
    query_str: str,
    *,
    params: dict[str, str] | None = None,
    plugin_path: Path | None = None,
) -> str | QueryResult:
    """Load the user plugin and invoke query(request).

    Orchestrates the data flow:
    1. Load and validate plugin (Plugin Contract, ACL #2)
    2. Create QueryRequest from query_str + params
    3. Set CWD to plugin directory (04_cli_conventions.md §2.6)
    4. Invoke plugin.query(request) and return result
    """
    if plugin_path is None:
        plugin_path = project_root / "konkon.py"

    plugin = load_plugin(plugin_path)
    request = QueryRequest(query=query_str, params=params or {})

    # CWD guarantee: plugin runs in its own directory (§2.6)
    saved_cwd = os.getcwd()
    try:
        os.chdir(plugin_path.parent)
        return invoke_query(plugin, request)
    finally:
        os.chdir(saved_cwd)
