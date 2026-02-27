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
- 04_cli_design.md §4.3 (build), §4.4 (search)
"""

import os
from pathlib import Path

from konkon.core import ingestion
from konkon.core.models import QueryRequest, QueryResult
from konkon.core.transformation.plugin_host import (
    invoke_build,
    invoke_query,
    load_plugin,
)


def run_build(project_root: Path, *, plugin_path: Path | None = None) -> None:
    """Load the user plugin and invoke build(raw_data).

    Orchestrates the data flow:
    1. Load and validate plugin (Plugin Contract, ACL #2)
    2. Get RawDataAccessor from Ingestion Context (ACL #1)
    3. Set CWD to plugin directory (04_cli_design.md §3.6)
    4. Invoke plugin.build(accessor)
    """
    if plugin_path is None:
        plugin_path = project_root / "konkon.py"

    plugin = load_plugin(plugin_path)
    accessor = ingestion.get_accessor(project_root)

    # CWD guarantee: plugin runs in its own directory (§3.6)
    saved_cwd = os.getcwd()
    try:
        os.chdir(plugin_path.parent)
        invoke_build(plugin, accessor)
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
    3. Set CWD to plugin directory (04_cli_design.md §3.6)
    4. Invoke plugin.query(request) and return result
    """
    if plugin_path is None:
        plugin_path = project_root / "konkon.py"

    plugin = load_plugin(plugin_path)
    request = QueryRequest(query=query_str, params=params or {})

    # CWD guarantee: plugin runs in its own directory (§3.6)
    saved_cwd = os.getcwd()
    try:
        os.chdir(plugin_path.parent)
        return invoke_query(plugin, request)
    finally:
        os.chdir(saved_cwd)
